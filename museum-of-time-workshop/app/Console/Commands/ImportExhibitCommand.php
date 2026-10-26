<?php

namespace App\Console\Commands;

use App\Workshop\ExhibitImporter;
use Illuminate\Console\Command;

class ImportExhibitCommand extends Command
{
    protected $signature = 'workshop:import-exhibit {slug : Exhibit folder under museum-of-time/exhibits}';

    protected $description = 'Build a scene pack from exhibit notes and rendered media, and leave it pending in the inbox';

    public function handle(ExhibitImporter $importer): int
    {
        try {
            $submission = $importer->submit((string) $this->argument('slug'));
        } catch (\InvalidArgumentException $exception) {
            $this->error($exception->getMessage());

            return self::FAILURE;
        }

        $this->line(json_encode([
            'status' => $submission->status->value,
            'filename' => $submission->filename,
            'exhibit' => $submission->summary['exhibit'] ?? $this->argument('slug'),
            'scenes' => $submission->summary['scenes'] ?? null,
            'message' => 'Waiting for approval.',
        ], JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));

        return self::SUCCESS;
    }
}
