<?php

namespace App\Video;

class SubtitleBuilder
{
    /**
     * @param  list<array{start: float, end: float, text: string}>  $cues
     */
    public static function write(array $cues): string
    {
        $lines = [];
        $index = 1;

        foreach ($cues as $cue) {
            $text = trim(str_replace(["\r", "\n"], ' ', (string) ($cue['text'] ?? '')));

            if ($text === '') {
                continue;
            }

            $start = self::timestamp((float) $cue['start']);
            $end = self::timestamp(max((float) $cue['start'] + 0.2, (float) $cue['end']));
            $lines[] = $index."\n".$start.' --> '.$end."\n".$text."\n";
            $index++;
        }

        $path = tempnam(sys_get_temp_dir(), 'mot-srt-');
        $srt = $path.'.srt';
        rename($path, $srt);
        file_put_contents($srt, implode("\n", $lines));

        return $srt;
    }

    public static function timestamp(float $seconds): string
    {
        $ms = (int) round(max(0, $seconds) * 1000);
        $hours = intdiv($ms, 3_600_000);
        $ms %= 3_600_000;
        $minutes = intdiv($ms, 60_000);
        $ms %= 60_000;
        $secs = intdiv($ms, 1000);
        $ms %= 1000;

        return sprintf('%02d:%02d:%02d,%03d', $hours, $minutes, $secs, $ms);
    }
}
