# grok-repos

Independent projects live in their own folders. Each project has its own dependencies and README.

## Projects

| Folder | Description | How to run |
| --- | --- | --- |
| [`suit-o-cs2/`](suit-o-cs2/) | Suit-O, a local Counter-Strike 2 companion that speaks original in-character lines into your headset from official Game State Integration. | On Windows, from `suit-o-cs2/`: create a virtualenv, `pip install -r requirements.txt`, install the GSI config, then double-click `Start Suit-O GUI.vbs` or run `python -m suit_o.gui`. `python -m suit_o` is the console listener. Full steps are in [`suit-o-cs2/README.md`](suit-o-cs2/README.md). |
| [`museum-of-time/`](museum-of-time/) | Museum of Time exhibit archive: halls, scripts, stills, and timeline wireframes. Rendered video and audio stay outside git. | Read [`museum-of-time/README.md`](museum-of-time/README.md). |
| [`museum-of-time-workshop/`](museum-of-time-workshop/) | Museum of Time admin interface. The first section is a desktop timeline editor that stitches storyboard frames with ffmpeg. | From `museum-of-time-workshop/`: `composer install`, copy `.env.example` to `.env`, `php artisan key:generate`, `php artisan migrate`, `npm install && npm run build`, `php artisan workshop:seed-gala`, then `composer dev`. Full steps are in [`museum-of-time-workshop/README.md`](museum-of-time-workshop/README.md). |
| `super-position/` | An s&box game. Coming later. | Not in the repo yet. |
