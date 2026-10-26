<?php

namespace App\Video;

use Symfony\Component\Process\Process;

class Ffmpeg
{
    public function run(array $args): void
    {
        $command = array_merge([
            (string) config('video.ffmpeg', 'ffmpeg'),
            '-y',
            '-hide_banner',
            '-loglevel', 'error',
        ], $args);

        $process = new Process($command);
        $process->setTimeout((float) config('video.timeout', 600));
        $process->run();

        if (! $process->isSuccessful()) {
            $error = trim($process->getErrorOutput());

            throw new \RuntimeException($error !== '' ? $error : 'ffmpeg failed.');
        }
    }
}
