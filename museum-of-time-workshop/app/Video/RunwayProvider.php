<?php

namespace App\Video;

/**
 * Stub for a Runway image-to-video client. Off by default.
 * v0 never opens a network connection, even when the flag is on.
 */
class RunwayProvider implements VideoProvider
{
    public function generate(string $startFrame, ?string $endFrame, string $prompt, float $duration): string
    {
        if (! config('video.providers.runway.enabled')) {
            throw new VideoProviderDisabled('Runway is off. Set RUNWAY_ENABLED=true to select the stub. v0 does not call the Runway API.');
        }

        throw new VideoProviderDisabled('Runway is a stub in v0 and does not call the network.');
    }
}
