"""Run NEW short-window pYIN on vocal stem AND source; reuse historical raw CREPE/VAD."""
import csv,json,subprocess,time,hashlib
from pathlib import Path
import numpy as np
import librosa
from extract import group,SA
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=Path('/Users/rajeshbhat/claudecode/hindustani notations/performances/jasraj-performance-b')
WINDOWS=[(5,20,'Opening / historically preferred slow region'),(30,43,'Upper-Sa anchor near 0:37'),(699,713,'Previously undertracked alaap'),(1500,1515,'Later contrast A (tempo unverified)'),(2490,2505,'Later contrast B / historical VAD absent'),(2630,2645,'Closing / historical VAD present')]

def audio(path,a,b):
    buf=subprocess.check_output(['/opt/homebrew/bin/ffmpeg','-v','error','-ss',str(a),'-i',str(path),'-t',str(b-a),'-ac','1','-ar','16000','-f','f32le','-'])
    return np.frombuffer(buf,dtype=np.float32).copy()

def main():
    began=time.time()
    raw={round(float(r['time']),2):(float(r['frequency']),float(r['confidence'])) for r in csv.DictReader((SOURCE/'working/vocals.f0.csv').open())}
    vad=json.loads((SOURCE/'working/vad_segments.json').read_text())
    notes=[];reports=[];allframes=[]
    for a,b,title in WINDOWS:
        tracks=[]
        for name,path in [('vocal',SOURCE/'working/separated/htdemucs/source_audio/vocals.wav'),('source',SOURCE/'source_audio.mp3')]:
            y=audio(path,a-1,b+1)
            f,v,p=librosa.pyin(y,sr=16000,fmin=65,fmax=700,frame_length=2048,hop_length=160,center=True,fill_na=np.nan)
            np.savez(HERE/f'{a}-{b}-{name}-pyin.npz',f0=f,voiced=v,voiced_probability=p)
            tracks.append((f,p))
        rows=[]
        for j in range(round((b-a)*100)):
            t=round(a+j*.01,2); k=j+100
            hz,prob=tracks[0][0][k],tracks[0][1][k]
            shz,sprob=tracks[1][0][k],tracks[1][1][k]
            chz,conf=raw.get(t,(0,0))
            # Trim historical VAD padding; this is a proxy, not a singer identity oracle.
            voice=any(s['start']+.5<=t<s['end']-.5 for s in vad)
            rows.append(dict(t=t,hz=float(hz),pyin_prob=float(prob),source=float(shz),source_prob=float(sprob),crepe=chz,conf=conf,voice=voice))
        ns,reasons=group(rows);notes+=ns;allframes+=rows
        current=json.loads((ROOT/'data/pt-jasraj-side-a/performance.json').read_text())['notes']
        current=[n for n in current if n['t']<b and n['t']+n['dur']>a]
        report=dict(start=a,end=b,title=title,frames=len(rows),candidate_notes=len(ns),current_notes=len(current),candidate_seconds=round(sum(n['dur'] for n in ns),3),abstention_reasons=reasons)
        reports.append(report);print(json.dumps(report),flush=True)
    clean=[{k:(v if not isinstance(v,float) or np.isfinite(v) else None) for k,v in r.items()} for r in allframes]
    (HERE/'frame-evidence.json').write_text(json.dumps(clean,separators=(',',':'),allow_nan=False))
    data=dict(title='Jasraj precision-first excerpt pilot',sa_hz=SA,notes=notes,windows=reports,scope='Only selected intervals analyzed; all other time untranscribed',confidence='No probability of correctness assigned')
    (HERE/'candidate.json').write_text(json.dumps(data,indent=2))
    inputs=[SOURCE/'working/vocals.f0.csv',SOURCE/'working/vad_segments.json',ROOT/'data/pt-jasraj-side-a/performance.json']
    report=dict(windows=reports,total_notes=len(notes),total_analyzed_seconds=sum(b-a for a,b,_ in WINDOWS),transcribed_seconds=round(sum(n['dur'] for n in notes),3),elapsed_seconds=round(time.time()-began,2),librosa_version=librosa.__version__,new_trackers=['librosa pYIN on existing Demucs vocal stem','librosa pYIN on original source mix'],reused_evidence=['historical raw CREPE (not VAD-rescue CSV)','historical Silero VAD segments, edges trimmed 500 ms'],settings=dict(sa_hz=SA,sample_rate=16000,hop=160,frame=2048,fmin=65,fmax=700,padding_seconds=1,crepe_score_min=.9,pyin_voiced_probability_min=.8,source_pyin_voiced_probability_min=None,absolute_agreement_cents=35,min_contiguous_frames=10),inputs={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in inputs},limitations=['No human listening or annotated ground truth; precision not measured','pYIN source and stem are same algorithm; not independent models. New pYIN is algorithmically independent of historical CREPE','Historical speech VAD on separated vocals is imperfect for singing and can include bleed; no new separation or fresh neural voice detector','Agreement can still follow accompaniment; no singer identity guarantee','Conservative stable notes omit glides, ornaments, short notes and disagreements; gaps mean untranscribed, not singer silence','No full-recording extraction. Later windows selected by time, not verified tempo.'])
    (HERE/'report.json').write_text(json.dumps(report,indent=2))

if __name__=='__main__': main()
