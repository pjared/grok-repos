# Changelog

All notable changes to Suit-O are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
Dates are Pacific Time. Each entry lists the short commit hash.

New notes go under `## [Unreleased]`. Every push to `main` updates this file in that same commit. After the Suit-O tests pass on `main`, a release step moves Unreleased into `## [x.y.z] - YYYY-MM-DD`, writes that version into `pyproject.toml`, and tags `suit-o-vX.Y.Z`. It skips the cut when Unreleased is empty. The Update button only pulls a tested build. It does not commit or tag.

## [Unreleased]

### Changed

- The README and tests no longer name a personal headset or a home machine. Personal settings stay in gitignored `config.local.yaml`. (`3715752`)

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

- Lineup packs you keep on this PC, and an Update button that pulls `main` only after the Suit-O tests for that commit have passed. (`7fd25ea`)

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
