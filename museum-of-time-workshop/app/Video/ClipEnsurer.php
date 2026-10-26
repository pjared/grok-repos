<?php

namespace App\Video;

use App\Jobs\GenerateShotJob;
use App\Models\Sequence;
use Illuminate\Support\Facades\Storage;

class ClipEnsurer
{
    public function ensure(Sequence $sequence): void
    {
        foreach ($sequence->shots()->orderBy('order')->get() as $shot) {
            $path = $shot->clip_path ? Storage::disk('public')->path($shot->clip_path) : null;

            if (! $path || ! is_file($path)) {
                (new GenerateShotJob($shot->id))->handle(app(VideoProvider::class));
            }
        }
    }
}
