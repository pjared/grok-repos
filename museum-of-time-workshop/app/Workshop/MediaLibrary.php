<?php

namespace App\Workshop;

use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\Process\Process;

class MediaLibrary
{
    /** @var array<string, array{sig: string, duration: ?float}> */
    private static array $probes = [];

    public static int $probeCount = 0;

    public ?string $linkNotice = null;

    public static function forgetCache(): void
    {
        self::$probes = [];
        self::$probeCount = 0;
    }

    public function root(): ?string
    {
        $root = config('workshop.media_root');

        if (! is_string($root) || $root === '' || ! is_dir($root)) {
            return null;
        }

        $real = realpath($root);

        return $real === false ? null : $real;
    }

    public function link(): void
    {
        try {
            $this->placeLink();
            $this->linkNotice = null;
        } catch (\Throwable $exception) {
            $this->linkNotice = $exception->getMessage() !== ''
                ? $exception->getMessage()
                : 'Media library could not be linked.';
        }
    }

    /**
     * @return list<array{exhibit: string, label: string, importable: bool, files: list<array<string, mixed>>}>
     */
    public function groups(): array
    {
        $records = $this->records();
        $slugs = $this->slugs();
        $grouped = [];

        foreach ($records as $record) {
            $exhibit = $this->exhibitKey($record['relative'], $slugs);
            $grouped[$exhibit][] = $record;
        }

        ksort($grouped);
        $groups = [];

        foreach ($grouped as $exhibit => $files) {
            usort($files, fn (array $left, array $right) => $left['relative'] <=> $right['relative']);
            $groups[] = [
                'exhibit' => $exhibit,
                'label' => $this->label($exhibit),
                'importable' => $exhibit !== 'library' && is_dir($this->archiveExhibit($exhibit)),
                'files' => array_map(fn (array $file) => $this->present($file), $files),
            ];
        }

        return $groups;
    }

    /**
     * @return list<array{relative: string, absolute: string, stem: string, extension: string, kind: string}>
     */
    public function records(): array
    {
        $this->link();
        $root = $this->root();

        if ($root === null) {
            return [];
        }

        $records = [];
        $files = new \RecursiveIteratorIterator(
            new \RecursiveDirectoryIterator($root, \FilesystemIterator::SKIP_DOTS),
        );

        foreach ($files as $file) {
            if (! $file->isFile()) {
                continue;
            }

            $real = realpath($file->getPathname());

            if ($real === false || ! str_starts_with($real, $root.DIRECTORY_SEPARATOR)) {
                continue;
            }

            $extension = strtolower($file->getExtension());

            if (! in_array($extension, ['mp4', 'mov', 'mp3', 'jpg', 'jpeg', 'png'], true)) {
                continue;
            }

            $relative = ltrim(str_replace('\\', '/', substr($real, strlen($root))), '/');
            $records[] = [
                'relative' => $relative,
                'absolute' => $real,
                'stem' => pathinfo($real, PATHINFO_FILENAME),
                'extension' => $extension,
                'kind' => match ($extension) {
                    'mp4', 'mov' => 'video',
                    'mp3' => 'audio',
                    default => 'image',
                },
            ];
        }

        return $records;
    }

    /**
     * @param  array{relative: string, absolute: string, stem: string, extension: string, kind: string}  $file
     * @return array<string, mixed>
     */
    private function present(array $file): array
    {
        $duration = in_array($file['kind'], ['video', 'audio'], true)
            ? $this->duration($file['absolute'])
            : null;

        return [
            'name' => basename($file['relative']),
            'relative' => $file['relative'],
            'kind' => $file['kind'],
            'duration' => $duration,
            'duration_label' => $duration === null ? null : $this->clock($duration),
            'url' => Storage::disk('public')->url('media/'.$file['relative']),
        ];
    }

    private function duration(string $path): ?float
    {
        $signature = filemtime($path).':'.filesize($path);

        if ((self::$probes[$path]['sig'] ?? null) === $signature) {
            return self::$probes[$path]['duration'];
        }

        self::$probeCount++;
        $probed = $this->probe($path);
        self::$probes[$path] = ['sig' => $signature, 'duration' => $probed];

        return $probed;
    }

    private function probe(string $path): ?float
    {
        $process = new Process([
            (string) config('video.ffprobe', 'ffprobe'),
            '-v', 'error',
            '-show_entries', 'format=duration',
            '-of', 'default=noprint_wrappers=1:nokey=1',
            $path,
        ]);
        $process->setTimeout(30);
        $process->run();

        if (! $process->isSuccessful()) {
            return null;
        }

        $value = trim($process->getOutput());

        return is_numeric($value) ? round((float) $value, 3) : null;
    }

    private function clock(float $seconds): string
    {
        $seconds = max(0, (int) round($seconds));

        return intdiv($seconds, 60).':'.str_pad((string) ($seconds % 60), 2, '0', STR_PAD_LEFT);
    }

    /**
     * @param  list<string>  $slugs
     */
    private function exhibitKey(string $relative, array $slugs): string
    {
        $parts = explode('/', $relative);

        if (($parts[0] ?? '') === 'exhibits' && ($parts[1] ?? '') !== '') {
            return $parts[1];
        }

        $named = ($parts[0] ?? '') === 'assets' ? ($parts[2] ?? null) : (($parts[0] ?? '') === 'previews' ? ($parts[1] ?? null) : null);

        if (is_string($named) && in_array($named, $slugs, true)) {
            return $named;
        }

        foreach ($slugs as $slug) {
            if (str_contains($relative, $slug)) {
                return $slug;
            }
        }

        return 'library';
    }

    /**
     * @return list<string>
     */
    private function slugs(): array
    {
        $slugs = [];

        foreach ([$this->archiveExhibit(''), $this->root() !== null ? $this->root().'/exhibits' : ''] as $directory) {
            if ($directory === '' || ! is_dir($directory)) {
                continue;
            }

            foreach (File::directories($directory) as $child) {
                $slugs[] = basename($child);
            }
        }

        return array_values(array_unique($slugs));
    }

    private function label(string $exhibit): string
    {
        if ($exhibit === 'library') {
            return 'Library';
        }

        $readme = $this->archiveExhibit($exhibit).'/README.md';

        if (is_file($readme) && preg_match('/^#\s+(.+)$/m', (string) file_get_contents($readme), $match) === 1) {
            return trim($match[1]);
        }

        return str_replace('-', ' ', $exhibit);
    }

    private function archiveExhibit(string $slug): string
    {
        return rtrim((string) config('workshop.archive'), DIRECTORY_SEPARATOR).'/exhibits'.($slug === '' ? '' : '/'.$slug);
    }

    private function placeLink(): void
    {
        $root = $this->root();
        $link = storage_path('app/public/media');

        if ($root === null) {
            return;
        }

        if (is_link($link)) {
            if (realpath($link) === $root) {
                return;
            }

            unlink($link);
        }

        if (file_exists($link)) {
            return;
        }

        File::ensureDirectoryExists(dirname($link));
        File::link($root, $link);
    }
}
