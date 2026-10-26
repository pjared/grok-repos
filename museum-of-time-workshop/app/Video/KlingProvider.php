<?php

namespace App\Video;

/**
 * Stub for a Kling image-to-video client. Off by default.
 * v0 never opens a network connection, even when the flag is on.
 */
class KlingProvider implements VideoProvider
{
    public function generate(string $startFrame, ?string $endFrame, string $prompt, float $duration): string
    {
        if (! config('video.providers.kling.enabled')) {
            throw new VideoProviderDisabled('Kling is off. Set KLING_ENABLED=true to select the stub. v0 does not call the Kling API.');
        }

        throw new VideoProviderDisabled('Kling is a stub in v0 and does not call the network.');
    }
}
