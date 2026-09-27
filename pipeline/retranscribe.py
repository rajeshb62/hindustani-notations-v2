#!/usr/bin/env python3
"""Rebuild performance.json from its saved work/f0.vad.csv (no Demucs/CREPE rerun).

    python3 -m pipeline.retranscribe                      # every performance in data/
    python3 -m pipeline.retranscribe <slug> ...
    python3 -m pipeline.retranscribe <slug> --sa 97.4     # re-pin a wrong Sa
"""

from __future__ import annotations

import argparse
import json

from .run import DATA, write_catalog
from .transcribe import (
    build_contour,
    frames_to_notes,
    load_frames,
    prepare_frames,
    singer_range,
    write_performance,
)


def retranscribe(slug: str, sa_pin: float | None = None) -> dict:
    dest = DATA / slug
    perf = json.loads((dest / "performance.json").read_text())
    sa_hz = float(sa_pin or perf["sa_hz"])
    frames = prepare_frames(load_frames(dest / "work" / "f0.vad.csv"), sa_hz)
    notes = frames_to_notes(frames, sa_hz, prepared=True)
    sa_meta = perf.get("sa_estimate") or {"sa_source": perf.get("sa_source")}
    if sa_pin:
        sa_meta = {**sa_meta, "sa_hz": sa_hz, "sa_source": "user-pin"}
    write_performance(
        notes,
        dest / "performance.json",
        title=perf["title"],
        audio_rel=perf["audio"],
        sa_hz=sa_hz,
        sa_meta=sa_meta,
        extra=perf.get("pipeline"),
        contour=build_contour(frames, sa_hz, singer_range(notes, sa_hz)),
    )
    return {"slug": slug, "sa_hz": sa_hz, "before": perf["stats"]["note_count"], "after": len(notes)}


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("slugs", nargs="*")
    p.add_argument("--sa", type=float, default=None, help="Pin Sa in Hz (needs exactly one slug)")
    args = p.parse_args()
    slugs = args.slugs or [
        d.name for d in sorted(DATA.iterdir()) if (d / "work" / "f0.vad.csv").exists()
    ]
    if args.sa and len(slugs) != 1:
        p.error("--sa applies to one performance; name its slug")
    for slug in slugs:
        print(retranscribe(slug, args.sa))
    write_catalog()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
