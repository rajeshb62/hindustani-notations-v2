"""Vocal / accompaniment split via Demucs when available."""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def isolate(audio: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    vocals = out_dir / "vocals.wav"
    other = out_dir / "no_vocals.wav"
    if vocals.exists() and other.exists():
        return {"vocals": str(vocals), "no_vocals": str(other), "skipped": True}

    cmd = [
        sys.executable,
        "-m",
        "demucs",
        "--two-stems=vocals",
        "-n",
        "htdemucs",
        "-o",
        str(out_dir / "demucs"),
        str(audio),
    ]
    try:
        subprocess.run(cmd, check=True)
    except (subprocess.CalledProcessError, FileNotFoundError):
        # Fall back: treat the mix as vocals. Sa detection will use the mix too.
        shutil.copy2(audio, vocals)
        shutil.copy2(audio, other)
        return {
            "vocals": str(vocals),
            "no_vocals": str(other),
            "skipped": False,
            "demucs": False,
            "note": "Demucs unavailable; using mix for both stems.",
        }

    stem_root = out_dir / "demucs" / "htdemucs" / audio.stem
    src_v = stem_root / "vocals.wav"
    src_n = stem_root / "no_vocals.wav"
    if src_v.exists():
        shutil.copy2(src_v, vocals)
    if src_n.exists():
        shutil.copy2(src_n, other)
    return {"vocals": str(vocals), "no_vocals": str(other), "demucs": True, "skipped": False}
