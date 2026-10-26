<?php

namespace App\Video;

class Drawtext
{
    /** @var list<string> */
    private static array $files = [];

    /** @var list<string> */
    private static array $texts = [];

    public static function filter(string $text, array $options = []): string
    {
        $size = $options['size'] ?? 28;
        $y = $options['y'] ?? 'h-th-36';
        $font = self::escapePath(Fonts::path());
        $file = self::escapePath(self::write($text));

        $filter = "drawtext=fontfile='{$font}':textfile='{$file}':expansion=none:fontsize={$size}:fontcolor=white:box=1:boxcolor=0x0f1014@0.72:boxborderw=12:x=(w-text_w)/2:y={$y}";

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

    /**
     * Paths of text files the next ffmpeg run still needs.
     *
     * @return list<string>
     */
    public static function files(): array
    {
        return self::$files;
    }

    /**
     * Exact strings written to those files, in order.
     *
     * @return list<string>
     */
    public static function texts(): array
    {
        return self::$texts;
    }

    public static function cleanup(): void
    {
        foreach (self::$files as $file) {
            if (is_file($file)) {
                @unlink($file);
            }
        }

        self::$files = [];
        self::$texts = [];
    }

    public static function escapePath(string $path): string
    {
        $path = str_replace('\\', '/', $path);

        return str_replace(
            ['\\', "'", ':', ',', '[', ']'],
            ['\\\\', "\\'", '\\:', '\\,', '\\[', '\\]'],
            $path,
        );
    }

    private static function write(string $text): string
    {
        $path = tempnam(sys_get_temp_dir(), 'mot-drawtext-');

        if ($path === false || file_put_contents($path, $text) === false) {
            throw new \RuntimeException('Could not write drawtext text.');
        }

        self::$files[] = $path;
        self::$texts[] = $text;

        return $path;
    }
}
