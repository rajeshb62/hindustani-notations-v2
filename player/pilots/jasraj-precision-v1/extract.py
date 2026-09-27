"""Candidate-only strict frame gating. Never changes source or production files."""
import math, statistics, sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from pipeline.swara import nearest_swara
SA=136.18
STEP=.01

def group(frames):
    notes=[]; reasons=Counter(); run=[]
    def flush():
        if len(run)>=10:
            hz=statistics.median(f['hz'] for f in run)
            h=nearest_swara(hz,SA)
            notes.append(dict(t=round(run[0]['t'],3),dur=round(len(run)*STEP,3),hz=round(hz,3),swara=h.swara,octave=h.octave,label=h.label,cents_off=round(h.cents_off,2),support_frames=len(run),max_tracker_disagreement_cents=round(max(abs(1200*math.log2(f['hz']/f['crepe'])) for f in run),2)))
        else: reasons['short_temporal_support_frames']+=len(run)
        run.clear()
    for f in frames:
        reason=None
        if not f['voice']: reason='no_voice_evidence'
        elif not all(math.isfinite(f[x]) and f[x]>0 for x in ['hz','crepe','source']): reason='unvoiced_tracker'
        elif f['conf']<.9 or f['pyin_prob']<.8: reason='weak_tracker_evidence'
        elif max(abs(1200*math.log2(f['hz']/f[x])) for x in ['crepe','source'])>35: reason='absolute_pitch_disagreement'
        if reason:
            flush(); reasons[reason]+=1; continue
        h=nearest_swara(f['hz'],SA)
        if run:
            prev=nearest_swara(run[-1]['hz'],SA)
            if (h.swara,h.octave)!=(prev.swara,prev.octave) or abs(f['t']-run[-1]['t']-STEP)>.001: flush()
        run.append(f)
    flush()
    return notes,dict(reasons)
