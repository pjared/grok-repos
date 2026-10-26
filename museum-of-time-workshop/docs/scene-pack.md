# Scene pack

A scene pack is a JSON file, or a `.zip` of that JSON plus its frames. Frame paths are relative to the JSON file and must stay inside its directory. `workshop:import-scenes` adds a JSON pack immediately. The editor's Import scenes button takes a `.zip` and leaves it pending in the inbox, the same approval gate as a pack dropped in the inbox folder.

```json
{
  "exhibit": "gala-arrest",
  "scenes": [
    {
      "title": "The ring",
      "after_order": 3,
      "prompt": "Iole turns the ring in the light.",
      "duration": 4,
      "truth": "invented",
      "model": "FLUX",
      "frame": "frames/ring.jpg",
      "narration": "She kept the ring.",
      "voice": "MoT Docent 3",
      "plaque": "Iole's arrest: 1923, 50%"
    }
  ]
}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `exhibit` | yes | Exhibit slug, name, or id. The pack is added to that exhibit's latest sequence. |
| `scenes` | yes | One or more scene objects, applied in order. |
| `title` | no | Timeline label. Defaults to `New scene`. |
| `after_id` | no | Shot id to insert after. Omit both placement fields to append. |
| `after_order` | no | Order number to insert after. Each scene sees the order numbers left by the scenes before it. Do not set this together with `after_id`. |
| `prompt` | no | Defaults to an empty prompt. |
| `duration` | no | Seconds. Defaults to 4. Minimum 0.2. |
| `truth` | no | `documented`, `legend`, or `invented`. Defaults to `invented`. |
| `model` | no | Defaults to `FLUX`. |
| `frame` | no | Image path relative to the pack file (`jpg`, `jpeg`, `png`, `webp`, or `gif`). A missing file, a `..` path, an absolute path, or a symlink that leaves the pack is an error. Omit for an empty frame, which cannot be rendered or exported until a frame is added. |
| `narration` | no | Narration cue on the new shot. |
| `voice` | no | Voice label for the narration cue. |
| `plaque` | no | Plaque cue on the new shot. |

`after` is not accepted. Use `after_id` or `after_order`.

`php artisan workshop:add-scene` adds one scene with the same fields as options (`--exhibit`, `--after-id`, `--after-order`, `--prompt`, `--duration`, `--truth`, `--frame`, `--narration`, `--plaque`) and prints the shot as JSON. Pass only one of `--after-id` and `--after-order`.

A zip contains one JSON file (`pack.json`, or the only `.json` in the archive) and the frames it names. Paths in the archive stay inside the zip. The editor extracts that zip into the inbox and lists it as pending. Approve adds the scenes. Reject does not.

Inbox packs use `WORKSHOP_INBOX` (default `storage/app/inbox`). Put a JSON file there with its frame files beside it, or put a `.zip` there. The editor lists the pack as pending. A pack that is not valid JSON, or that names a frame that is not in the pack, is shown with that error and cannot be approved.
