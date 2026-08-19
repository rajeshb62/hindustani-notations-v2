"""Build a first performance from the older project's CREPE+VAD track.

This does not copy that app. It re-quantizes the existing f0 with just intonation
and writes Hz-first performance.json so the new player is immediately listenable.
"""

from __future__ import annotations

import sys
from pathlib import Path

LEGACY = Path("/Users/rajeshbhat/claudecode/hindustani notations")
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from pipeline.run import run  # noqa: E402


def main() -> int:
    audio = LEGACY / "ICCR-1854-AC_SIDE_B.mp3"
    f0 = LEGACY / "vocals.f0.vad.csv"
    if not audio.exists():
        print("Legacy audio not found:", audio)
        return 1
    if not f0.exists():
        print("Legacy f0 not found:", f0)
        return 1
    out = run(
        audio,
        title="ICCR-1854 Side B",
        sa_pin=96.97,
        skip_demucs=True,
        f0_csv=f0,
        skip_vad=True,
    )
    print("Bootstrapped", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
