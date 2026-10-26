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

            self::assertPlacement($scene, $number);
        }

        return new self($exhibit, array_values($scenes), $directory);
    }

    /**
     * @return list<Shot>
     */
    public function import(AddScene $addScene): array
    {
        $copied = [];

        try {
            return DB::transaction(function () use ($addScene, &$copied) {
                $sequence = ExhibitSequences::find($this->exhibit);
                $created = [];

                foreach ($this->scenes as $scene) {
                    $sequence->refresh();
                    $after = $this->after($sequence, $scene);
                    $frame = $this->storeFrame($sequence, $scene['frame'] ?? null);

                    if (is_string($frame)) {
                        $copied[] = $frame;
                    }

                    $attributes = [
                        'title' => $scene['title'] ?? null,
                        'prompt' => $scene['prompt'] ?? '',
                        'duration' => $scene['duration'] ?? AddScene::DEFAULT_DURATION,
                        'truth' => $scene['truth'] ?? 'invented',
                        'model' => $scene['model'] ?? AddScene::DEFAULT_MODEL,
                        'frame_path' => $frame,
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
        } catch (\Throwable $exception) {
            Storage::disk('public')->delete($copied);

            throw $exception;
        }
    }

    /**
     * @param  array<string, mixed>  $scene
     */
    private function after(Sequence $sequence, array $scene): ?Shot
    {
        [$id, $order] = self::placement($scene, 0);

        if ($id === null && $order === null) {
            return null;
        }

        $shots = $sequence->shots()->get();

        if ($id !== null) {
            $shot = $shots->firstWhere('id', $id);

            if (! $shot) {
                throw new \InvalidArgumentException("No shot id {$id} on this sequence to insert after.");
            }

            return $shot;
        }

        $shot = $shots->first(fn (Shot $candidate) => (int) $candidate->order === $order);

        if (! $shot) {
            throw new \InvalidArgumentException("No shot at order {$order} on this sequence to insert after.");
        }

        return $shot;
    }

    /**
     * @param  array<string, mixed>  $scene
     */
    private static function assertPlacement(array $scene, int $sceneNumber): void
    {
        self::placement($scene, $sceneNumber);
    }

    /**
     * @param  array<string, mixed>  $scene
     * @return array{0: ?int, 1: ?int}
     */
    private static function placement(array $scene, int $sceneNumber): array
    {
        $label = $sceneNumber > 0 ? "Scene {$sceneNumber}" : 'Scene';

        if (self::present($scene['after'] ?? null)) {
            throw new \InvalidArgumentException("{$label} uses ambiguous \"after\". Use after_id or after_order.");
        }

        $hasId = self::present($scene['after_id'] ?? null);
        $hasOrder = self::present($scene['after_order'] ?? null);

        if ($hasId && $hasOrder) {
            throw new \InvalidArgumentException("{$label} cannot set both after_id and after_order.");
        }

        return [
            $hasId ? self::wholeNumber($scene['after_id'], "{$label} after_id must be a shot id.") : null,
            $hasOrder ? self::wholeNumber($scene['after_order'], "{$label} after_order must be an order number.") : null,
        ];
    }

    private static function present(mixed $value): bool
    {
        return $value !== null && $value !== '';
    }

    private static function wholeNumber(mixed $value, string $message): int
    {
        if (is_int($value) || (is_string($value) && preg_match('/^\d+$/', $value) === 1)) {
            return (int) $value;
        }

        throw new \InvalidArgumentException($message);
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
        $inside = $sceneNumber > 0
            ? "Scene {$sceneNumber} frame \"{$relative}\" must stay inside the pack."
            : "Scene pack frame \"{$relative}\" must stay inside the pack.";
        $missing = $sceneNumber > 0
            ? "Scene {$sceneNumber} is missing frame \"{$relative}\"."
            : "Scene pack is missing frame \"{$relative}\".";
        $normalized = str_replace('\\', '/', $relative);

        if (
            $normalized === ''
            || str_starts_with($normalized, '/')
            || str_contains($normalized, '..')
            || preg_match('/^[A-Za-z]:/', $normalized) === 1
        ) {
            throw new \InvalidArgumentException($inside);
        }

        $directory = realpath($directory);

        if ($directory === false) {
            throw new \InvalidArgumentException($missing);
        }

        $candidate = $directory.DIRECTORY_SEPARATOR.str_replace('/', DIRECTORY_SEPARATOR, $normalized);
        $real = realpath($candidate);

        if ($real !== false && ! str_starts_with($real, $directory.DIRECTORY_SEPARATOR)) {
            throw new \InvalidArgumentException($inside);
        }

        if ($real === false || ! is_file($real)) {
            throw new \InvalidArgumentException(is_link($candidate) ? $inside : $missing);
        }

        return $real;
    }
}
