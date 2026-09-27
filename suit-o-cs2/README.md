# Suit-O

Suit-O is a local companion for Counter-Strike 2. While you play, it listens to Valve's Game State Integration feed and speaks short, in-character lines into your headset: round starts, a broke buy, a plant, a multi-kill, your own death, the end of the match.

The voice is an original parody of a jittery corporate suit-assistant. He stammers, offers "Helpful tip:" advice nobody asked for, is proud of a useless "detective mode," gets huffy and threatens to report the developers when the economy is a shortcut, and treats every goodbye like a finale. The lines are written for Suit-O. They are not quotes from another game.

Suit-O v1 runs on your PC. It uses Windows' built-in speech synthesizer. It does not call an AI API, does not read the microphone, and does not send audio to voice chat.

## What it uses from the game

CS2 posts JSON to `http://127.0.0.1:3000` when you install the config file in this folder. Suit-O checks a shared auth token, then reacts to your own HUD state: your health, your money, your round kills, the round result, and whether the bomb was planted, defused, or exploded. Those are things you can already see or hear.

Bomb coordinates and weapon lists may arrive in the payload because the config asks for the `bomb` and `player_weapons` blocks. Suit-O never reads coordinates and never subscribes to other players. It does not keep your inventory. The one weapon fact it reads is the name of the item in your hand, so the lineup overlay can tell that you are holding a smoke. Ammo and the rest of the loadout are ignored, and that name is never spoken. A clutch (last player alive) is not detected, because that would need everyone else's alive state.

## Layout

| Piece | Role |
| --- | --- |
| `suit_o/gsi/` | Local HTTP server. Validates the token and queues payloads so speech cannot stall CS2. |
| `suit_o/events/` | Diffs snapshots into typed events. |
| `suit_o/lines/` | `LineProvider` chooses a line. v1 reads `lines/lines.yaml`. A future AI provider can replace this class without touching detection. |
| `suit_o/speech/` | `SpeechBackend` plays audio. v1 uses `pyttsx3` (SAPI). `remote` is a documented stub and is not implemented. |
| `config.yaml` | Shared settings: port, token, cooldowns, and the reserved push-to-talk key. This file stays in git. |
| `config.local.yaml` | Your settings: output device, volume, mute, voice tuning, and the lineup overlay. Git ignores it. |
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

   `Start Suit-O GUI.bat` does the same thing with `pythonw`. The window has four tabs.

   **Listener.** Shows whether the listener is up and how long it has been since CS2 last sent game state. Mute, volume, and the output device are saved to `config.local.yaml` (next to `config.yaml`, and not part of git). The first time Suit-O starts, settings you already changed in `config.yaml` — such as a JBL chat output device — are copied into that local file and those keys in `config.yaml` go back to the shared defaults, so **Update** can pull. Pick the playback device you actually want to hear. The list is Windows' speech outputs (SAPI), for example speakers, a headset earphone, a digital output, or a monitor. A headset often shows up twice — once for game audio and once for chat — and the Windows default is not always the one that makes a sound. Choose the endpoint, then press **Test voice**. Microphones are not listed, and Suit-O still refuses a microphone or virtual-cable name if one is typed into `speech.output_device`. **Update** runs `git pull --ff-only` in this checkout. If a requirements file changed, Suit-O reinstalls it and reloads. If you have local edits git would overwrite, the window says so and leaves the running copy alone. **Check for updates when Suit-O opens** does that same check at startup.

   **Voice.** Fine-tune the voice used for every in-game line. The picker lists installed Windows SAPI voices (blank in the config, shown as "Engine default", keeps the engine's own voice) and any voice you built on the Voice Training tab (`Clone: name`). Sliders set speaking rate (words per minute), pitch (-10 to 10), volume (the same slider as on the Listener tab), and an optional pause before each line (milliseconds). Emphasis is None, Mild, or Strong. **Preview** speaks the text box through the output device selected on the Listener tab, including slider positions you have not saved yet. **Save** writes the settings to `config.local.yaml` and uses them for every in-game line. Saving a cloned voice sets `speech.backend` to `clone`. **Reset to defaults** puts back rate 185, pitch 0, volume 0.85, no pause, no emphasis, and the engine default voice, and saves that immediately. Closing the window saves the last saved tuning, not an unsaved draft. Volume is the exception: moving either volume slider saves it.

   **Voice Training.** Record a short script in your own voice (or someone who agreed), then press **Build voice**. That stores a profile under `voices/` (gitignored) and adds it to the Voice tab. See [Voice cloning](#voice-cloning) below. The tab tells you if the optional packages are missing, and whether synthesis will use NVIDIA CUDA or the CPU.

   **Lineups.** Import your own smoke screenshots and show them in a small overlay while you play. See [Smoke lineups](#smoke-lineups) below.

7. The console listener still works if you want a terminal instead of the window. Double-click `Start Suit-O.bat`, or:

   ```powershell
   python -m suit_o
   ```

   The log line `GSI endpoint ready at http://127.0.0.1:3000/` means it is waiting. Join a match. On a new round you should see a line in the log and hear it. Leaving `speech.output_device` blank uses the Windows default playback device. To target one device by name, set `output_device` to part of its playback name, such as `Headphones`. Use the speaker or headphone name, not the microphone name.

Optional voice settings. Saving them from the window writes `config.local.yaml`; the same keys in `config.yaml` are the shared defaults. These six are not tied to SAPI, so a future custom or cloned voice (a remote TTS server) can reuse the same panel and the same keys:

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

- In the desktop window, press **Mute**. Press **Unmute** to hear lines again. The choice is saved in `config.local.yaml`.
- In the console listener, type `m` and press Enter. Type `m` again to unmute. Type `q` and Enter to quit. Console mute lasts for that run; it does not rewrite `config.yaml`.
- Or set `mute: true` in `config.local.yaml` before starting. A `mute` value still sitting in `config.yaml` is moved to the local file on the next launch.
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

## Smoke lineups

While you hold a smoke grenade, Suit-O can show one of your lineup screenshots in a small window at the corner of the screen (top-right by default). The window is a separate always-on-top surface. It does not read game memory, inject code, hook DirectX, or send keystrokes or mouse input into CS2. The only input it uses is the Game State Integration feed you already installed: the map, your team (T or CT), whether you are alive, the round phase, and the name of the weapon in your hand.

Run CS2 in **borderless windowed** or **windowed** mode so a normal desktop window can sit on top of the game. Fullscreen exclusive mode will cover it. Some third-party leagues and anti-cheats, including FACEIT, restrict overlays. This one is meant for Valve matchmaking and casual play.

The card hides when the smoke is not in your hand, when you are dead, or when the round is over. A hotkey can hide it even while you are holding a smoke, and show it again the next time the trigger matches. Two more hotkeys cycle to the next or previous lineup. The defaults are `ctrl+shift+right`, `ctrl+shift+left`, and `ctrl+shift+h`. Saving them writes `config.local.yaml`. They must not be the same chord as `ptt.cs2_voice_key` or the reserved `ptt.keybind`. On Windows they are registered with the system so they work while CS2 is focused. They only change this overlay. They are not forwarded to the game. On Windows the overlay is click-through, so mouse clicks land on the game underneath.

A pack lineup shows the stand photo and the aim photo side by side. The caption is the stand spot, the aim spot, and the throw type (for example `T ramp → Window (jumpthrow)`). **Smokes only**, on by default, hides flash, molotov, and HE cards from that overlay. Folder screenshots are smokes. The overlay still appears only while a smoke is in your hand.

No lineup images are shipped. Add your own PNGs:

```text
lineups/<map>/<t|ct>/<name>.png
lineups/<map>/<t|ct>/<name>.txt    optional caption; otherwise the filename is the caption
lineups/<map>/<t|ct>/order.txt     optional order, one filename per line
```

Use the CS2 map id, such as `de_dust2` or `de_mirage`. A short folder name (`dust2`) is also accepted. `t` and `ct` are the two sides. Empty folders for the current premier maps are already there. The **Lineups** tab can import PNGs for a map and side, rename them, set a caption, reorder them, and preview them. It also saves the card width, opacity, corner, monitor, and the smokes-only filter. Images you add stay on your machine; png and caption files under `lineups/` are gitignored.

**Import pack** accepts a folder or a `.zip` in the version 1 format described by `lineups/pack.schema.json`. `lineups/example-pack/lineups.json` is an example with no photos. Each lineup has an id, map, side (`T` or `CT`), grenade (`smoke`, `flash`, `molotov`, or `he`), stand spot, aim spot, throw type, and paths to a stand photo and an aim photo. Suit-O checks the file, then copies it into `lineup-data/` (gitignored). Importing the same id again replaces that lineup and leaves the others. Those images belong to their creators and stay on your machine; do not commit them. A `setpos` string in the pack is practice-server text only. Suit-O never sends it to CS2.

## Speech log

Every line Suit-O speaks is written to the Listener tab with a local time (`HH:MM:SS`), and appended to a daily file in `logs/` (`speech-YYYY-MM-DD.jsonl`). A line held back by mute or a cooldown is written too, marked `skipped (mute)` or `skipped (cooldown)`. Each file row has the time, the event, the line, that status, the map and round number when CS2 has sent them, and the voice name (or `engine default`). **Open log folder** opens `logs/`. **Copy** puts the lines currently in the window on the clipboard. `logs.keep_days` (14 by default) deletes a daily file once it is that many days old. The folder is gitignored. The game-state token is not written there.

## Updates without closing the window

Leave the desktop window open. Suit-O watches `config.yaml`, `config.local.yaml`, `lines/`, `voices/`, and `lineups/`. A valid change applies immediately, including during a live round: volume, the output device, voice tuning, mute, stock lines, cloned-voice files, and lineup images. That reload does not stop the game-state listener. If a file is invalid, the previous settings stay in effect and the error is written in the event log.

A change under `suit_o/` (for example after **Update**) restarts the window in place. Several files saved together count as one restart. Suit-O stops the game-state listener and frees port 3000, then opens again on the same tab with the same window position. Mute is kept. A short **Reloaded** notice confirms it. A restart waits if you are in a live round and not in the menu. The window shows **Update pending** until the round ends or you return to the menu, then reloads. Freezetime, a finished round, warmup, and the menu do not wait.

**Update** on the Listener tab fetches `origin/main` and reads that commit's check runs from the public GitHub API. It applies the commit only when the Suit-O pytest check succeeded. A failed check, or a check that is still running or missing, stops the update and the status line says why. Nothing is pulled in that case. When the check passed, **Update** runs `git pull --ff-only`. When `requirements.txt`, `requirements-dev.txt`, or `requirements-voice.txt` changed, it runs `python -m pip install -r` on those files, then restarts. If the pull is already current, nothing restarts. If local edits would be overwritten, or the histories have diverged, the status line says what to do and Suit-O keeps running. Personal settings in `config.local.yaml` do not block the pull. **Update** also waits out a live round, with the same **Update pending** notice, and does not pull until you are in the menu or the round is no longer live.

Pushes to `main` run that pytest job on `windows-latest` (`.github/workflows/suit-o-tests.yml`).

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

**Startup says the output device looks like a microphone or cable.** `speech.output_device` matched a mic, stereo mix, or virtual-cable name. Clear it in `config.local.yaml` (or in `config.yaml` if you have not launched since editing it), or set a headphone/speaker name. Suit-O will not play into a device that usually feeds voice chat.

**Update says a file has local edits.** Those edits are in a tracked file, usually `config.yaml`. Suit-O settings belong in `config.local.yaml`. The first launch moves output device, volume, mute, voice tuning, and lineup settings there. Commit or stash anything else, then press **Update** again.

**Update says tests failed or are still running.** Suit-O will not apply that commit. Wait until the Suit-O pytest check on GitHub is green, then press **Update** again.

**The window says Update pending during a match.** A code reload or **Update** is waiting so the game-state listener stays up through the live round. It runs when you leave the round or return to the menu. Settings and lineup files can still change while you play.

**The window says it kept the previous settings.** The file you just saved does not parse. Suit-O is still using the last good config and lines. The log line is the reason.

**Startup says the push-to-talk key matches the CS2 voice key.** Change `ptt.keybind` or clear it. Leave `ptt.cs2_voice_key` set to the key you actually use in game so the check stays honest. A lineup hotkey that uses that same chord is refused for the same reason.

**The smoke overlay never appears.** Hold a smoke on a map that has PNGs for your side, and be alive before the round ends. CS2 needs to be borderless or windowed, not fullscreen exclusive. Check **Overlay enabled** on the Lineups tab. If you pressed the hide hotkey, press it again. FACEIT and similar clients may block any overlay; use this for Valve matchmaking and casual games.

**You only want to develop on a machine without CS2.** `python -m suit_o.simulate` and `python -m pytest` are the whole loop. They stub speech and do not need the game or a sound device.
