<?php

namespace App\Video;

class HouseStandard
{
    public const EPISODE_MIN = 180;

    public const EPISODE_MAX = 240;

    public const SHORT_MIN = 45;

    public const SHORT_MAX = 60;

    public static function episodeWarning(float $seconds): ?string
    {
        if ($seconds >= self::EPISODE_MIN && $seconds <= self::EPISODE_MAX) {
            return null;
        }

        return sprintf(
            'Episode is %s, outside the 3–4 minute house standard.',
            self::clock($seconds),
        );
    }

    public static function clock(float $seconds): string
    {
        $rounded = (int) round($seconds);

        return sprintf('%d:%02d', intdiv($rounded, 60), $rounded % 60);
    }
}
