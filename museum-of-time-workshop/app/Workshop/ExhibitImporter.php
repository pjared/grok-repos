<?php

namespace App\Workshop;

use App\Models\ScenePackSubmission;
use Illuminate\Support\Facades\File;

class ExhibitImporter
{
    public function __construct(
        private readonly ExhibitNotes $notes,
        private readonly SceneInbox $inbox,
    ) {}

    public function submit(string $slug): ScenePackSubmission
    {
        $pack = $this->notes->pack($slug);
        $directory = $this->inbox->directory();
        File::ensureDirectoryExists($directory);

        $name = $slug.'.json';
        $path = $directory.DIRECTORY_SEPARATOR.$name;

        if (is_file($path)) {
            $name = $slug.'-'.uniqid().'.json';
            $path = $directory.DIRECTORY_SEPARATOR.$name;
        }

        File::put($path, json_encode($pack, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES)."\n");
        $submission = $this->inbox->scan()->firstWhere('filename', $name);

        if (! $submission) {
            throw new \RuntimeException('Exhibit pack was not added to the inbox.');
        }

        return $submission;
    }
}
