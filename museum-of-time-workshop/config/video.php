<?php

return [
    'ffmpeg' => env('FFMPEG_BINARY', 'ffmpeg'),
    'ffprobe' => env('FFPROBE_BINARY', 'ffprobe'),

    /*
    | The active generator. "fake" renders locally with ffmpeg.
    | "runway" and "kling" are stubs and stay off unless explicitly enabled.
    */
    'provider' => env('VIDEO_PROVIDER', 'fake'),

    'fps' => (int) env('VIDEO_FPS', 12),
    'timeout' => (int) env('VIDEO_TIMEOUT', 600),

    'episode' => [
        'width' => (int) env('EPISODE_WIDTH', 1280),
        'height' => (int) env('EPISODE_HEIGHT', 720),
        'min_seconds' => 180,
        'max_seconds' => 240,
    ],

    'short' => [
        'width' => (int) env('SHORT_WIDTH', 720),
        'height' => (int) env('SHORT_HEIGHT', 1280),
        'min_seconds' => 45,
        'max_seconds' => 60,
    ],

    'providers' => [
        'runway' => [
            'enabled' => (bool) env('RUNWAY_ENABLED', false),
            'api_key' => env('RUNWAY_API_KEY'),
        ],
        'kling' => [
            'enabled' => (bool) env('KLING_ENABLED', false),
            'api_key' => env('KLING_API_KEY'),
        ],
    ],
];
