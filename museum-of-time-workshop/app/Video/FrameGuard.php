<?php

namespace App\Video;

use App\Models\Sequence;
use App\Models\Shot;

class FrameGuard
{
    public static function message(Shot $shot): string
    {
        return 'Shot '.$shot->order.' "'.$shot->title.'" has no frame. Add a frame before rendering or exporting.';
    }

    public static function assertExportable(Sequence $sequence): void
    {
        $missing = $sequence->shots()->orderBy('order')->get()->filter(
            fn (Shot $shot) => ! $shot->hasFrame(),
        );

        if ($missing->isEmpty()) {
            return;
        }

        $list = $missing->map(fn (Shot $shot) => $shot->order.' "'.$shot->title.'"')->implode(', ');

        throw new \RuntimeException('Cannot render or export. These shots have no frame: '.$list.'.');
    }
}
