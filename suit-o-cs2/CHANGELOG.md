# Changelog

All notable changes to Suit-O are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Dates are Pacific Time. Each entry lists the short commit hash.

New notes go under `## [Unreleased]`. Do not add a heading for today's date. Under Unreleased, each category appears once, in the order Added, Changed, Removed, Fixed. Add a new bullet under that heading instead of starting another one. Every push to `main` updates this file in that same commit. After the Suit-O tests pass on `main`, a release step moves Unreleased into `## [x.y.z] - YYYY-MM-DD`, writes that version into `pyproject.toml`, and tags `suit-o-vX.Y.Z`. Dated version headings are created only by that release step. It skips the cut when Unreleased is empty. The Update button only fast-forwards to the newest commit on main whose `suit-o-tests.yml` run passed. It does not commit or tag.

## [Unreleased]

## [0.25.0] - 2026-09-28

### Added

- An Installations button at the top of the window, shown only while something optional is missing. It opens a checklist: chat brain (Ollama and llama3.2), push-to-talk, voice training, and recording clean-up. Ticked parts install in the background with progress in the window, and their models download during the install. (`d748fa5`)
- `Install Suit-O.bat` sets Suit-O up on Python 3.11, which voice training needs. It installs Python 3.11 when it is missing, rebuilds the venv, keeps the optional parts this PC had, and reopens Suit-O. Installations runs it from Move to Python 3.11. Settings and voices are not touched. (`d748fa5`)

### Changed

- Messages about a missing optional part point to Installations. (`d748fa5`)

## [0.24.0] - 2026-09-28

### Changed

- The Update button sits at the top of the window, to the right of What's new. (`e5a9c1b`)

### Fixed

- Reloading after an update no longer opens a console window on Windows. (`e5a9c1b`)

## [0.23.2] - 2026-09-28

### Fixed

- Voice Training uploads and Clips no longer say ffmpeg is missing. The ffmpeg that Suit-O uses now installs with the base requirements, so Update adds it. (`35baaf1`)

## [0.23.1] - 2026-09-27

### Fixed

- Update no longer opens Command Prompt windows. git, pip, and ffmpeg run with their console hidden on Windows. (`883edbf`)

## [0.23.0] - 2026-09-27

### Added

- A mic light next to Hold to talk on the Chat tab. It turns green and reads Listening while the push-to-talk key or button is held, and goes back to grey on release. (`e77ae77`)

## [0.22.1] - 2026-09-27

### Fixed

- Push-to-talk warm-up checks whether a round is live before it loads the speech or chat model, and unloads if the round goes live while that load is still running, so the models do not stay in memory for the round. (`de53870`)

## [0.22.0] - 2026-09-27

### Changed

- Chat with a cloned voice keeps the voice model loaded between sentences and renders the next sentence while the current one plays, so there is no reload pause after each sentence. The model is released when chat goes idle or a round goes live. (`36d00ec`)
- Push-to-talk sends what it heard when you let go. Pressing the key starts loading the speech and chat models while you talk, and transcription no longer blocks the window. If Suit-O is still answering, the text waits in the box. (`36d00ec`)
- Chat keeps the Ollama model loaded between messages, caps how long a reply can run, and sends only the last 16 messages, so a long chat does not keep getting slower. (`36d00ec`)
- The chat persona adds the suit assistant's quick mood swings, guilt trips for a nice review, and jokes about the developers and menus, in original wording. (`36d00ec`)

## [0.21.0] - 2026-09-27

### Changed

- Four stock lines, for the menu greeting, idle chat, a kill, and an ace, are reworded so they do not match the game's dialogue. (`e9a613c`)

## [0.20.0] - 2026-09-27

### Added

- Halftime, a match win, and which side planted the bomb, using the side, score, and intermission the game already sends. (`b77296e`)

### Changed

- Stock lines for the menu, idle chat, round start, a kill, an ace, low health, death, a bomb plant, and the end of a round or match. The last-alive line shares the enemy bomb plant, because own-player data has no alive teammate count. (`b77296e`)

## [0.19.17] - 2026-09-27

### Fixed

- The chat panel test expects Hold to talk to be enabled when faster-whisper is installed, and disabled when it is not. (`afec94b`)

## [0.19.16] - 2026-09-27

### Fixed

- Git ignores `config.local.yaml.*.bak`, so a backup of an unreadable local config is not committed. (`a0c7ab5`)

## [0.19.15] - 2026-09-27

### Fixed

- A saved GSI key is copied into every CS2 config that still has the sample key. A config that already has a different key is left unchanged, and the window says so. (`f9fdb3d`)

## [0.19.14] - 2026-09-27

### Fixed

- The README says to start Suit-O once before restarting CS2, so the game picks up the GSI key. (`5504bd2`)

## [0.19.13] - 2026-09-27

### Fixed

- `config.local.yaml` is written only when a setting changes. A file that cannot be read is copied aside and left in place, and the window says so. (`fbecf8a`)

## [0.19.12] - 2026-09-27

### Fixed

- Update no longer installs `requirements-dev.txt`. That file stays for tests and for CI. (`46fa874`)

## [0.19.11] - 2026-09-27

### Fixed

- Only one cloned-voice render runs at a time. A second request is queued on that render instead of starting another. (`a7d5817`)

## [0.19.10] - 2026-09-27

### Fixed

- Reloading lines keeps each line's cooldown, so a line that just played is not spoken again immediately. (`cec3a06`)

## [0.19.9] - 2026-09-27

### Fixed

- Update reports an error when the checkout is not the commit whose tests were checked. (`234fdb1`)

## [0.19.8] - 2026-09-27

### Fixed

- Restarting Suit-O on Windows keeps working when Python or the config path contains a space. (`738012c`)

## [0.19.7] - 2026-09-27

### Fixed

- A Clips vocal-separation or speaker-tag error is shown in the window. The callback no longer crashes by reading the exception after the handler has finished. (`8d79263`)

## [0.19.6] - 2026-09-27

### Fixed

- Suit-O keeps an existing GSI key. A new key is saved only after CS2's gamestate config was written, including a Steam library that is not on the default drive. If that file cannot be found, the window says so. (`58bd8a3`)

## [0.19.5] - 2026-09-27

### Fixed

- A failed window update is logged and the queue keeps running, so Update, chat, and Voice Training can still reach the window. (`e1309e6`)

## [0.19.4] - 2026-09-27

### Fixed

- Update follows the newest main commit whose Suit-O tests passed. A release cut has no run until the release job starts one, so Update no longer stops on that untested commit. (`0782781`)

## [0.19.3] - 2026-09-27

### Fixed

- The Lineups detail panel keeps the stand and aim pictures at a fixed size. Notes stay in the pack and are not shown there. A Source link opens the lineup's URL when one is set. (`7080e63`)

## [0.19.2] - 2026-09-27

### Fixed

- A lineup pack with `null` in an optional field imports. `notes`, `source_url`, `source_timestamp`, `second_source_url`, and `verified_by_second_source` treat `null` the same as a missing key. (`6dfd1ea`)
- A chat reply no longer returns from a `finally` block, which pytest warned about. (`6dfd1ea`)

## [0.19.1] - 2026-09-27

### Fixed

- Suit-O 0.19.0 lists each changelog category once, in the order Added, Changed, Removed, Fixed. (`cc684dc`)

## [0.19.0] - 2026-09-27

### Added

- Lineup photos can be JPEG or WebP as well as PNG. Pillow is part of the base install. (`747417c`)
- The first launch writes a random GSI token into `config.local.yaml` and, when the CS2 cfg is already outside the repo, into that file. The sample token stays in git. (`747417c`)

### Changed

- Voice synthesis uses NVIDIA CUDA or AMD ROCm when that PyTorch build is available, and the CPU otherwise. DirectML is detected and left unused, because Chatterbox does not run on it. The tab names the stack and not the graphics card. (`f7c802e`)
- The README and tests no longer name a personal headset or a home machine. Personal settings stay in gitignored `config.local.yaml`. (`3715752`)

### Removed

- The `suit-o.log` file. Startup deletes a leftover log. Messages stay in the window, or on the console when you start Suit-O from a terminal. (`6440bbb`)

### Fixed

- A test that opens a Tk window skips itself when Tcl cannot create one, including a GitHub runner with no display. (`2288d7e`)
- Startup closes a leftover log handler before it deletes `suit-o.log`, so Windows can remove the file. (`2288d7e`)
- The Windows test run installs `tzdata` so the release step can date a version in Pacific time. (`2288d7e`)
- Voice pre-rendering waits while GSI says the round phase is live, then continues. (`747417c`)
- A voice cache file that is incomplete or unreadable uses the Windows voice. (`747417c`)
- Window updates from worker threads run on the main thread. (`747417c`)
- A broken PyTorch install greys out Voice Training and Clips instead of stopping the window from opening. (`747417c`)
- Update reinstalls optional voice, clips, and chat requirements only when this PC already has them. (`747417c`)
- The menu greeting no longer repeats when a voice file is written, or when the window restarts in place. (`2326a59`)
- Update fast-forwards to the exact commit whose `suit-o-tests.yml` run passed. A newer commit that landed after that check is not installed. (`0127af3`)

## [0.18.0] - 2026-09-27

### Added

- The window shows the Suit-O version from `pyproject.toml`. After Update pulls a newer build, What's new lists the changelog sections between the version you had and the one you just got. The same panel opens from a button any time. Versions are cut on `main` after tests pass, not by the Update button. (`c73331c`)

## [0.17.0] - 2026-09-27

### Added

- A changelog of Suit-O changes since the first commit. (`5039067`)

## [0.16.0] - 2026-09-27

### Added

- Optional cleanup on those short uploads. Separate vocals and Pick a speaker run the same Demucs and pyannote passes as Clips, before the clip is saved. The checkboxes stay grey until those optional packages are installed, and speaker tags also need a Hugging Face token. (`f3f0cf0`)

## [0.15.0] - 2026-09-27

### Added

- Push-to-talk on the Chat tab. The hotkey defaults to F8, which is not CS2's voice key. Change it on the tab; it is saved in `config.local.yaml`. If it matches your CS2 voice bind, the tab warns you. Hold to talk stays grey, with an install hint, until the optional chat requirements are installed. The speech model is released with the chat model when chat is idle or a round goes live. (`b6d087a`)

## [0.14.0] - 2026-09-27

### Added

- A Chat tab for talking to Suit-O outside a live round. Type a message. He answers in text and in the voice selected on the Voice tab, including a cloned voice, through the output device on the Listener tab. A live round shows "paused during match" and does not call the model or speak. The menu, warmup, and the time between matches stay open. The tab notes that live chat with CS2 open needs roughly 7 to 9 GB of VRAM. After chat has been idle for about a minute, or as soon as a round goes live, Suit-O asks Ollama to unload the model. (`f0d43c8`, `6f51379`)

## [0.13.0] - 2026-09-27

### Added

- Voice Training accepts recordings you already have. Add files, or drop them on the tab: wav, mp3, m4a, flac, ogg, and video. A file under about 30 seconds becomes a normalized mono clip in the selected voice's library, with a transcript you can edit. A longer file opens in Clips so you can cut it. The tab shows total usable duration, and Build voice uses those clips. (`5a93d0b`)

## [0.12.1] - 2026-09-27

### Fixed

- Lineup packs that include extra fields, such as notes and source links, import instead of failing. Notes and a source link show on the lineup. Tests no longer read or write your real `config.local.yaml`. (`e6e4749`)

## [0.12.0] - 2026-09-27

### Added

- A Clips page on Voice Training for one long take. Open a recording, view the waveform, set in and out points, and save clips into that voice's library. Auto-split finds speech by silence. Optional vocal separation and speaker tags can clean the take first. (`203a3f9`, `81bae65`, `35c762c`)

## [0.11.0] - 2026-09-27

### Changed

- The lineup overlay follows the grenade in your hand, not only smokes. You can filter a pack by map, grenade, and status. (`3d46ea0`)

## [0.10.0] - 2026-09-27

### Added

- A greeting in the main menu about queueing Premier, once per visit, with a switch to turn it off. Opening the console on the menu does not greet you again. (`30ab137`, `80b04fa`)

## [0.9.0] - 2026-09-27

### Added

- An activity log on the Listener tab. It shows spoken lines, skipped lines, game events, and refused game-state posts, without the auth token. The log stays in memory. An in-place restart carries the lines across and then deletes the handoff. (`47bf28d`, `262040c`, `5611a27`)

### Removed

- The daily speech-log file. Those lines live in the window instead. (`e27c761`, `262040c`)

## [0.8.0] - 2026-09-27

### Added

- Lineup packs you keep on this PC, and an Update button that runs `git pull --ff-only` when a GitHub check named pytest looks successful. That pull can still include a newer commit than the one the check covered. (`7fd25ea`)

## [0.7.1] - 2026-09-27

### Fixed

- The "check for updates when Suit-O opens" checkbox crashed the window before it appeared. (`58847ad`)

## [0.7.0] - 2026-09-27

### Added

- Reload without closing the window. Edits to config, lines, voices, and lineups apply in place. A code change restarts the window once, on the same tab, and waits out a live round. Personal settings live in gitignored `config.local.yaml`, so an update is not blocked by your headset or volume. (`dec77ba`)

## [0.6.0] - 2026-09-26

### Added

- A smoke lineup overlay. It shows a card you supply while a smoke is in your hand, and hides when you are dead or the round is over. Its hotkeys only change that window. (`77801e5`)

## [0.5.0] - 2026-09-26

### Added

- Pre-rendered lines for a cloned voice. A match plays those files and uses the Windows voice only when a file is missing. Live synthesis is for preview, so a match does not keep the voice model on the GPU. (`0d90c2a`)

## [0.4.0] - 2026-09-26

### Added

- Voice Training. Record a short original script and build a cloned voice on this PC. The cloning packages stay optional. (`67885c7`)

## [0.3.0] - 2026-09-26

### Added

- A Voice tab for the installed Windows voice: which voice, rate, pitch, volume, pause, and emphasis. (`1380b0d`)

## [0.2.0] - 2026-09-26

### Added

- A desktop window with mute, volume, a playback-device picker, a test line, and a scrolling event log. `python -m suit_o.gui` opens it. (`3514d1c`)

## [0.1.0] - 2026-09-26

### Added

- Suit-O, a local Counter-Strike 2 companion. It listens on your PC for the game's own state feed and speaks original lines about your match: round starts, a broke buy, a plant, a kill, your death, the end of the match. Playback stays on a headset or speakers. (`8db45be`)
