<?php

namespace App\Video;

class Concatenator
{
    public function __construct(private readonly Ffmpeg $ffmpeg) {}

    /**
     * @param  list<string>  $absolutePaths
     */
    public function join(array $absolutePaths): string
    {
        if ($absolutePaths === []) {
            throw new \InvalidArgumentException('Nothing to concatenate.');
        }

        $list = tempnam(sys_get_temp_dir(), 'mot-concat-');
        $lines = array_map(
            fn (string $path) => "file '".str_replace("'", "'\\''", $path)."'",
            $absolutePaths,
        );
        file_put_contents($list, implode("\n", $lines)."\n");

        $output = tempnam(sys_get_temp_dir(), 'mot-join-').'.mp4';
        $fps = (string) max(1, (int) config('video.fps', 12));

        $this->ffmpeg->run([
            '-f', 'concat',
            '-safe', '0',
            '-i', $list,
            '-an',
            '-r', $fps,
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-crf', '28',
            '-pix_fmt', 'yuv420p',
            $output,
        ]);

        @unlink($list);

        return $output;
    }
}
