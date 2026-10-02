import math
import unittest

from pipeline.transcribe import Frame, build_contour, frames_to_notes

SA = 96.97


def hz(cents: float) -> float:
    return SA * 2 ** (cents / 1200.0)


def run(cents_list, t0=0.0, step=0.01):
    return [Frame(t0 + i * step, hz(c), 0.9) for i, c in enumerate(cents_list)]


class VoiceGate(unittest.TestCase):
    def test_keeps_sung_frames_and_drops_silent_residue(self):
        import csv, tempfile
        import numpy as np, soundfile as sf
        from pathlib import Path
        from pipeline.vad_filter import filter_f0
        sr = 16000
        t = np.arange(0, 3.0, 1 / sr)
        # 1 s near-silent residue, 1 s "singing", 1 s near-silent residue.
        y = np.where((t >= 1) & (t < 2), 0.3, 0.3 * 10 ** (-70 / 20)) * np.sin(2 * np.pi * 220 * t)
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            sf.write(d / "vocals.wav", y, sr)
            with (d / "f0.csv").open("w", newline="") as f:
                w = csv.writer(f); w.writerow(["time", "frequency", "confidence"])
                for k in range(300):
                    w.writerow([f"{k * 0.01:.2f}", "220.0", "0.9"])
            meta = filter_f0(d / "f0.csv", d / "vocals.wav", d / "out.csv")
            kept = [float(r["time"]) for r in csv.DictReader((d / "out.csv").open())]
        self.assertTrue(all(0.85 <= k <= 2.15 for k in kept), (min(kept), max(kept)))
        self.assertGreater(meta["kept"], 95)


class Grouping(unittest.TestCase):
    def test_short_ornament_survives(self):
        # 300 ms Sa, 20 ms kan on Re, 300 ms Sa
        frames = run([0] * 30 + [204] * 2 + [0] * 30)
        notes = frames_to_notes(frames, SA)
        self.assertEqual([n.label for n in notes], ["S", "R", "S"])

    def test_single_frame_flicker_inside_held_note_is_bridged(self):
        # Unsmoothed: a 10 ms Re between two Sa groups merges into one Sa.
        frames = run([0] * 30 + [204] + [0] * 30)
        notes = frames_to_notes(frames, SA, prepared=True)
        self.assertEqual([n.label for n in notes], ["S"])
        self.assertAlmostEqual(notes[0].dur, 0.61, places=2)

    def test_octave_jump_is_not_merged(self):
        frames = run([0] * 30 + [1200] * 30)
        notes = frames_to_notes(frames, SA)
        self.assertEqual([n.label for n in notes], ["S", "S'"])

    def test_single_frame_spike_is_removed(self):
        frames = run([0] * 20 + [386] + [0] * 20)
        notes = frames_to_notes(frames, SA)
        self.assertEqual([n.label for n in notes], ["S"])


class Range(unittest.TestCase):
    def test_octave_jump_above_singers_range_is_flagged(self):
        # Minutes in madhya/taar; then held S' jumps to S'' (2x) as bleed does.
        body = []
        for k in range(60):  # ~54 s, so the 0.3 s S'' is a rare excursion (<1%)
            body += [0] * 30 + [702] * 30 + [1200] * 30
        frames = run(body + [1200] * 30 + [2400] * 30 + [1200] * 30)
        # prepared=True: skip the octave deglitcher, which already folds short
        # synthetic jumps; the real 25:33 excursions were long enough to survive it.
        notes = frames_to_notes(frames, SA, prepared=True)
        self.assertEqual([n.flag for n in notes if n.label == "S''"], ["range"])
        self.assertTrue(all(n.flag is None for n in notes if n.label != "S''"))

    def test_contour_drops_out_of_range_frames(self):
        c = build_contour(run([1200, 1200, 2400, 1200]), SA, cents_range=(-500, 2000))
        self.assertEqual(c["runs"], [[0.0, [1200, 1200]], [0.03, [1200]]])


class OctaveFlips(unittest.TestCase):
    def test_flicker_keeps_the_octave_that_fits_the_phrase(self):
        # P, then M / M' alternating every 20-30 ms, then P (Jasraj 21:46).
        frames = run([702] * 10 + [498] * 2 + [1698] * 2 + [498] * 3 + [1698] * 3 + [702] * 10)
        notes = frames_to_notes(frames, SA, prepared=True)
        self.assertEqual([(n.label, n.flag) for n in notes if n.swara == "M"],
                         [("M", None), ("M'", "octave"), ("M", None), ("M'", "octave")])

    def test_curve_drops_flip_fragments_but_keeps_the_real_line(self):
        from pipeline.transcribe import error_spans
        frames = run([702] * 10 + [498] * 2 + [1698] * 2 + [498] * 3 + [1698] * 3 + [702] * 10)
        notes = frames_to_notes(frames, SA, prepared=True)
        c = build_contour(frames, SA, drop=error_spans(notes, SA))
        kept = [x for _, run_ in c["runs"] for x in run_]
        self.assertNotIn(1698, kept)
        self.assertEqual(kept.count(498), 5)

    def test_held_octave_leap_is_not_a_flip(self):
        frames = run([0] * 30 + [1200] * 30 + [0] * 30)
        notes = frames_to_notes(frames, SA, prepared=True)
        self.assertTrue(all(n.flag is None for n in notes))


class Calibration(unittest.TestCase):
    def singer(self, sa_err=8, g=316, extra=()):
        # Held phrases where Sa/Pa are sung sa_err cents sharp of the pin and
        # komal Ga sits at g (table 294).
        body = []
        for _ in range(12):
            body += [sa_err] * 30 + [g + sa_err] * 30 + [702 + sa_err] * 30 + list(extra)
        return run(body)

    def test_sa_shift_is_corrected_and_komal_ga_measured(self):
        from pipeline.calibrate import calibrated_notes
        notes, sa, cal = calibrated_notes(self.singer(), SA)
        self.assertAlmostEqual(cal["sa_refine"]["shift_cents"], 8, delta=1)
        self.assertAlmostEqual(1200 * math.log2(sa / SA), 8, delta=1)
        self.assertAlmostEqual(cal["positions"]["g"], 316, delta=2)
        self.assertEqual(cal["positions"]["S"], 0)
        self.assertAlmostEqual(cal["positions"]["P"], 702, delta=0.1)
        ga = [n for n in notes if n.swara == "g"]
        self.assertTrue(ga and all(abs(n.cents_off) < 3 for n in ga))

    def test_shift_is_clamped_and_rare_swaras_keep_the_table(self):
        from pipeline.calibrate import calibrated_notes
        _, _, cal = calibrated_notes(self.singer(sa_err=0, g=334), SA)
        from pipeline.swara import SWARA_CENTS
        self.assertAlmostEqual(cal["positions"]["g"], SWARA_CENTS["g"] + 30, delta=0.1)
        self.assertEqual(cal["swaras"]["N"]["source"], "table")


class SaDetection(unittest.TestCase):
    def test_vocal_tonic_histogram_runs(self):
        import numpy as np
        from pipeline.detect_sa import _vocal_tonic_histogram
        f0 = np.array([SA * 2 ** (c / 1200) for c in [0] * 200 + [702] * 100 + [1200] * 100])
        cands = _vocal_tonic_histogram(f0)
        self.assertTrue(cands)

    def test_resting_notes_read_a_ma_tuned_tanpura(self):
        import numpy as np
        from pipeline.detect_sa import _sa_by_resting_notes
        # Jasraj side B: the tanpura's strongest usable peak is mandra Ma
        # (91.5 Hz); the singing rests on Sa=137.3 and Pa.
        sa = 137.3
        cents = [0] * 40 + [702] * 15 + [133] * 10 + [300] * 10 + [608] * 10 + [812] * 10 + [1120] * 5
        voiced = np.array([sa * 2 ** (c / 1200) for c in cents * 10])
        r = _sa_by_resting_notes([{"hz": 88.8}, {"hz": 86.1}, {"hz": 91.5}], voiced)
        self.assertEqual(r["peak_as"], "ma")
        self.assertAlmostEqual(r["sa_hz"], sa, delta=1.0)

    def test_raga_fit_picks_sa_over_the_tanpura_pa(self):
        import numpy as np
        from pipeline.raga import RAGAS, choose_sa
        # Todi phrase around Sa=161.5; the tanpura's strongest peak is Pa (242).
        sa = 161.5
        cents = [0] * 40 + [90] * 20 + [294] * 10 + [590] * 5 + [792] * 10 + [1088] * 15
        hz = np.array([sa * 2 ** (c / 1200) for c in cents])
        r = choose_sa([242.2, 121.1], hz, RAGAS["todi"])
        self.assertAlmostEqual(r["sa_hz"], sa, delta=1.0)
        self.assertGreater(r["fit"], 0.95)


class Output(unittest.TestCase):
    def test_error_notes_are_removed_but_audited(self):
        import json, tempfile
        from pathlib import Path
        from pipeline.transcribe import write_performance
        body = []
        for _ in range(60):
            body += [0] * 30 + [702] * 30 + [1200] * 30
        notes = frames_to_notes(run(body + [1200] * 30 + [2400] * 30 + [1200] * 30), SA, prepared=True)
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "performance.json"
            write_performance(notes, out, title="t", audio_rel="a.mp3", sa_hz=SA, sa_meta={})
            perf = json.loads(out.read_text())
        self.assertNotIn("S''", [n["label"] for n in perf["notes"]])
        self.assertTrue(all("flag" not in n for n in perf["notes"]))
        self.assertEqual([r[2:] for r in perf["removed_notes"]], [["S''", "range"]])
        self.assertEqual(perf["stats"]["removed"], {"range": 1, "octave": 0})


class Contour(unittest.TestCase):
    def test_gap_splits_runs(self):
        frames = run([0, 10, 20]) + run([702, 702], t0=1.0)
        c = build_contour(frames, SA)
        self.assertAlmostEqual(c["step"], 0.01)
        self.assertEqual(c["runs"], [[0.0, [0, 10, 20]], [1.0, [702, 702]]])


if __name__ == "__main__":
    unittest.main()
