<?php

namespace App\Jobs;

use App\Enums\ShotStatus;
use App\Models\Shot;
use App\Video\FrameGuard;
use App\Video\VideoProvider;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

class GenerateShotJob implements ShouldQueue
{
    use Queueable;

    public int $timeout = 600;

    public int $tries = 1;

    public function __construct(public int $shotId) {}

    public function handle(VideoProvider $provider): void
    {
        $shot = Shot::query()->findOrFail($this->shotId);

        if (! $shot->hasFrame()) {
            $shot->update(['status' => ShotStatus::Failed]);

            throw new \RuntimeException(FrameGuard::message($shot));
        }

        $shot->update(['status' => ShotStatus::Rendering]);

        $start = Storage::disk('public')->path((string) $shot->frame_path);
        $next = Shot::query()
            ->where('sequence_id', $shot->sequence_id)
            ->where('order', '>', $shot->order)
            ->orderBy('order')
            ->first();
        $end = $next?->frame_path ? Storage::disk('public')->path($next->frame_path) : null;

        try {
            $absolute = $provider->generate($start, $end, (string) $shot->prompt, (float) $shot->duration_s);
            $shot->update([
                'clip_path' => $this->relativePublicPath($absolute),
                'status' => ShotStatus::Ready,
            ]);
        } catch (\Throwable $exception) {
            $shot->update(['status' => ShotStatus::Failed]);

            throw $exception;
        }
    }

    public function failed(?\Throwable $exception): void
    {
        Shot::query()->whereKey($this->shotId)->update(['status' => ShotStatus::Failed]);
    }

    private function relativePublicPath(string $absolute): string
    {
        $root = rtrim(Storage::disk('public')->path(''), DIRECTORY_SEPARATOR).DIRECTORY_SEPARATOR;

        if (str_starts_with($absolute, $root)) {
            return ltrim(substr($absolute, strlen($root)), DIRECTORY_SEPARATOR);
        }

        $relative = 'clips/'.Str::uuid().'.mp4';
        $destination = Storage::disk('public')->path($relative);
        File::ensureDirectoryExists(dirname($destination));
        File::copy($absolute, $destination);

        return $relative;
    }
}
