<?php

namespace App\Workshop;

use App\Models\Exhibit;
use Illuminate\Support\Facades\File;

class ExhibitNotes
{
    public function __construct(private readonly MediaLibrary $media) {}

    /**
     * @return array{title: string, wing: string, hall: string, truth: string, scenes: list<array<string, mixed>>}
     */
    public function pack(string $slug): array
    {
        $slug = trim($slug);

        if ($slug === '' || str_contains($slug, '/') || str_contains($slug, '\\') || str_contains($slug, '..')) {
            throw new \InvalidArgumentException('Pass an exhibit slug.');
        }

        $archive = realpath((string) config('workshop.archive'));
        $directory = $archive === false ? false : realpath($archive.DIRECTORY_SEPARATOR.'exhibits'.DIRECTORY_SEPARATOR.$slug);

        if ($archive === false || $directory === false || ! str_starts_with($directory, $archive.DIRECTORY_SEPARATOR.'exhibits'.DIRECTORY_SEPARATOR)) {
            throw new \InvalidArgumentException("Exhibit \"{$slug}\" was not found in the archive.");
        }

        $readme = $this->read($directory, 'README.md');
        $script = $this->read($directory, 'script.md');
        $truth = $this->truth($readme.' '.$script);
        $scenes = $this->shots($directory, $slug, $script, $truth);
        $plaque = $this->section($readme, 'Plaque');

        if ($plaque !== '' && $scenes !== []) {
            $last = array_key_last($scenes);
            $scenes[$last]['plaque'] = $plaque;
        }

        if ($scenes === []) {
            throw new \InvalidArgumentException("Exhibit \"{$slug}\" has no scenes to import.");
        }

        $scenes = $this->place($scenes, $slug);

        return [
            'exhibit' => $slug,
            'title' => $this->heading($readme) ?: str_replace('-', ' ', $slug),
            'wing' => $this->wing($readme),
            'hall' => 'Main Hall',
            'truth' => $truth,
            'scenes' => $scenes,
        ];
    }

    /**
     * @return list<array<string, mixed>>
     */
    private function shots(string $directory, string $slug, string $script, string $truth): array
    {
        $parsed = $this->scriptScenes($script);
        $voices = $this->voices($directory);
        $packs = $this->packs($directory, $parsed);
        $records = $this->media->records();
        $shots = [];

        $source = $packs !== [] ? $packs : array_map(function (array $scene) {
            return [
                'key' => 'scene-'.$scene['number'],
                'scene' => $scene['number'],
                'title' => $scene['title'],
                'duration' => $scene['duration'],
                'prompt' => $scene['prompt'],
                'tokens' => array_values(array_filter([$scene['token'], 'scene-'.$scene['number'], 'F'.$scene['number']])),
            ];
        }, $parsed);

        $seenNarration = [];

        foreach ($source as $shot) {
            $scene = $parsed[$shot['scene']] ?? null;
            $narration = null;
            $audio = null;

            if (! isset($seenNarration[$shot['scene']])) {
                $seenNarration[$shot['scene']] = true;
                $voice = $voices[$shot['scene']] ?? null;
                $narration = $voice['text'] ?? ($scene['narration'] ?? '');
                $stems = array_filter([$voice['stem'] ?? null, $scene['token'] ?? null, 'scene-'.$shot['scene']]);
                $audioFile = $this->match($records, $stems, ['mp3'], $slug);
                $audio = $audioFile ? 'media/'.$audioFile['relative'] : null;
            }

            $clip = $this->match($records, $shot['tokens'], ['mp4', 'mov'], $slug);
            $frame = $this->match($records, $shot['tokens'], ['jpg', 'jpeg', 'png'], $slug);
            $prompt = trim((string) $shot['prompt']);
            $shotTruth = $this->shotTruth($truth, $prompt.' '.($scene['prompt'] ?? ''));

            $row = [
                'title' => $shot['title'],
                'prompt' => $prompt,
                'duration' => $shot['duration'] >= 0.2 ? $shot['duration'] : 4,
                'truth' => $shotTruth,
                'model' => 'FLUX',
            ];

            if ($narration !== null && trim($narration) !== '') {
                $row['narration'] = trim($narration);
            }

            if ($audio !== null) {
                $row['narration_audio'] = $audio;
            }

            if ($clip !== null) {
                $row['clip_path'] = 'media/'.$clip['relative'];
            }

            if ($frame !== null) {
                $row['frame_path'] = 'media/'.$frame['relative'];
            }

            $shots[] = $row;
        }

        return $shots;
    }

    /**
     * The first new scene uses after_id when this exhibit already has a shot.
     * Each later scene uses after_order for the shot the previous scene will occupy.
     *
     * @param  list<array<string, mixed>>  $scenes
     * @return list<array<string, mixed>>
     */
    private function place(array $scenes, string $slug): array
    {
        $tail = $this->tail($slug);
        $cursor = 1;

        if ($tail !== null) {
            $scenes[0]['after_id'] = $tail['id'];
            $cursor = $tail['order'] + 1;
        }

        for ($index = 1, $count = count($scenes); $index < $count; $index++) {
            $scenes[$index]['after_order'] = $cursor;
            $cursor++;
        }

        return $scenes;
    }

    /**
     * @return array{id: int, order: int}|null
     */
    private function tail(string $slug): ?array
    {
        $exhibit = Exhibit::query()->where('slug', $slug)->first();
        $sequence = $exhibit?->sequences()->latest('id')->first();
        $shot = $sequence?->shots()->orderByDesc('order')->orderByDesc('id')->first();

        if ($shot === null) {
            return null;
        }

        return [
            'id' => $shot->id,
            'order' => (int) $shot->order,
        ];
    }

    /**
     * @return array<int, array{number: int, title: string, duration: float, narration: string, prompt: string, token: ?string}>
     */
    private function scriptScenes(string $script): array
    {
        $scenes = [];
        $current = null;

        foreach (preg_split("/\r\n|\n|\r/", $script) ?: [] as $line) {
            if (preg_match('/^#{2,3}\s+Scene\s+(\d+)\s+[—–-]\s+(.+?)\s*$/u', $line, $match) === 1) {
                $this->storeScene($scenes, $current);
                $current = $this->blankScene((int) $match[1], trim($match[2]), null);

                continue;
            }

            if (preg_match('/^#{2,3}\s+(\d+)\s+(.+?)\s+\(~?([^)]+)\)\s*(?:[—–-]\s*`([^`]+)`)?\s*$/u', $line, $match) === 1) {
                $this->storeScene($scenes, $current);
                $current = $this->blankScene((int) $match[1], trim($match[2]), $match[4] ?? null);
                $current['duration'] = $this->seconds($match[3]) ?? 4;

                continue;
            }

            if ($current === null) {
                continue;
            }

            if (preg_match('/^#{1,2}\s+/', $line) === 1) {
                $this->storeScene($scenes, $current);
                $current = null;

                continue;
            }

            if (preg_match('/^\*\*Est\. duration:\*\*\s*(.+)$/', $line, $match) === 1) {
                $current['duration'] = $this->seconds($match[1]) ?? $current['duration'];

                continue;
            }

            if (preg_match('/^\*\*Shot(?: lock)?:\*\*\s*(.*)$/', $line, $match) === 1) {
                $current['prompt'] = trim($match[1]);

                continue;
            }

            if (preg_match('/^\*\*.+\*\*$/', trim($line)) === 1 || str_starts_with(trim($line), '*(') || trim($line) === '' || str_starts_with(trim($line), '---')) {
                continue;
            }

            $current['narration'] = trim($current['narration'].' '.trim($line));
        }

        $this->storeScene($scenes, $current);

        return $scenes;
    }

    /**
     * @param  array<int, array{number: int, title: string, duration: float, narration: string, prompt: string, token: ?string}>  $scenes
     * @param  array{number: int, title: string, duration: float, narration: string, prompt: string, token: ?string}|null  $current
     */
    private function storeScene(array &$scenes, ?array $current): void
    {
        if ($current !== null) {
            $scenes[$current['number']] = $current;
        }
    }

    /**
     * @return array{number: int, title: string, duration: float, narration: string, prompt: string, token: ?string}
     */
    private function blankScene(int $number, string $title, ?string $token): array
    {
        return [
            'number' => $number,
            'title' => $title,
            'duration' => 4,
            'narration' => '',
            'prompt' => '',
            'token' => $token,
        ];
    }

    /**
     * @param  array<int, array{number: int, title: string, duration: float, narration: string, prompt: string, token: ?string}>  $scenes
     * @return list<array{key: string, scene: int, title: string, duration: float, prompt: string, tokens: list<string>}>
     */
    private function packs(string $directory, array $scenes): array
    {
        $packs = [];

        foreach (preg_split("/\r\n|\n|\r/", $this->read($directory, 'flux-cut-sheet.md')) ?: [] as $line) {
            if (preg_match('/^\|\s*([A-Za-z0-9._-]+)\s*\|\s*(\d+)\s*\|\s*([^|]+)\|\s*([^|]+)\|/', $line, $match) !== 1) {
                continue;
            }

            if (strtolower($match[1]) === 'pack') {
                continue;
            }

            $key = $this->packKey($match[1]);
            $scene = (int) $match[2];
            $packs[$key] = [
                'key' => $key,
                'scene' => $scene,
                'title' => $scenes[$scene]['title'] ?? $key,
                'duration' => $this->seconds($match[3]) ?? ($scenes[$scene]['duration'] ?? 4),
                'prompt' => trim($match[4]),
                'tokens' => array_values(array_unique(array_filter([$key, $match[1], $scenes[$scene]['token'] ?? null]))),
            ];
        }

        $promptFile = $this->read($directory, 'flux-prompts.md');
        $blocks = preg_split('/^(?=###\s+)/m', $promptFile) ?: [];

        foreach ($blocks as $block) {
            if (preg_match('/^###\s+(\S+)\s+·\s+~?(\d+(?:\.\d+)?)s\b[^\n]*\n([\s\S]*)$/', $block, $match) !== 1) {
                continue;
            }

            $key = $this->packKey($match[1]);
            $scene = $this->sceneNumber($key) ?? ($packs[$key]['scene'] ?? null);

            if ($scene === null) {
                continue;
            }

            $body = trim(preg_replace('/^##\s.*$/m', '', $match[3]) ?? '');
            $existing = $packs[$key] ?? [
                'key' => $key,
                'scene' => $scene,
                'title' => $scenes[$scene]['title'] ?? $key,
                'duration' => (float) $match[2],
                'prompt' => '',
                'tokens' => [],
            ];
            $existing['duration'] = (float) $match[2];
            $existing['prompt'] = $body !== '' ? $body : $existing['prompt'];
            $existing['tokens'] = array_values(array_unique(array_filter([
                ...$existing['tokens'],
                $key,
                $match[1],
                $scenes[$scene]['token'] ?? null,
            ])));
            $packs[$key] = $existing;
        }

        $shots = array_values($packs);
        usort($shots, function (array $left, array $right) {
            return [$left['scene'], $left['key']] <=> [$right['scene'], $right['key']];
        });

        $counts = [];

        foreach ($shots as $shot) {
            $counts[$shot['scene']] = ($counts[$shot['scene']] ?? 0) + 1;
        }

        foreach ($shots as $index => $shot) {
            $title = $scenes[$shot['scene']]['title'] ?? $shot['title'];
            $shots[$index]['title'] = ($counts[$shot['scene']] ?? 1) > 1 ? $title.' · '.$shot['key'] : $title;
        }

        return $shots;
    }

    /**
     * @return array<int, array{stem: string, text: string}>
     */
    private function voices(string $directory): array
    {
        $voices = [];
        $folder = $directory.DIRECTORY_SEPARATOR.'vo';

        if (! is_dir($folder)) {
            return $voices;
        }

        foreach (File::files($folder) as $file) {
            if (strtolower($file->getExtension()) !== 'txt') {
                continue;
            }

            $stem = $file->getFilenameWithoutExtension();

            if (preg_match('/(\d+)$/', $stem, $match) !== 1) {
                continue;
            }

            $voices[(int) $match[1]] = [
                'stem' => $stem,
                'text' => trim((string) file_get_contents($file->getPathname())),
            ];
        }

        return $voices;
    }

    /**
     * @param  list<array{relative: string, absolute: string, stem: string, extension: string, kind: string}>  $records
     * @param  list<string|null>  $stems
     * @param  list<string>  $extensions
     * @return array{relative: string, absolute: string, stem: string, extension: string, kind: string}|null
     */
    private function match(array $records, array $stems, array $extensions, string $slug): ?array
    {
        $wanted = [];

        foreach ($stems as $stem) {
            if (is_string($stem) && $stem !== '') {
                $wanted[] = strtolower($stem);
            }
        }

        $wanted = array_values(array_unique($wanted));
        $matches = [];

        foreach ($records as $record) {
            if (! in_array($record['extension'], $extensions, true) || ! $this->owned($record['relative'], $slug)) {
                continue;
            }

            $stem = strtolower($record['stem']);
            $hit = in_array($stem, $wanted, true);

            if (! $hit) {
                foreach ($wanted as $token) {
                    if (str_ends_with($stem, '-'.$token)) {
                        $hit = true;
                        break;
                    }
                }
            }

            if ($hit) {
                $matches[] = $record;
            }
        }

        usort($matches, fn (array $left, array $right) => $left['relative'] <=> $right['relative']);

        return $matches[0] ?? null;
    }

    private function owned(string $relative, string $slug): bool
    {
        $relative = str_replace('\\', '/', $relative);
        $slug = preg_quote($slug, '#');

        return preg_match('#^(?:exhibits/'.$slug.'/|assets/[^/]+/'.$slug.'/|previews/'.$slug.'/)#', $relative) === 1;
    }

    private function packKey(string $id): string
    {
        if (preg_match('/(F\d+[a-z]?)$/i', $id, $match) === 1) {
            return 'F'.substr($match[1], 1);
        }

        return $id;
    }

    private function sceneNumber(string $key): ?int
    {
        if (preg_match('/F(\d+)/i', $key, $match) === 1) {
            return (int) $match[1];
        }

        if (preg_match('/(\d+)$/', $key, $match) === 1) {
            return (int) $match[1];
        }

        return null;
    }

    private function seconds(string $raw): ?float
    {
        if (preg_match('/(\d+):(\d{2})/', $raw, $match) === 1) {
            return ((int) $match[1] * 60) + (int) $match[2];
        }

        if (preg_match('/(\d+(?:\.\d+)?)\s*s/', $raw, $match) === 1) {
            return (float) $match[1];
        }

        return null;
    }

    private function truth(string $text): string
    {
        if (stripos($text, 'sourced') !== false || stripos($text, 'Surviving Books') !== false) {
            return 'documented';
        }

        if (stripos($text, 'parable') !== false || stripos($text, 'Travelers') !== false) {
            return 'legend';
        }

        return 'invented';
    }

    private function shotTruth(string $truth, string $text): string
    {
        if (stripos($text, 'story-prop') !== false || stripos($text, 'invented') !== false) {
            return 'invented';
        }

        return $truth;
    }

    private function heading(string $markdown): ?string
    {
        if (preg_match('/^#\s+(.+)$/m', $markdown, $match) !== 1) {
            return null;
        }

        return trim($match[1]);
    }

    private function wing(string $readme): string
    {
        if (stripos($readme, 'Surviving Books') !== false) {
            return 'Surviving Books';
        }

        if (stripos($readme, 'Travelers') !== false || stripos($readme, 'parable') !== false) {
            return 'Wheel of Travelers';
        }

        if (preg_match('/\*\*Wing:\*\*\s*(.+)$/m', $readme, $match) === 1) {
            return trim($match[1]);
        }

        return 'Wheel of Travelers';
    }

    private function section(string $markdown, string $heading): string
    {
        if (preg_match('/^##\s+'.preg_quote($heading, '/').'\s*\n([\s\S]*?)(?=^##\s|\z)/m', $markdown, $match) !== 1) {
            return '';
        }

        return trim($match[1]);
    }

    private function read(string $directory, string $name): string
    {
        $path = $directory.DIRECTORY_SEPARATOR.$name;

        return is_file($path) ? (string) file_get_contents($path) : '';
    }
}
