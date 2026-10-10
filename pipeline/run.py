#!/usr/bin/env python3
"""End-to-end: audio → performance.json for the player."""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

from .calibrate import calibrated_notes
from . import corrections
from .detect_sa import estimate_sa, write_estimate
from .raga import RAGAS
from .extract_f0 import extract_f0
from .isolate import isolate
from .transcribe import (
    absorb_passing,
    absorb_wavers,
    build_contour,
    error_spans,
    frames_to_notes,
    load_frames,
    prepare_frames,
    singer_range,
    write_performance,
)
from .vad_filter import filter_f0

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
PLAYER = ROOT / "player"


def slugify(title: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "-", title.strip().lower()).strip("-")
    return s or "performance"


def write_catalog() -> None:
    items = []
    for d in sorted(DATA.iterdir() if DATA.exists() else []):
        perf = d / "performance.json"
        if not perf.exists() or (d / "hidden.json").exists():  # hidden.json: kept, not listed
            continue
        meta = json.loads(perf.read_text())
        items.append(
            {
                "id": d.name,
                "title": meta.get("title", d.name),
                "path": f"./data/{d.name}/performance.json",
                "sa_hz": meta.get("sa_hz"),
                "notes": (meta.get("stats") or {}).get("note_count"),
            }
        )
    (PLAYER / "catalog.json").write_text(json.dumps(items, indent=2))


def run(
    audio: Path,
    title: str,
    sa_pin: float | None,
    skip_demucs: bool,
    f0_csv: Path | None,
    skip_vad: bool = False,
    calibrate: bool = True,
    raga: str | None = None,
    slug: str | None = None,
) -> Path:
    slug = slug or slugify(title)
    dest = DATA / slug
    dest.mkdir(parents=True, exist_ok=True)
    audio = audio.resolve()
    dest_audio = dest / audio.name
    if dest_audio.resolve() != audio:
        if not dest_audio.exists():
            try:
                dest_audio.symlink_to(audio)
            except OSError:
                shutil.copy2(audio, dest_audio)

    work = dest / "work"
    work.mkdir(exist_ok=True)

    if skip_demucs:
        vocals = dest_audio
        other = dest_audio
        iso = {"demucs": False, "skipped": True, "vocals": str(vocals)}
    else:
        iso = isolate(dest_audio, work)
        vocals = Path(iso["vocals"])
        other = Path(iso["no_vocals"])

    if f0_csv:
        primary_f0 = Path(f0_csv)
        f0_meta = {"primary_csv": str(primary_f0), "trackers": ["provided"]}
    else:
        f0_meta = extract_f0(vocals, work)
        primary_f0 = Path(f0_meta["primary_csv"])

    if sa_pin:
        sa_meta = {
            "sa_hz": float(sa_pin),
            "sa_source": "user-pin",
            "tanpura_candidates": [],
            "vocal_tonic_candidates": [],
        }
    else:
        sa_meta = estimate_sa(
            accompaniment_wav=other if other.exists() else None,
            mix_wav=dest_audio,
            f0_csv=primary_f0,
            raga=raga,
        )
    write_estimate(sa_meta, dest / "sa_estimate.json")
    sa_hz = float(sa_meta["sa_hz"] or 130.81)

    vad_csv = work / "f0.vad.csv"
    if skip_vad:
        shutil.copy2(primary_f0, vad_csv)
        vad_meta = {"skipped": True, "out": str(vad_csv)}
    else:
        vad_meta = filter_f0(primary_f0, vocals, vad_csv, sa_hz=sa_hz)
    corr = corrections.load(dest)
    frames = corrections.drop_no_voice(prepare_frames(load_frames(vad_csv), sa_hz), corr)
    if calibrate:
        notes, sa_hz, calibration = calibrated_notes(frames, sa_hz)
    else:
        notes, calibration = frames_to_notes(frames, sa_hz, prepared=True), None
    notes = absorb_passing(absorb_wavers(corrections.flag_listener_notes(notes, corr), raga), raga)

    write_performance(
        notes,
        dest / "performance.json",
        title=title,
        audio_rel=dest_audio.name,
        sa_hz=sa_hz,
        sa_meta=sa_meta,
        extra={"isolate": iso, "f0": f0_meta, "vad": vad_meta},
        contour=build_contour(frames, sa_hz, singer_range(notes, sa_hz), error_spans(notes, sa_hz)),
        calibration=calibration,
        raga=raga,
    )
    write_catalog()
    return dest / "performance.json"


def main() -> int:
    p = argparse.ArgumentParser(description="Transcribe a Hindustani vocal recording to sargam.")
    p.add_argument("audio", type=Path)
    p.add_argument("--title", default=None)
    p.add_argument("--sa", type=float, default=None, help="Pin Sa in Hz")
    p.add_argument("--skip-demucs", action="store_true")
    p.add_argument("--f0-csv", type=Path, default=None)
    p.add_argument("--skip-vad", action="store_true")
    p.add_argument("--no-calibrate", action="store_true",
                   help="Keep the pinned Sa and the just table (no per-performance tuning)")
    p.add_argument("--slug", default=None,
                   help="data/ folder name (default: from the title)")
    p.add_argument("--raga", choices=sorted(RAGAS), default=None,
                   help="Use the raga's scale to choose Sa among tanpura peaks, and report fit")
    args = p.parse_args()
    title = args.title or args.audio.stem
    out = run(args.audio, title, args.sa, args.skip_demucs, args.f0_csv, args.skip_vad,
              calibrate=not args.no_calibrate, raga=args.raga, slug=args.slug)
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
