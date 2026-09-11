# XLSR-Mamba weights — base + Indic fine-tune

Two full, self-contained checkpoints, same architecture (`Model(emb_size=144, num_encoders=12)`
in `evaluate_model.py`), 319.3M params / 1.27GB each:

| File | What it is |
|---|---|
| `model_base.safetensors` | The original, unmodified XLSR-Mamba checkpoint (ASVspoof5 EER 2.77%). |
| `model_indic_ft.safetensors` | Same backbone, head fine-tuned on Hindi/Bengali/Tamil deepfakes (Indic test EER 0.31%, ASVspoof5 EER 21.28% — see `XLSR-Mamba-Field-Report.pdf`). |

They differ in exactly 129 of 565 tensors (the classifier head only) — see
`xlsr-mamba-indic-ft-lite.zip` for a 7.2MB file with just that head, if you already
have `model_base.safetensors` and don't need a second full copy.

## Load either one

```python
from evaluate_model import Model
from safetensors.torch import load_file

model = Model(emb_size=144, num_encoders=12)
model.load_state_dict(load_file("model_base.safetensors"), strict=False)   # or model_indic_ft.safetensors
model.eval()
```
