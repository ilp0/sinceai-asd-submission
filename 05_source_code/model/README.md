# Trained weights of the submitted model

| File | Content |
|---|---|
| `rp3-3h-r32-v1_step11500_trained.safetensors` | The trained parameters of the submitted model: run `rp3-3h-r32-v1`, checkpoint `checkpoint_last_step11500` (step 11500). 73 tensors, 1 419 213 float32 values, 5.7 MB. |
| `rebuild_checkpoint.py` | Makes the full checkpoint from the public Timestral-28M weights and this file. |
| `LICENSE` | The Timestral-28M licence (Modified MIT License, attribution notice "2026 - Mistral AI"). It applies to these weights, because they are a derivative of Timestral-28M. |

## What the file contains

Only the parameters that training changed. All other weights of the model are the unchanged Timestral-28M weights.

| Part | Values |
|---|---:|
| LoRA adapters (rank 32, alpha 64) on the attention QKV and output projections of the 12 blocks | 1 105 920 |
| Multi-label fault head (13 fault types, class attention pooling) | 312 909 |
| `forecast_query` token of the backbone | 384 |
| **Total trained** | **1 419 213** |
| Full model (backbone with LoRA and head) | 27 359 949 |

The file metadata records the run, the step, the config (`configs/rp3-3h-r32.yaml`) and the SHA-256 of the base weights that training used.

## Rebuild the full checkpoint

1. Put the Timestral-28M weights (`config.json`, `model.safetensors`) from `mistralai/Timestral-28M`, revision `49b26409ac87b5935539a5d8ffe7f397b720db47`, in `../src/data_analysis_experiment_2_lora/base_model/`.
2. Put the `timestral` package (github.com/mistralai/timestral) and the `timestral_ft` package (Timestral-ft, LoRA code) in `../src/data_analysis_experiment_2_lora/vendor/`.
3. Run the script:

```bash
python rebuild_checkpoint.py    # -> ../src/data_analysis_experiment_6_model/runs/rp3-3h-r32-v1/checkpoint_last_step11500.pt
```

The script checks that the base weights have the SHA-256 of training (`dfc83c62…b2015d`) and that the file has exactly the trainable parameters of the model. The output has the format that `analysis/predict_test.py` and `optimize/predict_test_fine.py` read. Then follow "Reproduce the test predictions" in `../README.md`.

Check of 8 November 2026: the rebuilt checkpoint is identical to the original training checkpoint (176 of 176 tensors equal, largest difference 0.0).

## Checksums (SHA-256)

```
7c6ce9bd5889419f9c7609a3496e594c785cf637b1bf8354cf8cc3790e692ae5  rp3-3h-r32-v1_step11500_trained.safetensors
dfc83c6220937ce5fc6687b35a4df94cd25e28a2cfe6fb92a23dad6301b2015d  Timestral-28M model.safetensors (base, not in this package)
```

## Licence

The weights are a derivative of Timestral-28M and stay under its Modified MIT License (`LICENSE`). Condition 1 of the licence: include the attribution and permission notice in all copies. Condition 2: the licence does not apply to a company whose monthly revenue is more than USD 20 million; such a company needs a commercial licence from Mistral AI.
