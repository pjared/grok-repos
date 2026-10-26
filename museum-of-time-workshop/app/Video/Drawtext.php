<?php

namespace App\Video;

class Drawtext
{
    public static function filter(string $text, array $options = []): string
    {
        $size = $options['size'] ?? 28;
        $y = $options['y'] ?? 'h-th-36';
        $font = self::escapePath(Fonts::path());
        $escaped = self::escape($text);

        $filter = "drawtext=fontfile='{$font}':text='{$escaped}':fontsize={$size}:fontcolor=white:box=1:boxcolor=0x0f1014@0.72:boxborderw=12:x=(w-text_w)/2:y={$y}";

        if (isset($options['enable'])) {
            $filter .= ":enable='{$options['enable']}'";
        }

        return $filter;
    }

    public static function between(float $start, float $end): string
    {
        $start = number_format(max(0, $start), 3, '.', '');
        $end = number_format(max((float) $start + 0.1, $end), 3, '.', '');

        return "between(t\\,{$start}\\,{$end})";
    }

    public static function escape(string $text): string
    {
        return str_replace(
            ['\\', "'", ':', '%', ','],
            ['\\\\', "\\'", '\\:', '\\%', '\\,'],
            $text,
        );
    }

    public static function escapePath(string $path): string
    {
        return str_replace(['\\', ':'], ['/', '\\:'], $path);
    }
}
