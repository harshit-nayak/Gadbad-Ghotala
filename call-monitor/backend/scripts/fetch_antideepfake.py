"""Download the AntiDeepfake MMS-300M weights (~1.27 GB) for the second detector.

    python scripts/fetch_antideepfake.py

Source: https://huggingface.co/nii-yamagishilab/mms-300m-anti-deepfake
Licence: CC BY-NC-SA 4.0 -- research and educational use only.

Uses huggingface_hub when installed (resumable), otherwise plain HTTPS.
Downloads to a .part file first, so an interrupted download never leaves a
truncated file that later looks complete.
"""

import sys
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEST = BACKEND_DIR / "models" / "mms-300m-anti-deepfake"
REPO = "nii-yamagishilab/mms-300m-anti-deepfake"
FILES = ("config.json", "model.safetensors")
MIN_WEIGHTS_BYTES = 1_000_000_000


def _via_hub(dest: Path) -> None:
    from huggingface_hub import hf_hub_download

    for name in FILES:
        hf_hub_download(REPO, name, local_dir=str(dest))


def _via_https(dest: Path) -> None:
    for name in FILES:
        target = dest / name
        part = target.with_suffix(target.suffix + ".part")
        url = f"https://huggingface.co/{REPO}/resolve/main/{name}"
        print(f"downloading {url}")
        with urllib.request.urlopen(url, timeout=120) as response, part.open("wb") as out:
            while chunk := response.read(1 << 20):
                out.write(chunk)
        part.replace(target)


def main() -> int:
    weights = DEST / "model.safetensors"
    if weights.is_file() and weights.stat().st_size > MIN_WEIGHTS_BYTES:
        print(f"Already present: {weights} ({weights.stat().st_size / 1e9:.2f} GB)")
        return 0
    DEST.mkdir(parents=True, exist_ok=True)
    try:
        _via_hub(DEST)
    except ImportError:
        _via_https(DEST)
    except Exception as e:  # noqa: BLE001
        print(f"huggingface_hub download failed ({e}); retrying over plain HTTPS")
        _via_https(DEST)

    if not (weights.is_file() and weights.stat().st_size > MIN_WEIGHTS_BYTES):
        print(f"Download incomplete: {weights}", file=sys.stderr)
        return 1
    print(f"Saved {weights} ({weights.stat().st_size / 1e9:.2f} GB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
