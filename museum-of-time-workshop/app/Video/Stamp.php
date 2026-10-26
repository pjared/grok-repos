<?php

namespace App\Video;

class Stamp
{
    public static function text(string $wing, string $exhibit, int $number, int $total): string
    {
        return "Museum of Time · {$wing} · {$exhibit} · Short {$number} of {$total}";
    }
}
