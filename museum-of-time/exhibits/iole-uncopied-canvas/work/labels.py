import cv2, json, subprocess, numpy as np
from PIL import Image, ImageDraw, ImageFont
SB='/usr/share/fonts/truetype/sand-box/custom/Source Serif Pro/SourceSerifPro-Semibold.ttf'
SI='/usr/share/fonts/truetype/sand-box/custom/Source Serif Pro/SourceSerifPro-It.ttf'
INK=(38,26,12); HI=(236,210,150)
def fit(draw, text, fontpath, maxw, maxh):
    s=int(maxh)
    while s>6:
        f=ImageFont.truetype(fontpath,s); b=draw.textbbox((0,0),text,font=f)
        if b[2]-b[0]<=maxw and b[3]-b[1]<=maxh: return f,b
        s-=1
    f=ImageFont.truetype(fontpath,6); return f,draw.textbbox((0,0),text,font=f)
def engrave(img, lines, rect, alpha):
    # lines: list of (text, font, rel_height, spacing)
    x,y,w,h=rect
    S=4  # supersample
    L=Image.new('RGBA',(int(w*S),int(h*S)),(0,0,0,0)); d=ImageDraw.Draw(L)
    padx=w*S*0.10; pady=h*S*0.14
    avail_h=h*S-2*pady
    total=sum(r for _,_,r in lines)
    cy=pady
    for text,fp,r in lines:
        lh=avail_h*r/total
        f,b=fit(d,text,fp,w*S-2*padx,lh*0.78)
        tw=b[2]-b[0]; th=b[3]-b[1]
        tx=(w*S-tw)/2-b[0]; ty=cy+(lh-th)/2-b[1]
        d.text((tx,ty+S*0.9),text,font=f,fill=HI+(int(110*alpha),))
        d.text((tx,ty),text,font=f,fill=INK+(int(235*alpha),))
        cy+=lh
    L=L.resize((max(1,int(round(w))),max(1,int(round(h)))),Image.LANCZOS)
    img.alpha_composite(L,(int(round(x)),int(round(y))))
def smooth(boxes, k=5):
    arr=np.array([b[:4] if b else [np.nan]*4 for b in boxes],float)
    out=arr.copy()
    for i in range(len(arr)):
        seg=arr[max(0,i-k//2):i+k//2+1]; seg=seg[~np.isnan(seg[:,0])]
        if len(seg): out[i]=seg.mean(0)
    return out
def run(name, rect_fn, alpha_fn, lines):
    src=f'work/n_{name}.mp4'; dst=f'work/l_{name}.mp4'
    cap=cv2.VideoCapture(src); W,H=1280,720
    p=subprocess.Popen(['ffmpeg','-y','-v','error','-f','rawvideo','-pix_fmt','rgb24','-s',f'{W}x{H}','-r','24','-i','-',
        '-c:v','libx264','-preset','veryfast','-crf','16','-pix_fmt','yuv420p',dst],stdin=subprocess.PIPE)
    i=0
    while True:
        ok,fr=cap.read()
        if not ok: break
        img=Image.fromarray(cv2.cvtColor(fr,cv2.COLOR_BGR2RGB)).convert('RGBA')
        a=alpha_fn(i); r=rect_fn(i)
        if a>0 and r is not None: engrave(img,lines,r,a)
        p.stdin.write(np.asarray(img.convert('RGB')).tobytes()); i+=1
    p.stdin.close(); p.wait(); print(name,'frames',i)
# F3a: GRIEF / 2091, plate visible until hand arrives (~frame 84)
t3=json.load(open('work/track_F3a.json')); s3=smooth(t3)
def r3(i):
    if i>=len(s3) or np.isnan(s3[i][0]) or i>88: return None
    x,y,w,h=s3[min(i,80)] if i>80 else s3[i]
    if i>80:  # keep last clean size, follow position
        x=s3[i][0]
    return (x+w*0.04,y+h*0.10,w*0.92,h*0.80)
a3=lambda i: 1.0 if i<=78 else max(0.0,1-(i-78)/10)
run('F3a',r3,a3,[('GRIEF',SB,1.25),('2091',SB,0.85)])
# F5a: PIGMENT LATER / THAN ITS CENTURY / Provenance unknown
t5=json.load(open('work/track_F5a.json')); s5=smooth(t5,3)
def r5(i):
    if i>=len(s5) or np.isnan(s5[i][0]): return None
    x,y,w,h=s5[i]
    if x+w>=1276: w=max(w,1.84*h)
    return (x,y,w,h)
a5=lambda i: 0 if i<144 else min(1.0,(i-143)/6)
run('F5a',r5,a5,[('PIGMENT LATER',SB,1.0),('THAN ITS CENTURY',SB,1.0),('Provenance unknown',SI,0.95)])
