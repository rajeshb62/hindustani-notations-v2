"""Vocal / accompaniment split.

Default: MelBand RoFormer "bleedless" (audio-separator), overlap 2. On the
Desh clip with listener-labelled stretches it put the voice at -25 dB, the
no-voice stretch at digital silence and the harmonium at -88 dB in the voice
stem. htdemucs, the previous default, did the opposite there: singing -74 dB
(lost to the accompaniment) and harmonium -30 dB (leaked into the voice).
Overlap 2 instead of the default 8 is ~3x faster with the same separation
(voice stems differ by -33 dB). Falls back to htdemucs, then to the mix.

work/separation.json records which model made the stems, so a cached stem
from an older model is replaced rather than reused.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

ROFORMER = "mel_band_roformer_kim_ft2_bleedless_unwa.ckpt"
ROFORMER_OVERLAP = 2


def _roformer(audio: Path, out_dir: Path, vocals: Path, other: Path) -> None:
    tmp = out_dir / "roformer"
    shutil.rmtree(tmp, ignore_errors=True)
    tmp.mkdir()
    exe = Path(sys.executable).with_name("audio-separator")
    subprocess.run(
        [str(exe), str(audio), "-m", ROFORMER, "--mdxc_overlap", str(ROFORMER_OVERLAP),
         "--output_dir", str(tmp), "--output_format", "WAV"],
        check=True,
    )
    v = next(tmp.glob("*(vocals)*.wav"))
    o = next(tmp.glob("*(other)*.wav"))
    shutil.move(v, vocals)
    shutil.move(o, other)
    shutil.rmtree(tmp, ignore_errors=True)


def _demucs(audio: Path, out_dir: Path, vocals: Path, other: Path) -> None:
    cmd = [sys.executable, "-m", "demucs", "--two-stems=vocals", "-n", "htdemucs",
           "-o", str(out_dir / "demucs"), str(audio)]
    try:
        subprocess.run(cmd, check=True)
    except subprocess.CalledProcessError:
        # Apple MPS rejects htdemucs on long tracks ("Output channels >
        # 65536 not supported"); CPU is slower but works.
        print("demucs failed on the default device; retrying on CPU", file=sys.stderr)
        subprocess.run(cmd[:3] + ["-d", "cpu"] + cmd[3:], check=True)
    stem_root = out_dir / "demucs" / "htdemucs" / audio.stem
    shutil.copy2(stem_root / "vocals.wav", vocals)
    shutil.copy2(stem_root / "no_vocals.wav", other)


def isolate(audio: Path, out_dir: Path) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    vocals = out_dir / "vocals.wav"
    other = out_dir / "no_vocals.wav"
    marker = out_dir / "separation.json"
    want = f"{ROFORMER}@overlap{ROFORMER_OVERLAP}"
    if vocals.exists() and other.exists() and marker.exists():
        done = json.loads(marker.read_text())
        if done.get("model") == want:
            return {"vocals": str(vocals), "no_vocals": str(other), "skipped": True, **done}

    for name, fn, model in (("roformer", _roformer, want), ("demucs", _demucs, "htdemucs")):
        try:
            fn(audio, out_dir, vocals, other)
        except (subprocess.CalledProcessError, FileNotFoundError, StopIteration) as exc:
            print(f"{name} separation failed: {exc}", file=sys.stderr)
            continue
        info = {"model": model, "separator": name}
        marker.write_text(json.dumps(info))
        return {"vocals": str(vocals), "no_vocals": str(other), "skipped": False,
                "demucs": name == "demucs", **info}

    # Last resort: treat the mix as vocals. Sa detection will use the mix too.
    shutil.copy2(audio, vocals)
    shutil.copy2(audio, other)
    marker.write_text(json.dumps({"model": "mix", "separator": "none"}))
    return {"vocals": str(vocals), "no_vocals": str(other), "skipped": False,
            "separator": "none", "note": "No separator worked; using the mix for both stems."}
