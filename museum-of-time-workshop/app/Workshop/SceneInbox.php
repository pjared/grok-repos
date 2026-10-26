<?php

namespace App\Workshop;

use App\Enums\ScenePackStatus;
use App\Models\ScenePackSubmission;
use App\Models\Shot;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\File;

class SceneInbox
{
    public function __construct(private readonly AddScene $addScene) {}

    /**
     * @return Collection<int, ScenePackSubmission>
     */
    public function scan(): Collection
    {
        $inbox = $this->directory();
        File::ensureDirectoryExists($inbox);

        foreach (File::files($inbox) as $file) {
            if (strtolower($file->getExtension()) !== 'json') {
                continue;
            }

            $fingerprint = hash_file('sha256', $file->getPathname());

            if (ScenePackSubmission::query()->where('fingerprint', $fingerprint)->exists()) {
                continue;
            }

            $stored = $this->store($file->getPathname(), $fingerprint);

            try {
                $pack = ScenePack::load($stored);
                ScenePackSubmission::query()->create([
                    'fingerprint' => $fingerprint,
                    'filename' => $file->getFilename(),
                    'stored_path' => $stored,
                    'status' => ScenePackStatus::Pending,
                    'summary' => [
                        'exhibit' => $pack->exhibit,
                        'scenes' => count($pack->scenes),
                    ],
                ]);
            } catch (\InvalidArgumentException $exception) {
                ScenePackSubmission::query()->create([
                    'fingerprint' => $fingerprint,
                    'filename' => $file->getFilename(),
                    'stored_path' => $stored,
                    'status' => ScenePackStatus::Invalid,
                    'error' => $exception->getMessage(),
                ]);
            }
        }

        return ScenePackSubmission::query()
            ->whereIn('status', [ScenePackStatus::Pending, ScenePackStatus::Invalid])
            ->latest()
            ->get();
    }

    /**
     * @return list<Shot>
     */
    public function approve(ScenePackSubmission $submission): array
    {
        if ($submission->status !== ScenePackStatus::Pending) {
            throw new \RuntimeException($submission->error ?: 'This pack is not waiting for approval.');
        }

        $shots = ScenePack::load($submission->stored_path)->import($this->addScene);
        $submission->update(['status' => ScenePackStatus::Approved]);

        return $shots;
    }

    public function reject(ScenePackSubmission $submission): void
    {
        if (! in_array($submission->status, [ScenePackStatus::Pending, ScenePackStatus::Invalid], true)) {
            throw new \RuntimeException('This pack is not waiting for approval.');
        }

        $submission->update(['status' => ScenePackStatus::Rejected]);
    }

    public function directory(): string
    {
        return (string) config('workshop.inbox');
    }

    private function store(string $source, string $fingerprint): string
    {
        $destination = storage_path('app/scene-packs/'.$fingerprint);
        File::ensureDirectoryExists($destination);

        $packPath = $destination.DIRECTORY_SEPARATOR.'pack.json';
        File::copy($source, $packPath);

        try {
            $pack = ScenePack::load($source);
        } catch (\InvalidArgumentException) {
            return $packPath;
        }

        foreach ($pack->scenes as $scene) {
            $relative = $scene['frame'] ?? null;

            if (! is_string($relative) || $relative === '') {
                continue;
            }

            $from = dirname($source).DIRECTORY_SEPARATOR.str_replace('/', DIRECTORY_SEPARATOR, str_replace('\\', '/', $relative));
            $to = $destination.DIRECTORY_SEPARATOR.str_replace('/', DIRECTORY_SEPARATOR, str_replace('\\', '/', $relative));
            File::ensureDirectoryExists(dirname($to));

            if (is_file($from)) {
                File::copy($from, $to);
            }
        }

        return $packPath;
    }
}
