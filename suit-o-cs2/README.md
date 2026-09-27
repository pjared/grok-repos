# Suit-O

Suit-O is a local companion for Counter-Strike 2. While you play, it listens to Valve's Game State Integration feed and speaks short, in-character lines into your headset: round starts, a broke buy, a plant, a multi-kill, your own death, the end of the match.

The voice is an original parody of a jittery corporate suit-assistant. He stammers, offers "Helpful tip:" advice nobody asked for, is proud of a useless "detective mode," gets huffy and threatens to report the developers when the economy is a shortcut, and treats every goodbye like a finale. The lines are written for Suit-O. They are not quotes from another game.

Suit-O v1 runs on your PC. It uses Windows' built-in speech synthesizer. It does not call an AI API, does not read the microphone, and does not send audio to voice chat.

## What it uses from the game

CS2 posts JSON to `http://127.0.0.1:3000` when you install the config file in this folder. Suit-O checks a shared auth token, then reacts to your own HUD state: your health, your money, your round kills, the round result, and whether the bomb was planted, defused, or exploded. Those are things you can already see or hear.

Bomb coordinates and weapon lists may arrive in the payload because the config asks for the `bomb` and `player_weapons` blocks. Suit-O never reads coordinates, never reads weapons, and never subscribes to other players. A clutch (last player alive) is not detected, because that would need everyone else's alive state.

## Layout

| Piece | Role |
| --- | --- |
| `suit_o/gsi/` | Local HTTP server. Validates the token and queues payloads so speech cannot stall CS2. |
| `suit_o/events/` | Diffs snapshots into typed events. |
| `suit_o/lines/` | `LineProvider` chooses a line. v1 reads `lines/lines.yaml`. A future AI provider can replace this class without touching detection. |
| `suit_o/speech/` | `SpeechBackend` plays audio. v1 uses `pyttsx3` (SAPI). `remote` is a documented stub and is not implemented. |
| `config.yaml` | Port, token, voice, device, cooldowns, mute, and a reserved push-to-talk key. |
| `gamestate_integration_suito.cfg` | The file you copy into the CS2 `cfg` folder. |

## Windows setup

These steps assume Windows 10 or 11 and the default Steam library path. If CS2 is on another disk, use that library's `cfg` folder instead.

1. Install Python 3.11 or newer from [python.org](https://www.python.org/downloads/windows/). On the first installer page, enable **Add python.exe to PATH**.

2. Open PowerShell in this folder (`suit-o-cs2`):

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   python -m pip install -r requirements.txt
   ```

   If activation is blocked, run `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` once, then activate again.

3. Pick a token and put the same value in both places:
   - `config.yaml` → `server.token`
   - `gamestate_integration_suito.cfg` → `auth` / `token`

   The sample value `suito-local-change-me` works for a first run. Change it before using a shared computer. Suit-O only binds to `127.0.0.1`.

4. Copy `gamestate_integration_suito.cfg` into the CS2 config directory:

   ```text
   C:\Program Files (x86)\Steam\steamapps\common\Counter-Strike Global Offensive\game\csgo\cfg\
   ```

   The file name has to stay `gamestate_integration_suito.cfg` (CS2 only loads files whose names start with `gamestate_integration_`).

5. Quit Counter-Strike 2 completely if it is running, then start it again. The game reads GSI configs at launch.

6. Start the desktop window and leave it open while you play. Double-click `Start Suit-O GUI.vbs` in this folder (no console window). From PowerShell:

   ```powershell
   python -m suit_o.gui
   ```

   `Start Suit-O GUI.bat` does the same thing with `pythonw`. The window has three tabs.

   **Listener.** Shows whether the listener is up and how long it has been since CS2 last sent game state. Mute, volume, and the output device are saved back to `config.yaml`. Pick the playback device you actually want to hear. The list is Windows' speech outputs (SAPI), for example speakers, a headset earphone, a digital output, or a monitor. A headset often shows up twice — once for game audio and once for chat — and the Windows default is not always the one that makes a sound. Choose the endpoint, then press **Test voice**. Microphones are not listed, and Suit-O still refuses a microphone or virtual-cable name if one is typed into `speech.output_device`.

   **Voice.** Fine-tune the voice used for every in-game line. The picker lists installed Windows SAPI voices (blank in the config, shown as "Engine default", keeps the engine's own voice) and any voice you built on the Voice Training tab (`Clone: name`). Sliders set speaking rate (words per minute), pitch (-10 to 10), volume (the same slider as on the Listener tab), and an optional pause before each line (milliseconds). Emphasis is None, Mild, or Strong. **Preview** speaks the text box through the output device selected on the Listener tab, including slider positions you have not saved yet. **Save** writes the settings and uses them for every in-game line. Saving a cloned voice sets `speech.backend` to `clone`. **Reset to defaults** puts back rate 185, pitch 0, volume 0.85, no pause, no emphasis, and the engine default voice, and saves that immediately. Closing the window saves the last saved tuning, not an unsaved draft. Volume is the exception: moving either volume slider saves it.

   **Voice Training.** Record a short script in your own voice (or someone who agreed), then press **Build voice**. That stores a profile under `voices/` (gitignored) and adds it to the Voice tab. See [Voice cloning](#voice-cloning) below. The tab tells you if the optional packages are missing, and whether synthesis will use NVIDIA CUDA or the CPU.

7. The console listener still works if you want a terminal instead of the window. Double-click `Start Suit-O.bat`, or:

   ```powershell
   python -m suit_o
   ```

   The log line `GSI endpoint ready at http://127.0.0.1:3000/` means it is waiting. Join a match. On a new round you should see a line in the log and hear it. Leaving `speech.output_device` blank uses the Windows default playback device. To target one device by name, set `output_device` to part of its playback name, such as `Headphones`. Use the speaker or headphone name, not the microphone name.

Optional voice settings in `config.yaml`. These six are not tied to SAPI, so a future custom or cloned voice (a remote TTS server) can reuse the same panel and the same keys:

- `speech.voice`: part of an installed voice name (`David`, `Zira`, ...), or the name of a cloned profile when `speech.backend` is `clone`. Blank keeps the engine default.
- `speech.rate`: words per minute, 80 to 400 (default 185).
- `speech.volume`: `0.0` to `1.0` (default `0.85`).
- `speech.pitch`: integer from `-10` to `10` (default `0`, the voice's own pitch). pyttsx3 cannot set SAPI pitch on its own, so Suit-O wraps each affected line in SAPI XML such as `<pitch absmiddle="2">`. Plain lines stay plain text.
- `speech.pause_ms`: milliseconds of silence before a line, `0` to `1000` (default `0`). Spoken with SAPI `<silence msec="..."/>` when it is not zero.
- `speech.emphasis`: `none`, `mild`, or `strong` (default `none`). Mild and strong use SAPI `<emph>`. Strong also raises pitch by 3 for that line only, still inside `-10` to `10`.

`speech.backend` may be `pyttsx3`, `clone`, or `stub`. `remote` is still refused at startup. Rate, volume, pause, pitch, and emphasis are the same fields for every backend. Chatterbox has no pitch or words-per-minute control, so pre-rendering applies pitch and rate to the waveform and maps emphasis onto Chatterbox's exaggeration control. Volume is applied when the WAV is played, on the output device from the Listener tab.

## Voice cloning

Stock Windows voices still sound like a default SAPI voice. Voice Training is a recorder plus a zero-shot clone, not a long training run.

The model is [Chatterbox](https://github.com/resemble-ai/chatterbox) by Resemble AI (`pip` package `chatterbox-tts`). It is published under the **MIT license**. That is not a non-commercial license: commercial use is allowed, and so is personal local use. You still have to record **your own voice, or someone who agreed to it**. Do not feed it ripped game audio or an actor's performance.

Chatterbox clones from a reference clip. The script in `voice_script.txt` is about one to three minutes of original Suit-O lines (vowels, consonants, numbers, questions) so the recording covers a wide set of sounds. The profile keeps the full recording. The model itself is prompted with a clean excerpt of up to 30 seconds, which is the length this model is built for. Edit `voice_script.txt` in any text editor and press **Reload script** before you record.

On the Voice Training tab: pick the **microphone** (input devices are allowed here), read the line, then **Record / Stop / Play back / Re-record**. The level meter moves while you record. Playback goes to the output device chosen on the Listener tab. That output still cannot be a microphone or a virtual cable. **Build voice** writes `voices/<name>/` with `profile.yaml`, `reference.wav`, and `prompt.wav`. You need about a minute of audio and a take for every script line.

**Build voice** also pre-renders every stock line in `lines/lines.yaml` to WAV files under `voices/<name>/cache/`. That render is required. It runs again when you edit those stock lines, and again when you save a new rate, pitch, pause, or emphasis for that voice. Volume does not rebuild the files. During a match Suit-O plays only those files: no live synthesis and no GPU use. If a file is missing (a line that filled in a real map name, health, or dollar amount, or a render that has not finished), that one line uses the Windows SAPI voice instead of generating audio mid-match. **Preview** on the Voice tab is the only live synthesis. After a render or a preview, the model is unloaded so the GPU is free for the match.

Install the optional stack only if you want this. The base app stays on PyYAML and pyttsx3.

```powershell
python -m pip install -r requirements-voice.txt
```

NVIDIA GPU (faster; the tab shows the CUDA device name when it is visible):

```powershell
python -m pip install torch torchaudio --index-url https://download.pytorch.org/whl/cu124
python -m pip install -r requirements-voice.txt
```

If there is no NVIDIA GPU, the same requirements file runs on CPU. The tab says which one it is using.

Rough size, so you can plan disk space before installing:

- Disk: about 8 GB free. The Python packages are several GB, and the first synthesis downloads about 2 GB of Chatterbox weights into the Hugging Face cache.
- VRAM: about 4–6 GB for the English Chatterbox model while it is pre-rendering or previewing, when CUDA is available. Matches do not use the GPU. CPU mode does not need VRAM; it uses system RAM and is slower, which only matters while the stock lines are being rendered.

After you build or save the cloned voice, Suit-O speaks it through the `clone` backend on the same speech thread as everything else (not the GUI thread). That thread only reads the pre-rendered WAV. Preview uses the clone for one line even before you save it, without switching in-game lines until **Save**.

`voices/` is gitignored. Nothing you record is committed.

## Mute

- In the desktop window, press **Mute**. Press **Unmute** to hear lines again. The choice is saved in `config.yaml`.
- In the console listener, type `m` and press Enter. Type `m` again to unmute. Type `q` and Enter to quit. Console mute lasts for that run; it does not rewrite `config.yaml`.
- Or set `mute: true` in `config.yaml` before starting.
- Or from another terminal: `Invoke-WebRequest -Method POST http://127.0.0.1:3000/mute`
- Status: `Invoke-WebRequest http://127.0.0.1:3000/status`

Muted means queued lines are dropped and the current line is stopped. CS2 keeps posting; Suit-O just stays quiet.

## Push-to-talk (reserved)

`ptt.keybind` is stored for a future version. v1 does not listen for it, does not open a microphone, and does not talk to voice chat. If you fill it in, it must be a different key from `ptt.cs2_voice_key` (your actual CS2 voice bind, default `v`). Suit-O refuses to start when those two match.

## Try it without the game

The simulator posts a synthetic match at the local server and uses an in-memory speech backend, so nothing is played out loud:

```powershell
python -m suit_o.simulate
```

It exits with an error if any event fails to produce a line. A normal run ends with `All 19 events produced a line.`

Unit tests (from this folder, with the dev requirements installed):

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest
```

## How lines are chosen

Each event has its own list in `lines/lines.yaml` (five to ten lines). Suit-O picks at random and will not repeat the same line twice in a row when it has another choice.

Per-event cooldowns and a global gap (`rate_limit.min_interval_seconds`) keep it from talking over every bullet. Aces, multi-kills, the bomb, and your death sit at priority 70 or above (`preempt_min_priority`). Those can speak during the gap and can interrupt a smaller line that is already playing.

A broke freeze (under rifle-plus-helmet money: 4100 on CT, 3700 on T) uses the low-buy lines instead of the generic round-start line.

## Remote speech later

`speech.backend: remote` is reserved for an HTTP TTS server on the home LAN (the machine in mind is a DGX Spark). Selecting it stops startup with an error. v1 contains no client for that server. When it exists, it should honor `speech.voice`, `speech.rate`, `speech.volume`, `speech.pitch`, `speech.pause_ms`, and `speech.emphasis`, and playback still has to be a local headset or speakers, still not voice chat.

## Troubleshooting

**No log lines when you play.** Confirm the cfg file is in `game\csgo\cfg\`, the name still starts with `gamestate_integration_`, and CS2 was restarted after the copy. The token in the cfg and in `config.yaml` must match. A mismatch is logged as `auth token mismatch`.

**Port already in use.** Change `server.port` and the `uri` in the cfg to the same new port, then restart both Suit-O and CS2.

**You hear nothing, but the log shows lines.** Check mute, the volume slider, and the output device. Press **Test voice** after choosing a playback device. On the Voice tab, **Preview** speaks the text box on that same device. A wireless headset can expose two outputs (game and chat) plus a microphone; pick a playback name, not the microphone. The Windows default is sometimes a different endpoint than the one you are wearing.

**It does not sound like Suit-O yet.** Open Voice Training, record the script in your own voice, and press **Build voice**. Suit-O then renders every stock line for that voice. On the Voice tab, pick `Clone: Suit-O` and press **Preview** to hear a live line. In a match you hear the rendered files. A line with no file yet uses the Windows voice. If the Voice Training tab says the optional packages are missing, install them with `python -m pip install -r requirements-voice.txt` and start the window again so the render can run.

**The desktop window opens and closes immediately.** Read `suit-o.log` in this folder. `pythonw` has no console, so startup errors are written there. A missing virtual environment is reported by the launcher itself.

**The voice list is empty or tiny.** Windows 10/11 often hides newer voices from classic SAPI. Install a speech voice under Settings → Time & language → Speech. Suit-O speaks with whatever SAPI can see.

**It talked, then went quiet.** Cooldowns are doing that on purpose. Death, bomb, and multi-kill lines can still break through. Lower `cooldowns` or `rate_limit.min_interval_seconds` if you want it chattier.

**Startup says the output device looks like a microphone or cable.** `speech.output_device` matched a mic, stereo mix, or virtual-cable name. Clear it, or set a headphone/speaker name. Suit-O will not play into a device that usually feeds voice chat.

**Startup says the push-to-talk key matches the CS2 voice key.** Change `ptt.keybind` or clear it. Leave `ptt.cs2_voice_key` set to the key you actually use in game so the check stays honest.

**You only want to develop on a machine without CS2.** `python -m suit_o.simulate` and `python -m pytest` are the whole loop. They stub speech and do not need the game or a sound device.
