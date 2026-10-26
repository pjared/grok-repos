# Scene pack

A scene pack is a JSON file. Frame paths are relative to that file and must stay inside its directory. `workshop:import-scenes` and the editor's Import scenes button add the scenes immediately. A pack dropped in the inbox waits until it is approved.

```json
{
  "exhibit": "gala-arrest",
  "scenes": [
    {
      "title": "The ring",
      "after": 3,
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
| `after` | no | Shot id on the sequence, if one matches, otherwise that order number. Omit to append. Each scene sees the order numbers left by the scenes before it. |
| `prompt` | no | Defaults to an empty prompt. |
| `duration` | no | Seconds. Defaults to 4. Minimum 0.2. |
| `truth` | no | `documented`, `legend`, or `invented`. Defaults to `invented`. |
| `model` | no | Defaults to `FLUX`. |
| `frame` | no | Image path relative to the pack file (`jpg`, `jpeg`, `png`, `webp`, or `gif`). A missing file is an error. Omit for an empty frame, which cannot be rendered or exported until a frame is added. |
| `narration` | no | Narration cue on the new shot. |
| `voice` | no | Voice label for the narration cue. |
| `plaque` | no | Plaque cue on the new shot. |

`php artisan workshop:add-scene` adds one scene with the same fields as options (`--exhibit`, `--after`, `--prompt`, `--duration`, `--truth`, `--frame`, `--narration`, `--plaque`) and prints the shot as JSON.

Inbox packs use `WORKSHOP_INBOX` (default `storage/app/inbox`). Put the JSON file there with its frame files beside it, using the same relative paths. The editor lists the pack as pending. Approve adds the scenes. Reject does not. A pack that is not valid JSON, or that names a frame that is not in the pack, is shown with that error and cannot be approved.
