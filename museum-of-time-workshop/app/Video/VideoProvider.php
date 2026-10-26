<?php

namespace App\Video;

interface VideoProvider
{
    /**
     * Render a clip from a start frame and an optional end frame.
     * Returns the absolute path of the finished MP4.
     */
    public function generate(string $startFrame, ?string $endFrame, string $prompt, float $duration): string;
}
