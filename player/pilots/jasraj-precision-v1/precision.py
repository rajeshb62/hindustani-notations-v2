"""Precision-first gate: fresh RMVPE + historical CREPE, with pYIN conflict veto.
Scores are model-specific evidence, not calibrated correctness probabilities.
"""
import math,statistics,sys,json
from pathlib import Path
from collections import Counter
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[2]))
from pipeline.swara import nearest_swara
SA=136.18

def group(frames):
    notes=[];run=[];reasons=Counter()
    def flush():
        if len(run)>=10:
            hz=statistics.median(f['rmvpe'] for f in run);h=nearest_swara(hz,SA)
            notes.append(dict(t=round(run[0]['t'],3),dur=round(len(run)*.01,3),hz=round(hz,3),swara=h.swara,octave=h.octave,label=h.label,cents_off=round(h.cents_off,2),support_frames=len(run),max_tracker_disagreement_cents=round(max(abs(1200*math.log2(f['rmvpe']/f['crepe'])) for f in run),2)))
        else:reasons['short_temporal_support_frames']+=len(run)
        run.clear()
    for f in frames:
        reason=None;h=None
        if not f['voice']:reason='no_voice_evidence'
        elif not all(f.get(k) and math.isfinite(f[k]) and f[k]>0 for k in ['rmvpe','crepe']):reason='unvoiced_neural_tracker'
        elif f['conf']<.9 or f['salience']<.3:reason='weak_neural_evidence'
        elif abs(1200*math.log2(f['rmvpe']/f['crepe']))>30:reason='absolute_neural_disagreement'
        elif f.get('hz') and f['pyin_prob']>=.5 and abs(1200*math.log2(f['rmvpe']/f['hz']))>35:reason='pyin_conflict'
        else:
            h=nearest_swara(f['rmvpe'],SA)
            if abs(h.cents_off)>25:reason='ambiguous_swara'
        if reason:flush();reasons[reason]+=1;continue
        if run:
            prev=nearest_swara(run[-1]['rmvpe'],SA)
            if (h.swara,h.octave)!=(prev.swara,prev.octave) or abs(f['t']-run[-1]['t']-.01)>.001:flush()
        run.append(f)
    flush()
    return notes,dict(reasons)

def main():
    rows=json.loads((HERE/'frame-evidence.json').read_text())
    rm={f['t']:f for f in json.loads((HERE/'rmvpe-evidence.json').read_text())}
    for f in rows:f.update(rmvpe=rm[f['t']]['hz'],salience=rm[f['t']]['salience'])
    old=json.loads((HERE/'report.json').read_text())
    if not (HERE/'initial-pyin-report.json').exists():(HERE/'initial-pyin-report.json').write_text(json.dumps(old,indent=2))
    reports=[];notes=[]
    for w in old['windows']:
        ns,reasons=group([f for f in rows if w['start']<=f['t']<w['end']]);notes.extend(ns)
        reports.append(dict(w,candidate_notes=len(ns),candidate_seconds=round(sum(n['dur'] for n in ns),3),abstention_reasons=reasons))
    data=dict(title='Jasraj precision-first excerpt pilot',sa_hz=SA,notes=notes,windows=reports,scope='Only selected intervals analyzed; all other time untranscribed',confidence='No probability of correctness assigned')
    (HERE/'candidate.json').write_text(json.dumps(data,indent=2))
    old.update(windows=reports,total_notes=len(notes),transcribed_seconds=round(sum(n['dur'] for n in notes),3),new_trackers=['Fresh RMVPE on existing vocal stem','Fresh pYIN on vocal stem (conflict veto)','Fresh pYIN on original mix (diagnostic only)'],settings=dict(sa_hz=SA,crepe_score_min=.9,rmvpe_salience_min=.3,absolute_neural_agreement_cents=30,pyin_conflict_min_probability=.5,pyin_conflict_cents=35,swara_distance_cents_max=25,min_contiguous_frames=10),rmvpe_provenance=json.loads((HERE/'rmvpe-provenance.json').read_text()),decision='Initial pYIN mandatory agreement was nearly empty; use two neural trackers and pYIN conflict veto, not a lower pYIN threshold to fill gaps.')
    old['limitations'].append('Still extremely sparse; this is an audition experiment, not a demonstrated improvement. Historical VAD prevents transcription of several excerpts.')
    (HERE/'report.json').write_text(json.dumps(old,indent=2))
    print(json.dumps({'notes':len(notes),'seconds':old['transcribed_seconds'],'windows':reports},indent=2))
if __name__=='__main__':main()
