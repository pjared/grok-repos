import cv2, numpy as np, json, sys
def track(path, init, min_area, maxjump, hsv_lo=(10,70,70), hsv_hi=(30,255,255), start_frame=0):
    cap=cv2.VideoCapture(path); res=[]; prev=init; i=0
    while True:
        ok,fr=cap.read()
        if not ok: break
        if i<start_frame: res.append(None); i+=1; continue
        hsv=cv2.cvtColor(fr,cv2.COLOR_BGR2HSV)
        m=cv2.inRange(hsv,np.array(hsv_lo),np.array(hsv_hi))
        m=cv2.morphologyEx(m,cv2.MORPH_CLOSE,np.ones((5,5),np.uint8))
        n,lab,st,cen=cv2.connectedComponentsWithStats(m)
        best=None
        for k in range(1,n):
            x,y,w,h,a=st[k]
            if a<min_area: continue
            c=cen[k]
            d=np.hypot(c[0]-prev[0],c[1]-prev[1]) if prev else 0
            if prev and d>maxjump: continue
            if best is None or (d if prev else -a)<best[0]: best=((d if prev else -a),[int(x),int(y),int(w),int(h),int(a)])
        if best: res.append(best[1]); prev=(best[1][0]+best[1][2]/2,best[1][1]+best[1][3]/2)
        else: res.append(None)
        i+=1
    return res
which=sys.argv[1]
if which=='F3a':
    r=track('work/n_F3a.mp4',(253,475),120,60)
else:
    r=track('work/n_F5a.mp4',None,1500,200,start_frame=100)
json.dump(r,open(f'work/track_{which}.json','w'))
for i in range(0,len(r),6): print(i, f'{i/24:.2f}', r[i])
