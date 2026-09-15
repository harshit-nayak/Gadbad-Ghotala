"""Download the Silero VAD model (~2.2 MB) used to isolate far-party speech.

    python scripts/fetch_silero.py

Without it the backend still runs, but falls back to the energy VAD, which is
noticeably weaker when the other party is in a noisy room -- and the far track
carries *their* room, since it is a digital tap of what they transmitted.

Stdlib only, so this works in the backend venv before anything else installs.
"""

import sys
import urllib.error
import urllib.request
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
DEFAULT_DEST = BACKEND_DIR / "models" / "silero_vad.onnx"

# Same file, two hosts -- the second is a mirror in case the first is blocked.
URLS = [
    "https://github.com/snakers4/silero-vad/raw/master/src/silero_vad/data/silero_vad.onnx",
    "https://raw.githubusercontent.com/snakers4/silero-vad/master/src/silero_vad/data/silero_vad.onnx",
]

MIN_BYTES = 500_000   # a truncated download or an HTML error page is much smaller
MAX_BYTES = 20_000_000


def fetch(dest: Path = DEFAULT_DEST) -> int:
    if dest.is_file() and dest.stat().st_size > MIN_BYTES:
        print(f"Already present: {dest} ({dest.stat().st_size:,} bytes)")
        return 0

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".onnx.part")

    for url in URLS:
        print(f"Downloading {url} ...")
        try:
            with urllib.request.urlopen(url, timeout=60) as response:
                data = response.read()
        except (urllib.error.URLError, TimeoutError, OSError) as e:
            print(f"  failed: {e}")
            continue

        if not MIN_BYTES < len(data) < MAX_BYTES:
            print(f"  unexpected size ({len(data):,} bytes); skipping this source")
            continue

        # Write to a temp name first so an interrupted download can never leave
        # a half-file that later looks present and valid.
        tmp.write_bytes(data)
        tmp.replace(dest)
        print(f"Saved {dest} ({len(data):,} bytes)")
        print("Restart the backend; /health should now report vad_backend: silero")
        return 0

    print(
        "\nCould not download the Silero VAD model.\n"
        "The backend will still run using the energy VAD fallback.\n"
        f"To install it by hand, save the file from one of:\n"
        + "".join(f"  {u}\n" for u in URLS)
        + f"to: {dest}\n"
        "(or point SILERO_VAD_PATH at wherever you put it)",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    dest = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else DEFAULT_DEST
    raise SystemExit(fetch(dest))
