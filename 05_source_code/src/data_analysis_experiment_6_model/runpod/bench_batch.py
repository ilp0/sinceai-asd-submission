"""On the pod: windows/s for inference and training at several batch sizes (no optimizer state kept)."""
import sys, time, json
sys.path.insert(0, ".")
import torch
from mlhead.config import load_config
from mlhead.data import WindowDataset, collate
from mlhead.model import masked_loss
from mlhead.train import build, to_device
cfg = load_config(sys.argv[1])
model, dev = build(cfg)
ds = WindowDataset(cfg, "val", 60)
items = [ds[i] for i in range(0, 256 * 40, 40)]
for bs in (16, 32, 64, 128):
    batches = [to_device(collate(items[i:i + bs]), dev) for i in range(0, len(items), bs)][:8]
    model.eval()
    with torch.no_grad():
        model(batches[0]); torch.cuda.synchronize(); t = time.time()
        for b in batches: model(b)
        torch.cuda.synchronize(); inf = len(batches) * bs / (time.time() - t)
    model.train()
    model(batches[0])[0].sum().backward(); torch.cuda.synchronize(); t = time.time()
    for b in batches:
        logits, _ = model(b); masked_loss(logits, b["labels"], b["label_mask"], cfg["loss"], None).backward()
    torch.cuda.synchronize(); tr = len(batches) * bs / (time.time() - t)
    model.zero_grad(set_to_none=True)
    print(json.dumps(dict(batch=bs, infer_windows_s=round(inf), train_windows_s=round(tr),
                          mem_gb=round(torch.cuda.max_memory_allocated() / 1e9, 1))), flush=True)
t = time.time(); n = 2000
for i in range(n): ds[i * 7 % len(ds)]
print(json.dumps(dict(cpu_getitem_ms=round((time.time() - t) / n * 1000, 2))))
