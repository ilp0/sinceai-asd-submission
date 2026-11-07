"""Timestral-28M encoder with its quantile head removed and a multi-label fault head added.

Backbone pass (unchanged Timestral code paths, one decoder slot instead of a forecast horizon):

    rows (R, P)  --causal per-patch scale + asinh-->  patch embedding (R, P/32, D)
    [Enc_1 .. Enc_N ; Q]  where Q is the pretrained forecast-query token, used here as a CLS token
    12 transformer blocks: time attention inside each row, variate attention across the rows of
    one window (every 4th block). Q reads all valid context patches of its row and, through the
    variate blocks, the other rows of the same window.

Head:
    per row:   [Q_out (D) | optional mean of Enc_out (D) | channel embedding (E) | window stats (6)]
               -> Linear -> GELU -> Dropout -> h_r (H)
    pooling:   class attention: class k has its own query q_k; a_k,r = softmax_r(q_k . W_k h_r)
               p_k = sum_r a_k,r W_v h_r   (a_k,r says which rows carried the evidence for class k)
    output:    logit_k = w_k . MLP(LayerNorm(p_k)) + b_k;  probability_k = sigmoid(logit_k)
Every class is an independent Bernoulli output, so several faults can be active at the same time.
"""
from __future__ import annotations

import math
import sys

import torch
from torch import Tensor, nn

from .config import resolve
from .data import N_STATS, PATCH, row_vocabulary


def import_timestral(cfg: dict):
    vp = str(resolve(cfg["backbone"]["vendor_path"]))
    if vp not in sys.path:
        sys.path.insert(0, vp)
    import timestral  # noqa: F401
    return timestral


class MultiLabelHead(nn.Module):
    def __init__(self, d_model: int, n_rows: int, n_classes: int, hc: dict):
        super().__init__()
        self.token_pool = hc["token_pool"]
        self.use_stats = bool(hc["row_stats"])
        self.pooling = hc["pooling"]
        e, h = int(hc["channel_embedding_dim"]), int(hc["hidden_dim"])
        in_dim = d_model * (2 if self.token_pool == "query_mean" else 1) + e + (N_STATS if self.use_stats else 0)
        self.row_embedding = nn.Embedding(n_rows, e) if e else None
        self.row_proj = nn.Sequential(nn.Linear(in_dim, h), nn.GELU(), nn.Dropout(hc["dropout"]))
        if self.pooling == "class_attention":
            self.class_queries = nn.Parameter(torch.randn(n_classes, h) / math.sqrt(h))
            self.key = nn.Linear(h, h, bias=False)
            self.value = nn.Linear(h, h, bias=False)
        elif self.pooling != "mean":
            raise ValueError(f"unknown pooling {self.pooling!r}")
        self.norm = nn.LayerNorm(h)
        self.mlp = nn.Sequential(nn.Linear(h, h), nn.GELU(), nn.Dropout(hc["dropout"]))
        self.out_weight = nn.Parameter(torch.randn(n_classes, h) / math.sqrt(h))
        self.out_bias = nn.Parameter(torch.zeros(n_classes))

    def set_prior(self, rate: Tensor) -> None:
        """Start every class at its expected positive rate (stable early training)."""
        r = rate.clamp(1e-4, 1 - 1e-4)
        with torch.no_grad():
            self.out_bias.copy_(torch.log(r / (1 - r)))

    def forward(self, q: Tensor, ctx: Tensor | None, row_ids: Tensor, stats: Tensor, group_ids: Tensor,
                n_groups: int) -> tuple[Tensor, Tensor | None]:
        feats = [q]
        if self.token_pool == "query_mean":
            feats.append(ctx)
        if self.row_embedding is not None:
            feats.append(self.row_embedding(row_ids))
        if self.use_stats:
            feats.append(stats)
        h = self.row_proj(torch.cat(feats, -1).to(self.row_proj[0].weight.dtype))      # (R, H)
        # Rows of one window are contiguous: pad to (B, Cmax, H).
        counts = torch.bincount(group_ids, minlength=n_groups)
        cmax = int(counts.max())
        pos = torch.arange(len(group_ids), device=h.device) - torch.repeat_interleave(
            torch.cumsum(counts, 0) - counts, counts)
        padded = h.new_zeros(n_groups, cmax, h.shape[-1])
        padded[group_ids, pos] = h
        valid = torch.zeros(n_groups, cmax, dtype=torch.bool, device=h.device)
        valid[group_ids, pos] = True
        if self.pooling == "class_attention":
            k, v = self.key(padded), self.value(padded)
            scores = torch.einsum("kh,bch->bkc", self.class_queries, k) / math.sqrt(k.shape[-1])
            scores = scores.masked_fill(~valid[:, None, :], float("-inf"))
            attn = scores.softmax(-1)                                                     # (B, K, C)
            pooled = torch.einsum("bkc,bch->bkh", attn, v)                                # (B, K, H)
            z = self.mlp(self.norm(pooled))
            logits = (z * self.out_weight).sum(-1) + self.out_bias
            return logits, attn
        mean = (padded * valid[..., None]).sum(1) / valid.sum(1, keepdim=True)
        z = self.mlp(self.norm(mean))
        return z @ self.out_weight.T + self.out_bias, None


class TimestralMultiLabel(nn.Module):
    def __init__(self, cfg: dict):
        super().__init__()
        import_timestral(cfg)
        from timestral.loading import load_model
        bb = load_model(resolve(cfg["backbone"]["path"]), device="cpu")
        assert bb.config.patch_size == PATCH, "data.PATCH must equal the backbone patch size"
        del bb.head                       # cut the quantile forecasting head
        self.backbone = bb
        self.cfg = cfg
        self.n_classes = len(cfg["labels"]["classes"])
        self.head = MultiLabelHead(bb.config.d_model, len(row_vocabulary(cfg)), self.n_classes, cfg["head"])
        self._configure_trainable()

    # ---------------------------------------------------------------- trainable parameters
    def _configure_trainable(self) -> None:
        bc = self.cfg["backbone"]
        mode = bc["mode"]
        bb = self.backbone
        if mode == "full":
            bb.requires_grad_(True)
        elif mode in ("frozen", "lora"):
            bb.requires_grad_(False)
            if mode == "lora":
                from timestral_ft.lora import apply_lora
                lc = bc["lora"]
                apply_lora(bb, rank=lc["rank"], alpha=lc["alpha"], dropout=lc["dropout"])
            n = int(bc.get("unfreeze_last_blocks", 0))
            if n:
                for layer in bb.transformer.layers[-n:]:
                    layer.requires_grad_(True)
                bb.transformer.out_norm.requires_grad_(True)
        else:
            raise ValueError(f"unknown backbone.mode {mode!r}")
        bb.representation.forecast_query.requires_grad_(bool(bc.get("train_query_token", True)) or mode == "full")
        bb.transformer.rope.rebuild_inv_freq()

    def parameter_groups(self, tc: dict) -> list[dict]:
        """Head, LoRA adapters and the query token use `learning_rate`; other backbone weights use
        `backbone_learning_rate`. No weight decay on norms, biases, embeddings and the query token."""
        groups = {}
        for name, p in self.named_parameters():
            if not p.requires_grad:
                continue
            fast = name.startswith("head.") or "lora_" in name or name.endswith("forecast_query")
            no_decay = p.ndim < 2 or "norm" in name or "embedding" in name or name.endswith("forecast_query")
            key = ("fast" if fast else "slow", no_decay)
            groups.setdefault(key, []).append(p)
        out = []
        for (speed, nd), params in groups.items():
            out.append(dict(params=params, lr=tc["learning_rate"] if speed == "fast" else tc["backbone_learning_rate"],
                            weight_decay=0.0 if nd else tc["weight_decay"], name=f"{speed}{'_nodecay' if nd else ''}"))
        return out

    def count_parameters(self) -> dict:
        total = sum(p.numel() for p in self.parameters())
        train = sum(p.numel() for p in self.parameters() if p.requires_grad)
        head = sum(p.numel() for p in self.head.parameters())
        return dict(total=total, trainable=train, head=head, trainable_backbone=train - head)

    # ---------------------------------------------------------------- forward
    def encode(self, values: Tensor, observed: Tensor, group_ids: Tensor) -> tuple[Tensor, Tensor]:
        """Backbone over packed rows. Returns the query-token output (R, D) and the mean of the
        valid context-token outputs (R, D)."""
        from timestral.layers import TwoStreamMask
        from timestral.masks import (build_forecast_positions, build_forecast_time_mask,
                                     build_two_stream_variate_mask, compute_enc_key_validity,
                                     group_first_observed_patch)
        bb, c = self.backbone, self.backbone.config
        rows, t = values.shape
        ll = t // c.patch_size
        if values.device.type == "mps":
            # The causal statistics use float64, which MPS lacks. The step has no gradient: run it on CPU.
            scaled = bb.scale(values.cpu(), observed.cpu())[0].to(values.device)
        else:
            scaled, _, _ = bb.scale(values, observed)
        x_enc = bb.representation(scaled, observed)
        x_dec = bb.representation.forecast_tokens(rows, 1)
        obs_patch = observed.unflatten(-1, (ll, c.patch_size)).any(-1)
        key_valid = compute_enc_key_validity(obs_patch, c.attend_missing_patches)
        time_mask = build_forecast_time_mask(ll, 1, key_valid, values.device)
        variate_mask = build_two_stream_variate_mask(group_ids, key_valid, 1)
        uniq, inverse = torch.unique(group_ids, return_inverse=True)
        first = group_first_observed_patch(obs_patch, inverse, uniq.numel())[inverse]
        positions = build_forecast_positions(ll, 1, first)
        x = torch.cat([x_enc, x_dec], 1)
        mask = TwoStreamMask(mask=time_mask, enc_len=ll) if c.split_context_horizon_attn else time_mask
        h = bb.transformer(x, mask, variate_mask, positions)
        q = h[:, ll]
        w = key_valid.to(h.dtype)[..., None]
        ctx = (h[:, :ll] * w).sum(1) / w.sum(1).clamp(min=1.0)
        return q, ctx

    def forward(self, batch: dict) -> tuple[Tensor, Tensor | None]:
        q, ctx = self.encode(batch["values"], batch["observed"], batch["group_ids"])
        return self.head(q, ctx, batch["row_ids"], batch["stats"], batch["group_ids"], batch["labels"].shape[0])


def masked_loss(logits: Tensor, labels: Tensor, mask: Tensor, lc: dict, pos_weight: Tensor | None) -> Tensor:
    """Mean over labelled (window, class) targets of BCE or focal loss."""
    y = labels
    if lc.get("label_smoothing", 0):
        s = lc["label_smoothing"]
        y = y * (1 - s) + 0.5 * s
    logits = logits.float()
    bce = nn.functional.binary_cross_entropy_with_logits(logits, y, pos_weight=pos_weight, reduction="none")
    if lc["type"] == "focal":
        p = torch.sigmoid(logits)
        pt = torch.where(labels > 0.5, p, 1 - p)
        bce = bce * (1 - pt).pow(lc["focal_gamma"])
    elif lc["type"] != "bce":
        raise ValueError(f"unknown loss {lc['type']!r}")
    return (bce * mask).sum() / mask.sum().clamp(min=1.0)
