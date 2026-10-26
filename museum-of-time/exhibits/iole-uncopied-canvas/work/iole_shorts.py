import subprocess
from pathlib import Path
EX=Path('/workspace/museum-of-time/exhibits/iole-uncopied-canvas'); FULL=EX/'out/Iole_full.mp4'
SANS='/usr/share/fonts/truetype/sand-box/google/Inter/Inter-VariableFont_opsz,wght.ttf'
SB='/usr/share/fonts/truetype/sand-box/custom/Source Serif Pro/SourceSerifPro-Semibold.ttf'
SI='/usr/share/fonts/truetype/sand-box/custom/Source Serif Pro/SourceSerifPro-It.ttf'
esc=lambda s: s.replace('\\','\\\\').replace(':','\\:').replace("'","\u2019")
LABEL=esc('Museum of Time · Travelers · Iole of the Uncopied Canvas'); CUE=esc('A parable — not a history.')
SH=[('Iole_short1',0.000,59.917),('Iole_short2',59.917,109.3333)]
for name,a,b in SH:
    d=b-a
    fc=(f"[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS,split=2[bgi][fgi];"
        f"[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS,"+('' if a==0 else 'afade=t=in:st=0:d=0.02,')+f"afade=t=out:st={d-0.04:.3f}:d=0.04,aformat=sample_rates=44100:channel_layouts=mono[am];"
        "[bgi]scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920,gblur=sigma=22,eq=brightness=-0.35:contrast=0.75[bg];"
        "[fgi]scale=1080:608[fg];"
        f"[bg][fg]overlay=(W-w)/2:(H-h)/2,drawtext=fontfile='{SANS}':text='{LABEL}':fontsize=28:fontcolor=0xE8E0D4@0.90:x=(w-text_w)/2:y=72:shadowcolor=black@0.6:shadowx=1:shadowy=1,"
        f"drawtext=fontfile='{SI}':text='{CUE}':fontsize=26:fontcolor=0xE8E0D4@0.75:x=(w-text_w)/2:y=116:shadowcolor=black@0.6:shadowx=1:shadowy=1,setsar=1,format=yuv420p[vm];"
        f"[1:v]drawtext=fontfile='{SB}':text='Full episode on YouTube':fontsize=42:fontcolor=0xE8E0D4@0.95:x=(w-text_w)/2:y=h*0.45:shadowcolor=black@0.5:shadowx=1:shadowy=1,"
        f"drawtext=fontfile='{SANS}':text='{LABEL}':fontsize=24:fontcolor=0xE8E0D4@0.80:x=(w-text_w)/2:y=h*0.53,fade=t=in:st=0:d=0.3,setsar=1,format=yuv420p[vs];"
        "[vm][am][vs][2:a]concat=n=2:v=1:a=1[v][a]")
    subprocess.run(['ffmpeg','-y','-v','error','-i',str(FULL),'-f','lavfi','-i','color=c=0x0A0908:s=1080x1920:r=24:d=2',
        '-f','lavfi','-i','anullsrc=r=44100:cl=mono:d=2','-filter_complex',fc,'-map','[v]','-map','[a]',
        '-c:v','libx264','-preset','medium','-crf','19','-pix_fmt','yuv420p','-r','24','-c:a','aac','-b:a','160k','-ar','44100','-ac','1',
        '-movflags','+faststart',str(EX/f'out/{name}.mp4')],check=True)
    print(name,a,b,round(d,3))
