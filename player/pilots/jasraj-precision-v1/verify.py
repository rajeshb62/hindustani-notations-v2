"""Independent gate, schema, HTTP, preservation and browser audit."""
import json,math,hashlib,urllib.request,subprocess
from pathlib import Path
HERE=Path(__file__).resolve().parent
c=json.loads((HERE/'candidate.json').read_text());r=json.loads((HERE/'report.json').read_text())
frames={f['t']:f for f in json.loads((HERE/'frame-evidence.json').read_text())}
rm={f['t']:f for f in json.loads((HERE/'rmvpe-evidence.json').read_text())}
assert c['sa_hz']==136.18 and len(frames)==8700 and len(rm)==8700
assert len(c['notes'])==r['total_notes']==sum(w['candidate_notes'] for w in r['windows'])
assert abs(sum(n['dur'] for n in c['notes'])-r['transcribed_seconds'])<1e-9
for n in c['notes']:
    assert n['dur']>=.1
    support=[f for t,f in frames.items() if n['t']-1e-6<=t<n['t']+n['dur']-1e-6]
    assert len(support)==n['support_frames']
    for f in support:
        pitch=rm[f['t']]
        assert f['voice'] and f['conf']>=.9 and pitch['salience']>=.3
        assert abs(1200*math.log2(pitch['hz']/f['crepe']))<=30
        if f['hz'] and f['pyin_prob']>=.5:assert abs(1200*math.log2(pitch['hz']/f['hz']))<=35
        ratios={'S':1,'r':256/243,'R':9/8,'g':32/27,'G':5/4,'M':4/3,'M+':45/32,'P':3/2,'d':128/81,'D':5/3,'n':16/9,'N':15/8}
        expected=136.18*ratios[n['swara']]*2**n['octave']
        assert abs(1200*math.log2(pitch['hz']/expected))<=25
    assert all(abs(b['t']-a['t']-.01)<1e-6 for a,b in zip(support,support[1:]))
for w in r['windows']:
    ns=[n for n in c['notes'] if w['start']<=n['t']<w['end']]
    assert len(ns)==w['candidate_notes']
    assert all(n['t']+n['dur']<=w['end']+1e-6 for n in ns)
    assert w['frames']==sum(w['abstention_reasons'].values())+sum(n['support_frames'] for n in ns)
assert all(a['t']+a['dur']<=b['t']+1e-6 for a,b in zip(c['notes'],c['notes'][1:]))
http={};base='http://127.0.0.1:8765/'
for path in ['pilots/jasraj-precision-v1/index.html','pilots/jasraj-precision-v1/app.js','pilots/jasraj-precision-v1/candidate.json','pilots/jasraj-precision-v1/README.md','data/pt-jasraj-side-a/performance.json']:
    with urllib.request.urlopen(base+path,timeout=10) as response:http[path]=response.status;assert response.status==200
with urllib.request.urlopen(urllib.request.Request(base+'data/pt-jasraj-side-a/source_audio.mp3',headers={'Range':'bytes=1000-1999'}),timeout=10) as response:
    assert response.status==206 and len(response.read())==1000
    http['audio_range']=response.status
hashes=json.loads(Path('/tmp/jasraj-pilot-original-hashes.json').read_text())
preserved={p:hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items()};assert all(preserved.values())
for script in ['app.js','test_browser.cjs']:subprocess.run(['node','--check',str(HERE/script)],check=True)
subprocess.run(['python3','-m','unittest','test_extract','test_precision'],cwd=HERE,check=True)
browser=subprocess.run(['node','test_browser.cjs'],cwd=HERE,capture_output=True,text=True,timeout=45,check=True)
result=dict(candidate_notes=len(c['notes']),analyzed_frames=len(frames),transcribed_seconds=r['transcribed_seconds'],current_notes_in_excerpts=sum(w['current_notes'] for w in r['windows']),http=http,production_hashes_unchanged=preserved,browser=json.loads(browser.stdout),invariants='all pass')
(HERE/'verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))
