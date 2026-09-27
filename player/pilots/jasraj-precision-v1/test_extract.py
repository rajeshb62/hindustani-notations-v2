import unittest
import extract

class PrecisionTests(unittest.TestCase):
    def test_absolute_octaves_and_no_gap_holds(self):
        frames = [dict(t=i*.01,hz=136.18,crepe=136.18,conf=.99,pyin_prob=.99,source=136.18,source_prob=.99,voice=True) for i in range(50)]
        for f in frames[20:30]: f['hz']=f['crepe']=f['source']=272.36
        frames[35]['voice']=False
        notes, reasons=extract.group(frames)
        self.assertEqual([(n['t'],n['dur'],n['octave']) for n in notes],[(0,.2,0),(.2,.1,1),(.36,.14,0)])
        self.assertEqual(reasons['no_voice_evidence'],1)
        self.assertTrue(all(n['hz'] in (136.18,272.36) for n in notes))

    def test_mix_voicing_score_is_not_a_singer_probability(self):
        frames=[dict(t=i*.01,hz=136.18,crepe=136.18,conf=.99,pyin_prob=.9,source=136.18,source_prob=.1,voice=True) for i in range(20)]
        notes,_=extract.group(frames)
        self.assertEqual(len(notes),1)
        frames[5]['crepe']=272.36
        notes,reasons=extract.group(frames)
        self.assertEqual(reasons['absolute_pitch_disagreement'],1)
        self.assertEqual(notes[0]['t'],.06)

if __name__=='__main__': unittest.main()
