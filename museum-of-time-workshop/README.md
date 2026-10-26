# Museum of Time Workshop

Desktop timeline editor for Museum of Time exhibits, and the first section of the admin interface. v0 stitches storyboard frames with ffmpeg. It does not call a paid video API, synthesize voiceover, sync to the cloud, or share a session between people.

## Requirements

- PHP 8.3 with `mbstring`, `xml`, `curl`, `sqlite`, `pdo_sqlite`, `zip`, `gd`, `bcmath`, and `intl`
- Composer 2
- Node.js 22 and npm
- SQLite
- ffmpeg and ffprobe on `PATH`
- A DejaVu or Liberation sans font (Debian/Ubuntu: `fonts-dejavu-core`) so burned-in plaque and stamp text can render

`composer.json` sets `policy.advisories.block` to false so Composer can install the requested Laravel 11 line, which current Composer security advisories flag.

## Run the admin interface

From `museum-of-time-workshop/`:

```bash
composer install
cp .env.example .env
php artisan key:generate
touch database/database.sqlite
php artisan migrate
php artisan storage:link
npm install
npm run build
php artisan workshop:seed-gala
```

`.env.example` already uses SQLite and the database queue. Real provider keys stay empty. `VIDEO_PROVIDER` defaults to `fake`.

Then start the app and a queue worker. `composer dev` runs both, plus Vite and the log tail:

```bash
composer dev
```

Or separately:

```bash
php artisan serve
php artisan queue:work --tries=1
```

Open the URL `artisan serve` prints. The editor is `/`. Placeholders live at `/exhibits`, `/wings`, and `/assets`.

`workshop:seed-gala` is idempotent. It slices `fixtures/gala_arrest_storyboard.jpg` into six shots on the Gala Arrest exhibit (wing Unit 14, hall Main Hall) and pins the locked character Tung to each shot.

## Desktop window

NativePHP is installed as a Composer package. Config is `config/nativephp.php`. The updater is off. The window opens only when you run the native command, not from the test suite.

```bash
php artisan native:install
composer native:dev
```

`composer native:dev` starts `php artisan native:run` and the Vite dev server. `native:install` downloads Electron, so CI does not run it. `composer install` does not either. `composer update` does, via `post-update-cmd`.

## Export

The Export button queues two jobs on the database driver:

- Episode, 16:9, aimed at 3–4 minutes. Outside that range the job records a warning.
- Shorts, 9:16, 45–60 seconds, split only on shot boundaries. Each short burns in `Museum of Time · {Wing} · {Exhibit} · Short N of M`.

Plaque cues are burned into the picture. Narration cues become a subtitle track. There is no voiceover audio. A plaque on a shot tagged `invented` is skipped and reported as a warning.

`FakeProvider` builds each shot with ffmpeg: a Ken Burns move when the shot has one frame, or a crossfade into the next shot's frame. `Runway` and `Kling` are registered and off. Enabling them still does not send HTTP. They throw until a real client exists.

Plaque lines and the short stamp are written to temporary text files and drawn with `drawtext=textfile` and `expansion=none`, then those files are removed. A shot with no frame is refused for render and export.

## Scenes

`+ Add scene` appends a draft shot (empty frame, blank prompt, model FLUX, 4 seconds, truth tag invented). `Insert after` puts one after the selected shot and renumbers. Upload a frame from the inspector before rendering that shot.

The same insert goes through `App\Workshop\AddScene` for the buttons, the command, and scene packs:

```bash
php artisan workshop:add-scene --exhibit=gala-arrest --after=3 --prompt="..." --duration=4 --truth=invented --frame=frames/ring.jpg --narration="..." --plaque="..."
```

The command prints the new shot as JSON. `--after` is a shot id when one matches, otherwise an order number. Omit it to append.

A scene pack is a JSON file. Frame paths are relative to that file. See [docs/scene-pack.md](docs/scene-pack.md).

```bash
php artisan workshop:import-scenes path/to/pack.json
```

The editor's Import scenes button uses the same file. A pack dropped in the inbox (`WORKSHOP_INBOX`, default `storage/app/inbox`) shows up as pending. Approve adds the scenes. Reject leaves the sequence unchanged. Invalid JSON or a missing frame is reported and is not imported.

## Sections

`config/sections.php` is the registry. Each section is a module under `app/Sections/<Name>` with its own `routes.php`, Livewire components, and a left-rail entry. Shared records are `Wing`, `Hall`, `Exhibit`, `Character`, and `Asset` (with a `TruthTag`). A `Sequence` belongs to an `Exhibit`.

| Section | Route | Status |
| --- | --- | --- |
| Editor | `/` | Timeline, inspector, characters, export |
| Exhibits | `/exhibits` | Placeholder |
| Wings & Halls | `/wings` | Placeholder |
| Assets | `/assets` | Placeholder |

## Tests

```bash
composer test
```

That runs Pest. Feature tests use an in-memory SQLite database. The export test renders the seeded gala with `FakeProvider` and checks both MP4s, so the machine running tests needs ffmpeg and a DejaVu font. GitHub Actions runs the same suite from `.github/workflows/workshop-tests.yml` when this folder changes.
