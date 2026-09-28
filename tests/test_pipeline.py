import math
import unittest

from pipeline.transcribe import Frame, build_contour, frames_to_notes
from pipeline.vad_filter import is_drone_harmonic

SA = 96.97


def hz(cents: float) -> float:
    return SA * 2 ** (cents / 1200.0)


def run(cents_list, t0=0.0, step=0.01):
    return [Frame(t0 + i * step, hz(c), 0.9) for i, c in enumerate(cents_list)]


class DroneFilter(unittest.TestCase):
    def test_sa_and_pa_in_any_octave_are_drone_pitches(self):
        for c in (0, 1200, 2400, -1200, 702, 1902):
            self.assertTrue(is_drone_harmonic(hz(c), SA), c)

    def test_other_swaras_are_not(self):
        for c in (204, 386, 498, 884, 1088):
            self.assertFalse(is_drone_harmonic(hz(c), SA), c)


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


class Suspects(unittest.TestCase):
    def test_passing_tone_in_meend_is_flagged(self):
        # Sa held, 30 ms through Re, Ga held: Re lies between its neighbours.
        frames = run([0] * 30 + [204] * 3 + [386] * 30)
        notes = frames_to_notes(frames, SA)
        self.assertEqual([(n.label, n.flag) for n in notes],
                         [("S", None), ("R", "passing"), ("G", None)])

    def test_kan_turn_is_trusted(self):
        # Sa, 30 ms touch of Re above, back to Sa: a turn, not a passage.
        frames = run([0] * 30 + [204] * 3 + [0] * 30)
        notes = frames_to_notes(frames, SA)
        self.assertEqual([n.flag for n in notes], [None, None, None])

    def test_offcentre_short_note_is_flagged(self):
        # 30 ms at 150 cents: between r and R, sampled mid-glide.
        frames = run([0] * 30 + [150] * 3 + [0] * 30)
        notes = frames_to_notes(frames, SA)
        self.assertEqual(notes[1].flag, "offcentre")

    def test_long_notes_are_always_trusted(self):
        # Held 30 cents off komal Re: off-centre, but long, so trusted.
        frames = run([0] * 30 + [120] * 30 + [386] * 30)
        notes = frames_to_notes(frames, SA)
        self.assertTrue(all(n.flag is None for n in notes))


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


class Contour(unittest.TestCase):
    def test_gap_splits_runs(self):
        frames = run([0, 10, 20]) + run([702, 702], t0=1.0)
        c = build_contour(frames, SA)
        self.assertAlmostEqual(c["step"], 0.01)
        self.assertEqual(c["runs"], [[0.0, [0, 10, 20]], [1.0, [702, 702]]])


if __name__ == "__main__":
    unittest.main()
