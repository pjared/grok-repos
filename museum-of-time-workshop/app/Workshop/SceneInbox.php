<?php

namespace App\Workshop;

use App\Enums\ScenePackStatus;
use App\Models\ScenePackSubmission;
use App\Models\Shot;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\File;

class SceneInbox
{
    /** @var array<string, string> */
    private static array $signatures = [];

    public static int $hashCount = 0;

    public function __construct(private readonly AddScene $addScene) {}

    public static function forgetScanCache(): void
    {
        self::$signatures = [];
        self::$hashCount = 0;
    }

    /**
     * @return Collection<int, ScenePackSubmission>
     */
    public function scan(): Collection
    {
        $inbox = $this->directory();
        File::ensureDirectoryExists($inbox);

        foreach (File::files($inbox) as $file) {
            $extension = strtolower($file->getExtension());

            if (! in_array($extension, ['json', 'zip'], true)) {
                continue;
            }

            $pathname = $file->getPathname();
            $signature = $file->getMTime().':'.$file->getSize();

            if ((self::$signatures[$pathname] ?? null) === $signature) {
                continue;
            }

            $fingerprint = hash_file('sha256', $pathname);
            self::$hashCount++;
            self::$signatures[$pathname] = $signature;

            if ($fingerprint === false || ScenePackSubmission::query()->where('fingerprint', $fingerprint)->exists()) {
                continue;
            }

            $stored = $pathname;

            try {
                $stored = $extension === 'zip'
                    ? $this->storeZip($pathname, $fingerprint)
                    : $this->store($pathname, $fingerprint);
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

    public function receive(string $source, string $filename): ScenePackSubmission
    {
        if (! is_file($source)) {
            throw new \InvalidArgumentException('Scene pack was not uploaded.');
        }

        $inbox = $this->directory();

        if (file_exists($inbox) && ! is_dir($inbox)) {
            throw new \RuntimeException('Scene inbox is not a directory.');
        }

        File::ensureDirectoryExists($inbox);

        $name = $this->inboxName($filename);
        File::copy($source, $inbox.DIRECTORY_SEPARATOR.$name);
        $submission = $this->scan()->firstWhere('filename', $name);

        if (! $submission) {
            throw new \RuntimeException('Scene pack was not added to the inbox.');
        }

        return $submission;
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

    private function storeZip(string $source, string $fingerprint): string
    {
        $destination = storage_path('app/scene-packs/'.$fingerprint);
        File::ensureDirectoryExists($destination);
        $this->extractZip($source, $destination);

        return $this->findPackJson($destination);
    }

    private function extractZip(string $source, string $destination): void
    {
        $zip = new \ZipArchive;

        if ($zip->open($source) !== true) {
            throw new \InvalidArgumentException('Scene pack zip could not be opened.');
        }

        for ($index = 0; $index < $zip->numFiles; $index++) {
            $this->assertZipEntry((string) $zip->getNameIndex($index));
        }

        $extracted = $zip->extractTo($destination);
        $zip->close();

        if ($extracted !== true) {
            throw new \InvalidArgumentException('Scene pack zip could not be extracted.');
        }

        $root = realpath($destination);

        if ($root === false) {
            throw new \InvalidArgumentException('Scene pack zip could not be extracted.');
        }

        $files = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($root, \FilesystemIterator::SKIP_DOTS),
        );

        foreach ($files as $file) {
            $real = realpath($file->getPathname());

            if ($real === false || ($real !== $root && ! str_starts_with($real, $root.DIRECTORY_SEPARATOR))) {
                throw new \InvalidArgumentException('Scene pack zip must keep its files inside the pack.');
            }
        }
    }

    private function assertZipEntry(string $name): void
    {
        $normalized = str_replace('\\', '/', $name);

        if (
            $normalized === ''
            || str_starts_with($normalized, '/')
            || str_contains($normalized, '..')
            || preg_match('/^[A-Za-z]:/', $normalized) === 1
        ) {
            throw new \InvalidArgumentException('Scene pack zip must keep its files inside the pack.');
        }
    }

    private function findPackJson(string $directory): string
    {
        $preferred = $directory.DIRECTORY_SEPARATOR.'pack.json';

        if (is_file($preferred)) {
            return $preferred;
        }

        $json = [];
        $files = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($directory, \FilesystemIterator::SKIP_DOTS),
        );

        foreach ($files as $file) {
            if ($file->isFile() && strtolower($file->getExtension()) === 'json') {
                $json[] = $file->getPathname();
            }
        }

        if (count($json) !== 1) {
            throw new \InvalidArgumentException('Scene pack zip must contain one JSON file.');
        }

        return $json[0];
    }

    private function inboxName(string $filename): string
    {
        $name = basename(str_replace('\\', '/', $filename));

        if (preg_match('/^[A-Za-z0-9._-]+\.zip$/', $name) !== 1) {
            $name = 'pack.zip';
        }

        if (is_file($this->directory().DIRECTORY_SEPARATOR.$name)) {
            $name = pathinfo($name, PATHINFO_FILENAME).'-'.uniqid().'.zip';
        }

        return $name;
    }
}
