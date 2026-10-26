<?php

return [
    /*
    | Drop a scene pack JSON file in this folder (with its frames beside it).
    | The editor lists it as pending. Nothing is added until it is approved.
    */
    'inbox' => env('WORKSHOP_INBOX') ?: storage_path('app/inbox'),
];
