<?php

namespace App\Jobs;

use App\Enums\ExportStatus;
use App\Models\Export;
use App\Video\EpisodeExporter;
use Illuminate\Contracts\Queue\ShouldQueue;
use Illuminate\Foundation\Queue\Queueable;

class ExportEpisodeJob implements ShouldQueue
{
    use Queueable;

    public int $timeout = 600;

    public int $tries = 1;

    public function __construct(public int $exportId) {}

    public function handle(EpisodeExporter $exporter): void
    {
        $export = Export::query()->findOrFail($this->exportId);
        $export->update(['status' => ExportStatus::Running]);

        try {
            $result = $exporter->export($export->sequence);
            $export->update([
                'status' => ExportStatus::Ready,
                'path' => $result->path,
                'warnings' => $result->warnings,
                'meta' => ['duration' => $result->duration],
            ]);
        } catch (\Throwable $exception) {
            $export->update([
                'status' => ExportStatus::Failed,
                'error' => $exception->getMessage(),
            ]);

            throw $exception;
        }
    }
}
