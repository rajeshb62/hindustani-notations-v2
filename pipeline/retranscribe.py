#!/usr/bin/env python3
"""Rebuild performance.json from its saved work/f0.vad.csv (no Demucs/CREPE rerun).

    python3 -m pipeline.retranscribe                      # every performance in data/
    python3 -m pipeline.retranscribe <slug> ...
    python3 -m pipeline.retranscribe <slug> --sa 97.4     # re-pin a wrong Sa
    python3 -m pipeline.retranscribe --no-calibrate       # pinned Sa + just table

Sa is always re-derived from the original pin (not the last refined value),
so running this repeatedly gives the same result.
"""

from __future__ import annotations

import argparse
import json

from .calibrate import calibrated_notes
from . import corrections
from .raga import RAGAS
from .run import DATA, write_catalog
from .transcribe import (
    absorb_passing,
    build_contour,
    error_spans,
    frames_to_notes,
    load_frames,
    prepare_frames,
    singer_range,
    write_performance,
)


def retranscribe(
    slug: str, sa_pin: float | None = None, calibrate: bool = True, raga: str | None = None
) -> dict:
    dest = DATA / slug
    perf = json.loads((dest / "performance.json").read_text())
    sa_meta = perf.get("sa_estimate") or {"sa_source": perf.get("sa_source")}
    if sa_pin:
        sa_meta = {**sa_meta, "sa_hz": float(sa_pin), "sa_source": "user-pin"}
    base_sa = float(sa_meta.get("sa_hz") or perf["sa_hz"])
    corr = corrections.load(dest)
    frames = corrections.drop_no_voice(prepare_frames(load_frames(dest / "work" / "f0.vad.csv"), base_sa), corr)
    if calibrate:
        notes, sa_hz, calibration = calibrated_notes(frames, base_sa)
    else:
        notes, sa_hz, calibration = frames_to_notes(frames, base_sa, prepared=True), base_sa, None
    notes = absorb_passing(corrections.flag_listener_notes(notes, corr), raga or perf.get("raga"))
    write_performance(
        notes,
        dest / "performance.json",
        title=perf["title"],
        audio_rel=perf["audio"],
        sa_hz=sa_hz,
        sa_meta=sa_meta,
        extra=perf.get("pipeline"),
        contour=build_contour(frames, sa_hz, singer_range(notes, sa_hz), error_spans(notes, sa_hz)),
        calibration=calibration,
        raga=raga or perf.get("raga"),
    )
    return {"slug": slug, "sa_hz": round(sa_hz, 3), "before": perf["stats"]["note_count"], "after": len(notes)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("slugs", nargs="*")
    p.add_argument("--sa", type=float, default=None, help="Pin Sa in Hz (needs exactly one slug)")
    p.add_argument("--raga", choices=sorted(RAGAS), default=None,
                   help="Record the performance's raga and report fit (needs one slug)")
    p.add_argument("--no-calibrate", action="store_true",
                   help="Keep the pinned Sa and the just table (no per-performance tuning)")
    args = p.parse_args()
    slugs = args.slugs or [
        d.name for d in sorted(DATA.iterdir()) if (d / "work" / "f0.vad.csv").exists()
    ]
    if (args.sa or args.raga) and len(slugs) != 1:
        p.error("--sa/--raga apply to one performance; name its slug")
    for slug in slugs:
        print(retranscribe(slug, args.sa, calibrate=not args.no_calibrate, raga=args.raga))
    write_catalog()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
