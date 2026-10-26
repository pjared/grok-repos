<?php

namespace App\Video;

class Fonts
{
    public static function path(): string
    {
        $candidates = [
            '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',
            '/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf',
            '/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf',
            'C:/Windows/Fonts/arial.ttf',
        ];

        foreach ($candidates as $path) {
            if (is_file($path)) {
                return $path;
            }
        }

        throw new \RuntimeException('No drawtext font found. Install fonts-dejavu-core.');
    }
}
