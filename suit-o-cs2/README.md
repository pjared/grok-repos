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

6. Set the headset as the **default playback device** in Windows sound settings if you want Suit-O in that headset. Leaving `speech.output_device` blank uses that default. To target one device by name, set `output_device` to part of its playback name, such as `Headphones`. Use the speaker/headphone name, not the microphone name.

7. Start Suit-O and leave the window open while you play:

   ```powershell
   python -m suit_o
   ```

   The log line `GSI endpoint ready at http://127.0.0.1:3000/` means it is waiting. Join a match. On a new round you should see a line in the log and hear it.

Optional voice settings in `config.yaml`:

- `speech.voice`: part of an installed voice name (`David`, `Zira`, ...). Blank keeps the default SAPI voice. These are the voices Windows already has. Suit-O does not clone a person's voice.
- `speech.rate`: words per minute (default 185).
- `speech.volume`: `0.0` to `1.0`.

## Mute

- In the Suit-O window, type `m` and press Enter. Type `m` again to unmute. Type `q` and Enter to quit.
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

`speech.backend: remote` is reserved for an HTTP TTS server on the home LAN (the machine in mind is a DGX Spark). Selecting it stops startup with an error. v1 contains no client for that server. When it exists, playback still has to be a local headset or speakers, still not voice chat.

## Troubleshooting

**No log lines when you play.** Confirm the cfg file is in `game\csgo\cfg\`, the name still starts with `gamestate_integration_`, and CS2 was restarted after the copy. The token in the cfg and in `config.yaml` must match. A mismatch is logged as `auth token mismatch`.

**Port already in use.** Change `server.port` and the `uri` in the cfg to the same new port, then restart both Suit-O and CS2.

**You hear nothing, but the log shows lines.** Check `mute`, `speech.volume`, and the Windows default playback device. The headset has to be a playback device, not the recording side of the same headset.

**The voice list is empty or tiny.** Windows 10/11 often hides newer voices from classic SAPI. Install a speech voice under Settings → Time & language → Speech. Suit-O speaks with whatever SAPI can see.

**It talked, then went quiet.** Cooldowns are doing that on purpose. Death, bomb, and multi-kill lines can still break through. Lower `cooldowns` or `rate_limit.min_interval_seconds` if you want it chattier.

**Startup says the output device looks like a microphone or cable.** `speech.output_device` matched a mic, stereo mix, or virtual-cable name. Clear it, or set a headphone/speaker name. Suit-O will not play into a device that usually feeds voice chat.

**Startup says the push-to-talk key matches the CS2 voice key.** Change `ptt.keybind` or clear it. Leave `ptt.cs2_voice_key` set to the key you actually use in game so the check stays honest.

**You only want to develop on a machine without CS2.** `python -m suit_o.simulate` and `python -m pytest` are the whole loop. They stub speech and do not need the game or a sound device.
