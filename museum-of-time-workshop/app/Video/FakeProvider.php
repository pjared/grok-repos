<?php

namespace App\Video;

use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

/**
 * Local stand-in for a paid image-to-video model.
 * One frame becomes a Ken Burns move. Two frames crossfade.
 */
class FakeProvider implements VideoProvider
{
    public function __construct(private readonly Ffmpeg $ffmpeg) {}

    public function generate(string $startFrame, ?string $endFrame, string $prompt, float $duration): string
    {
        if (! is_file($startFrame)) {
            throw new \InvalidArgumentException("Start frame not found: {$startFrame}");
        }

        $duration = max(0.2, $duration);
        $width = $this->even((int) config('video.episode.width', 1280));
        $height = $this->even((int) config('video.episode.height', 720));
        $fps = max(1, (int) config('video.fps', 12));

        $relative = 'renders/'.Str::uuid().'.mp4';
        $output = Storage::disk('public')->path($relative);
        File::ensureDirectoryExists(dirname($output));

        if ($endFrame && is_file($endFrame)) {
            $this->crossfade($startFrame, $endFrame, $duration, $width, $height, $fps, $output);
        } else {
            $this->kenBurns($startFrame, $duration, $width, $height, $fps, $output);
        }

        return $output;
    }

    private function kenBurns(string $frame, float $duration, int $width, int $height, int $fps, string $output): void
    {
        $seconds = $this->seconds($duration);
        $zoomWidth = $this->even((int) round($width * 1.2));
        $zoomHeight = $this->even((int) round($height * 1.2));
        $zoom = "min(t/{$seconds}\\,1)";

        $filter = implode(',', [
            "scale={$zoomWidth}:{$zoomHeight}:force_original_aspect_ratio=increase",
            "crop={$zoomWidth}:{$zoomHeight}",
            "crop=w='iw*(1-0.12*{$zoom})':h='ih*(1-0.12*{$zoom})':x='(iw-ow)/2':y='(ih-oh)/2'",
            "scale={$width}:{$height}",
            'format=yuv420p',
        ]);

        $this->ffmpeg->run([
            '-loop', '1',
            '-framerate', (string) $fps,
            '-i', $frame,
            '-vf', $filter,
            '-t', $seconds,
            '-r', (string) $fps,
            '-an',
            ...$this->encodeArgs(),
            $output,
        ]);
    }

    private function crossfade(string $start, string $end, float $duration, int $width, int $height, int $fps, string $output): void
    {
        $seconds = $this->seconds($duration);
        $fade = min(0.5, $duration / 4);
        $offset = max(0, $duration - $fade);
        $scale = "scale={$width}:{$height}:force_original_aspect_ratio=increase,crop={$width}:{$height},format=yuv420p,setpts=PTS-STARTPTS";
        $filter = "[0:v]{$scale}[a];[1:v]{$scale}[b];[a][b]xfade=transition=fade:duration=".$this->seconds($fade).':offset='.$this->seconds($offset).',format=yuv420p';

        $this->ffmpeg->run([
            '-loop', '1',
            '-framerate', (string) $fps,
            '-t', $seconds,
            '-i', $start,
            '-loop', '1',
            '-framerate', (string) $fps,
            '-t', $seconds,
            '-i', $end,
            '-filter_complex', $filter,
            '-t', $seconds,
            '-r', (string) $fps,
            '-an',
            ...$this->encodeArgs(),
            $output,
        ]);
    }

    /**
     * @return list<string>
     */
    private function encodeArgs(): array
    {
        return ['-c:v', 'libx264', '-preset', 'ultrafast', '-tune', 'stillimage', '-crf', '28', '-pix_fmt', 'yuv420p'];
    }

    private function seconds(float $duration): string
    {
        return number_format($duration, 3, '.', '');
    }

    private function even(int $value): int
    {
        return $value % 2 === 0 ? $value : $value - 1;
    }
}
