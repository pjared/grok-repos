<?php

return [
    /*
    | Drop a scene pack JSON file in this folder (with its frames beside it).
    | The editor lists it as pending. Nothing is added until it is approved.
    */
    'inbox' => env('WORKSHOP_INBOX') ?: storage_path('app/inbox'),

    /*
    | Rendered picture and sound live outside the repository.
    | The folder mirrors museum-of-time/: exhibits/<slug>/, assets/video,
    | assets/audio, and previews. The app links it at storage/app/public/media.
    */
    'media_root' => env('MEDIA_ROOT') ?: null,

    /*
    | Notes and prompts. Defaults to the museum-of-time archive beside this app.
    */
    'archive' => env('MUSEUM_ARCHIVE') ?: dirname(base_path()).DIRECTORY_SEPARATOR.'museum-of-time',
];
