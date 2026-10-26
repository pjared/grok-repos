import json, subprocess, sys
from pathlib import Path
EX=Path('/workspace/museum-of-time/exhibits/iole-uncopied-canvas'); W=EX/'work'; OUT=EX/'out'; OUT.mkdir(exist_ok=True)
FPS=24; X=0.5
SB='/usr/share/fonts/truetype/sand-box/custom/Source Serif Pro/SourceSerifPro-Semibold.ttf'
SI='/usr/share/fonts/truetype/sand-box/custom/Source Serif Pro/SourceSerifPro-It.ttf'
SANS='/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf'
def probe(p): return float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(p)],text=True))
def run(c): subprocess.run(c,check=True)
fr=lambda t: round(t*FPS)/FPS
vo=[EX/f'vo/iole-vo-0{i}.mp3' for i in range(7)]
d=[probe(p) for p in vo]
LEAD=0.3; GAPS=[0.5,0.5,1.0,1.0,1.0,1.0]; TAIL=2.0
starts=[LEAD]
for i in range(1,7): starts.append(starts[i-1]+d[i-1]+GAPS[i-1])
ends=[s+x for s,x in zip(starts,d)]
END=fr(ends[6]+TAIL)
S=starts; E=ends
T=[S[1]-0.25,            # card -> F1
   E[1]+0.25,            # F1 -> F2a
   S[2]+6.17,            # F2a -> F2b  (pause after "a painting she made.")
   E[2]+0.5,             # F2b -> F3a  (mid gap)
   S[3]+8.46,            # F3a -> F3b  (after "flawless likenesses.")
   S[3]+17.88,           # F3b -> F3c  (after "an unfinished life —")
   E[3]+0.25,            # F3c -> F4a  (xfade done 0.5s after S3 VO; short cut here)
   S[4]+6.09,            # F4a -> F4b  (after "a masterpiece.")
   S[4]+16.68,           # F4b -> F4c  (after "ordinary days.")
   E[4]+0.5,             # F4c -> F5a
   S[5]+7.19,            # F5a -> F5b  (after "No tidy author line.")
   E[5]+0.5]             # F5b -> F6
T=[fr(t) for t in T]
# clip, source, head trim, mode ('slow' uses all after head; 'center'/'start'/'tail' trims), interp
CL=[('CARD',None,0,None),
    ('F1','n_F1.mp4',0,'slow'),('F2a','n_F2a.mp4',0,'center'),('F2b','n_F2b.mp4',0,'slow'),
    ('F3a','l_F3a.mp4',0,'slow'),('F3b','n_F3b.mp4',0,'slow'),('F3c','n_F3c.mp4',0.30,'start'),
    ('F4a','n_F4a.mp4',0,'center'),('F4b','n_F4b.mp4',0.40,'slow'),('F4c','n_F4c.mp4',0.35,'tail'),
    ('F5a','l_F5a.mp4',1.35,'tail'),('F5b','n_F5b.mp4',1.75,'slow'),('F6','n_F6.mp4',1.00,'slow')]
bounds=[0.0]+T+[END]
plan=[]
for i,(n,src,head,mode) in enumerate(CL):
    a,b=bounds[i],bounds[i+1]
    out=(b-a)+(0 if i==0 else X/2)+(0 if i==len(CL)-1 else X/2)
    frames=round(out*FPS)
    if src is None: plan.append(dict(name=n,a=a,b=b,out=out,frames=frames)); continue
    raw=probe(W/src)-head
    if out<=raw:
        speed=1.0; span=out
        st={'center':head+(raw-out)/2,'start':head,'tail':head+raw-out,'slow':head+(raw-out)/2}[mode]
    else:
        speed=(out+2.5/FPS)/raw; span=raw; st=head
    plan.append(dict(name=n,src=src,a=a,b=b,out=out,frames=frames,raw=raw,speed=speed,start=st,span=span))
for p in plan: print(f"{p['name']:5s} ep {p['a']:7.3f}-{p['b']:7.3f} out={p['out']:6.3f} " + (f"speed={p['speed']:.3f} src {p['start']:.2f}+{p['span']:.2f} of {p['raw']:.2f}" if 'speed' in p else 'card'))
print('VO starts',[round(s,3) for s in S],'ends',[round(e,3) for e in E],'END',END)
sys.stdout.flush()
# title card
card=plan[0]
txt=lambda s: s.replace(':','\\:').replace("'","\u2019")
vf=(f"drawtext=fontfile='{SB}':text='IOLE OF THE UNCOPIED CANVAS':fontsize=56:fontcolor=0xF2F0EC:x=(w-text_w)/2:y=h*0.40,"
    f"drawtext=fontfile='{SI}':text='{txt('A parable — not a history.')}':fontsize=32:fontcolor=0xF2F0EC@0.92:x=(w-text_w)/2:y=h*0.40+86,"
    f"drawtext=fontfile='{SANS}':text='{txt('Museum of Time · Travelers')}':fontsize=20:fontcolor=0xF2F0EC@0.70:x=(w-text_w)/2:y=h*0.80,"
    f"fade=t=in:st=0:d=0.6,setsar=1,format=yuv420p")
timed=[W/'t_00_CARD.mp4']
run(['ffmpeg','-y','-v','error','-f','lavfi','-i',f'color=c=black:s=1280x720:r={FPS}','-vf',vf,'-frames:v',str(card['frames']),
     '-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p',str(timed[0])])
for i,p in enumerate(plan[1:],1):
    dst=W/f"t_{i:02d}_{p['name']}.mp4"
    vf=f"trim=start={p['start']:.4f}:duration={p['span']+0.2:.4f},setpts=PTS-STARTPTS"
    if p['speed']>1.001:
        mode='mci:mc_mode=aobmc:me_mode=bidir:vsbmc=1' if p['speed']>1.45 else 'blend'
        vf+=f",setpts={p['speed']:.5f}*PTS,minterpolate=fps={FPS}:mi_mode={mode}"
    if i==len(plan)-1: vf+=f",fade=t=out:st={p['out']-1.5:.3f}:d=1.5"
    vf+=",setsar=1,format=yuv420p"
    run(['ffmpeg','-y','-v','error','-i',str(W/p['src']),'-an','-vf',vf,'-frames:v',str(p['frames']),'-r',str(FPS),
         '-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p',str(dst)])
    got=int(subprocess.check_output(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries','stream=nb_read_frames','-of','csv=p=0',str(dst)],text=True))
    assert got==p['frames'],(p['name'],got,p['frames'])
    timed.append(dst)
inp=[]; [inp.extend(['-i',str(t)]) for t in timed]
fc=[]; cur='0:v'
for k,t in enumerate(T):
    fc.append(f'[{cur}][{k+1}:v]xfade=transition=fade:duration={X}:offset={t-X/2:.5f}[x{k}]'); cur=f'x{k}'
# narration track
ad=[]; am=''
for i,p in enumerate(vo):
    inp.extend(['-i',str(p)])
    ad.append(f'[{len(timed)+i}:a]aformat=sample_rates=44100:channel_layouts=mono,adelay={int(round(S[i]*1000))}:all=1[a{i}]'); am+=f'[a{i}]'
fc+=ad+[f'{am}amix=inputs=7:normalize=0:duration=longest,apad,atrim=0:{END:.4f}[am]']
raw=W/'iole_raw.mp4'
run(['ffmpeg','-y','-v','error',*inp,'-filter_complex',';'.join(fc),'-map',f'[{cur}]','-map','[am]','-c:v','libx264','-preset','medium','-crf','18',
     '-pix_fmt','yuv420p','-c:a','pcm_s16le','-t',f'{END:.4f}',str(W/'iole_raw.mov')])
json.dump(dict(plan=plan,T=T,S=S,E=E,END=END),open(W/'iole_plan.json','w'),indent=1,default=float)
print('raw done', probe(W/'iole_raw.mov'))
