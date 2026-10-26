<?php

namespace App\Workshop;

use App\Models\Sequence;
use App\Models\Shot;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

class ScenePack
{
    /**
     * @param  list<array<string, mixed>>  $scenes
     */
    private function __construct(
        public readonly string $exhibit,
        public readonly array $scenes,
        public readonly string $directory,
    ) {}

    public static function load(string $path): self
    {
        if (! is_file($path)) {
            throw new \InvalidArgumentException("Scene pack not found: {$path}");
        }

        try {
            $data = json_decode((string) file_get_contents($path), true, 512, JSON_THROW_ON_ERROR);
        } catch (\JsonException $exception) {
            throw new \InvalidArgumentException('Scene pack is not valid JSON: '.$exception->getMessage());
        }

        if (! is_array($data)) {
            throw new \InvalidArgumentException('Scene pack must be a JSON object.');
        }

        $exhibit = $data['exhibit'] ?? null;
        $scenes = $data['scenes'] ?? null;

        if (! is_string($exhibit) || trim($exhibit) === '' || ! is_array($scenes) || $scenes === []) {
            throw new \InvalidArgumentException('Scene pack must include an exhibit and at least one scene.');
        }

        $directory = dirname($path);

        foreach (array_values($scenes) as $index => $scene) {
            $number = $index + 1;

            if (! is_array($scene)) {
                throw new \InvalidArgumentException("Scene {$number} is not an object.");
            }

            if (isset($scene['frame']) && $scene['frame'] !== null && $scene['frame'] !== '') {
                if (! is_string($scene['frame'])) {
                    throw new \InvalidArgumentException("Scene {$number} has a frame path that is not a string.");
                }

                self::resolveFrame($directory, $scene['frame'], $number);
            }
        }

        return new self($exhibit, array_values($scenes), $directory);
    }

    /**
     * @return list<Shot>
     */
    public function import(AddScene $addScene): array
    {
        return DB::transaction(function () use ($addScene) {
            $sequence = ExhibitSequences::find($this->exhibit);
            $created = [];

            foreach ($this->scenes as $scene) {
                $sequence->refresh();
                $after = $this->after($sequence, $scene['after'] ?? null);
                $attributes = [
                    'title' => $scene['title'] ?? null,
                    'prompt' => $scene['prompt'] ?? '',
                    'duration' => $scene['duration'] ?? AddScene::DEFAULT_DURATION,
                    'truth' => $scene['truth'] ?? 'invented',
                    'model' => $scene['model'] ?? AddScene::DEFAULT_MODEL,
                    'frame_path' => $this->storeFrame($sequence, $scene['frame'] ?? null),
                    'narration' => $scene['narration'] ?? null,
                    'voice' => $scene['voice'] ?? null,
                    'plaque' => $scene['plaque'] ?? null,
                ];

                $created[] = $after
                    ? $addScene->insertAfter($sequence, $after, $attributes)
                    : $addScene->append($sequence, $attributes);
            }

            return $created;
        });
    }

    private function after(Sequence $sequence, mixed $after): ?Shot
    {
        if ($after === null || $after === '') {
            return null;
        }

        if (! is_numeric($after)) {
            throw new \InvalidArgumentException('Scene "after" must be a shot id or order number.');
        }

        $needle = (int) $after;
        $shots = $sequence->shots()->get();
        $byId = $shots->firstWhere('id', $needle);

        if ($byId) {
            return $byId;
        }

        $byOrder = $shots->first(fn (Shot $shot) => (int) $shot->order === $needle);

        if ($byOrder) {
            return $byOrder;
        }

        throw new \InvalidArgumentException("No shot {$after} on this sequence to insert after.");
    }

    private function storeFrame(Sequence $sequence, mixed $relative): ?string
    {
        if ($relative === null || $relative === '') {
            return null;
        }

        $source = self::resolveFrame($this->directory, (string) $relative, 0);
        $extension = strtolower(pathinfo($source, PATHINFO_EXTENSION) ?: 'jpg');

        if (! in_array($extension, ['jpg', 'jpeg', 'png', 'webp', 'gif'], true)) {
            throw new \InvalidArgumentException('Frame must be a jpg, png, webp, or gif.');
        }

        $stored = 'scenes/'.$sequence->id.'/'.Str::uuid().'.'.$extension;
        Storage::disk('public')->put($stored, File::get($source));

        return $stored;
    }

    private static function resolveFrame(string $directory, string $relative, int $sceneNumber): string
    {
        $label = $sceneNumber > 0 ? "Scene {$sceneNumber} is missing frame \"{$relative}\"." : "Scene pack is missing frame \"{$relative}\".";
        $normalized = str_replace('\\', '/', $relative);

        if ($normalized === '' || str_starts_with($normalized, '/') || str_contains($normalized, '..')) {
            throw new \InvalidArgumentException($label);
        }

        $directory = realpath($directory);

        if ($directory === false) {
            throw new \InvalidArgumentException($label);
        }

        $candidate = $directory.DIRECTORY_SEPARATOR.str_replace('/', DIRECTORY_SEPARATOR, $normalized);
        $real = realpath($candidate);

        if ($real === false || ! is_file($real) || ! str_starts_with($real, $directory.DIRECTORY_SEPARATOR)) {
            throw new \InvalidArgumentException($label);
        }

        return $real;
    }
}
