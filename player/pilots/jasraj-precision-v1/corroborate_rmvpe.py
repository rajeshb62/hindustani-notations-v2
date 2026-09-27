"""Fresh candidate-only RMVPE evidence for the same pilot excerpts."""
import sys,json,time,hashlib
from pathlib import Path
import numpy as np
import torch
HERE=Path(__file__).resolve().parent
LEGACY=Path('/Users/rajeshbhat/claudecode/hindustani notations')
sys.path.insert(0,str(LEGACY))
from extract_rmvpe_candidate_chunked import RMVPE,infer_with_confidence
from analyze import audio,SOURCE,WINDOWS

def main():
    torch.set_num_threads(4)
    model=LEGACY/'melody_improve_runs/rmvpe_tools/rmvpe.pt'
    tracker=RMVPE(str(model),is_half=False,device='cpu',use_jit=False)
    rows=[];start=time.time()
    for a,b,title in WINDOWS:
        y=audio(SOURCE/'working/separated/htdemucs/source_audio/vocals.wav',a-1,b+1)
        f,c=infer_with_confidence(tracker,y,.03)
        for j in range(round((b-a)*100)):
            rows.append(dict(t=round(a+j*.01,2),hz=float(f[j+100]),salience=float(c[j+100])))
        print(a,b,'voiced',int(np.count_nonzero(f)),flush=True)
    (HERE/'rmvpe-evidence.json').write_text(json.dumps(rows,separators=(',',':')))
    (HERE/'rmvpe-provenance.json').write_text(json.dumps(dict(model=str(model),sha256=hashlib.sha256(model.read_bytes()).hexdigest(),source=str(SOURCE/'working/separated/htdemucs/source_audio/vocals.wav'),elapsed_seconds=time.time()-start,rows=len(rows),note='Fresh RMVPE on existing separated vocal stem; salience is not correctness probability'),indent=2))
if __name__=='__main__': main()
