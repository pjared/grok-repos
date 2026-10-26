<?php

namespace App\Video;

class VideoProviderManager
{
    public function driver(?string $name = null): VideoProvider
    {
        $name ??= (string) config('video.provider', 'fake');

        return match ($name) {
            'fake' => app(FakeProvider::class),
            'runway' => app(RunwayProvider::class),
            'kling' => app(KlingProvider::class),
            default => throw new \InvalidArgumentException("Unknown video provider [{$name}]."),
        };
    }
}
