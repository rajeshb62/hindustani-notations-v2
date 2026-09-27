import unittest
import precision

def frames():
    return [dict(t=i*.01,hz=136.18,pyin_prob=.9,crepe=136.18,conf=.99,voice=True,rmvpe=136.18,salience=.8) for i in range(50)]

class Tests(unittest.TestCase):
    def test_two_neural_trackers_can_support_pyin_abstention(self):
        rows=frames()
        for f in rows: f['hz']=None;f['pyin_prob']=.01
        notes,_=precision.group(rows)
        self.assertEqual(len(notes),1)
        self.assertEqual(notes[0]['dur'],.5)
    def test_octave_and_gap_not_averaged_or_held(self):
        rows=frames()
        for f in rows[20:30]: f['rmvpe']=f['crepe']=f['hz']=272.36
        rows[35]['voice']=False
        notes,_=precision.group(rows)
        self.assertEqual([(n['t'],n['dur'],n['octave']) for n in notes],[(0,.2,0),(.2,.1,1),(.36,.14,0)])
    def test_confident_pyin_conflict_vetoes(self):
        rows=frames()
        for f in rows:f['hz']=272.36
        self.assertEqual(precision.group(rows)[0],[])
    def test_between_swaras_abstains(self):
        rows=frames()
        for f in rows:f['hz']=f['crepe']=f['rmvpe']=136.18*2**(40/1200)
        self.assertEqual(precision.group(rows)[0],[])
    def test_low_neural_evidence_abstains(self):
        for key,value in [('conf',.8),('salience',.1),('voice',False),('rmvpe',272.36)]:
            rows=frames()
            for f in rows:f[key]=value
            self.assertEqual(precision.group(rows)[0],[])

if __name__=='__main__': unittest.main()
