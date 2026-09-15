"""Download the XLSR-Mamba base checkpoint (~1.28 GB) for the xlsr-mamba detector.

    python scripts/fetch_xlsr_mamba.py

Two files make the Indic model, both in backend/models/xlsr-mamba/:

  model_base.safetensors            public -- https://huggingface.co/AustinXiao/XLSR-Mamba-LA
                                    (MIT). This script downloads it.
  conformer_head_only.safetensors   the Indic fine-tuned head (7.2 MB). It lives in a
                                    PRIVATE repo, so it can't be fetched anonymously:
                                    harshit-nayak/Gadbad-Ghotala, branch
                                    XLSR_MAMBA_FINETUNED, release/xlsr-mamba-indic-ft-lite.zip

Downloads to a .part file first, so an interrupted download never leaves a
truncated file that later looks complete.
"""

import sys
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEST = BACKEND_DIR / "models" / "xlsr-mamba"
BASE_URL = "https://huggingface.co/AustinXiao/XLSR-Mamba-LA/resolve/main/model.safetensors"
MIN_BASE_BYTES = 1_000_000_000


def main() -> int:
    DEST.mkdir(parents=True, exist_ok=True)
    base = DEST / "model_base.safetensors"
    if base.is_file() and base.stat().st_size > MIN_BASE_BYTES:
        print(f"Already present: {base} ({base.stat().st_size / 1e9:.2f} GB)")
    else:
        part = base.with_suffix(".safetensors.part")
        print(f"downloading {BASE_URL}")
        with urllib.request.urlopen(BASE_URL, timeout=120) as response, part.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        part.replace(base)
        print(f"Saved {base} ({base.stat().st_size / 1e9:.2f} GB)")

    head = DEST / "conformer_head_only.safetensors"
    if not head.is_file():
        print(
            f"\nMISSING: {head}\n"
            "The Indic head is in a private repo and cannot be downloaded here. Copy\n"
            "conformer_head_only.safetensors out of release/xlsr-mamba-indic-ft-lite.zip on\n"
            "branch XLSR_MAMBA_FINETUNED of harshit-nayak/Gadbad-Ghotala into that folder.\n"
            "Without it, DETECTORS can still use 'xlsr-mamba-base' (the un-fine-tuned model).",
            file=sys.stderr,
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
