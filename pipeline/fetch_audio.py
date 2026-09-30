#!/usr/bin/env python3
"""Download the recordings from the Internet Archive (NCPA collection).

Audio is not kept in git. Each performance's recording is fetched to the path
its performance.json expects and checked by size:

    python3 -m pipeline.fetch_audio            # every performance
    python3 -m pipeline.fetch_audio <slug> ...
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"

# slug: (archive.org identifier, file in the item, local name, size in bytes)
SOURCES: dict[str, tuple[str, str, str, int]] = {
    "iccr-1854-side-b": (
        "dni.ncaa.ICCR-1854-AC",  # Vocal Recital by Pandit Raja Kale
        "ICCR-1854-AC_SIDE_B.mp3", "ICCR-1854-AC_SIDE_B.mp3", 23457792,
    ),
    "pt-jasraj-side-a": (
        "dni.ncaa.SF-SFC000755-AC",  # Hindustani Vocal Recital by Pandit Jasraj
        "SF-SFC000755-AC_SIDE_A.mp3", "source_audio.mp3", 42998784,
    ),
    "pt-jasraj-side-b": (
        "dni.ncaa.SF-SFC000755-AC",
        "SF-SFC000755-AC_SIDE_B.mp3", "SF-SFC000755-AC_SIDE_B.mp3", 43328640,
    ),
    "todi-paluskar-side-a": (
        "dni.ncaa.SKSS-T206-AC",  # A Collection of Bandishes in Raga Todi (Vol. I)
        "SKSS-T206-AC_SIDE_A.mp3", "SKSS-T206-AC_SIDE_A.mp3", 27480576,
    ),
    "todi-ghulam-ali": (
        "dni.ncaa.SKSS-T206-AC",
        "SKSS-T206-AC_SIDE_B.mp3", "SKSS-T206-AC_SIDE_B.mp3", 28987392,
    ),
}


def fetch(slug: str) -> str:
    ident, name, local, size = SOURCES[slug]
    dest = DATA / slug / local
    if dest.exists() and dest.stat().st_size == size:
        return f"{slug}: already present"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_symlink():
        dest.unlink()
    url = f"https://archive.org/download/{ident}/{name}"
    tmp = dest.with_suffix(".part")
    print(f"{slug}: downloading {url}", flush=True)
    urllib.request.urlretrieve(url, tmp)
    got = tmp.stat().st_size
    if got != size:
        tmp.unlink()
        raise RuntimeError(f"{slug}: expected {size} bytes, got {got}")
    tmp.rename(dest)
    return f"{slug}: ok ({size / 1e6:.1f} MB)"


def main() -> int:
    for slug in sys.argv[1:] or list(SOURCES):
        print(fetch(slug))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
