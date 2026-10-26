<?php

use App\Enums\CueType;
use App\Models\TextCue;
use App\Video\Drawtext;
use App\Video\EpisodeExporter;
use App\Video\Ffmpeg;
use App\Video\ShortsExporter;
use Illuminate\Support\Facades\Storage;

it('exports plaque text with an apostrophe, a colon, and a percent sign', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $shot = makeShot($sequence, 1, 0.4, 'The ring');
    $plaque = "Iole's arrest: 1923, 50%";
    TextCue::query()->create([
        'shot_id' => $shot->id,
        'type' => CueType::Plaque,
        'offset_s' => 0,
        'text' => $plaque,
        'voice' => null,
    ]);

    $seen = (object) ['texts' => [], 'filters' => []];
    $this->app->bind(Ffmpeg::class, function () use ($seen) {
        return new class($seen) extends Ffmpeg
        {
            public function __construct(private object $seen) {}

            public function run(array $args): void
            {
                foreach (Drawtext::files() as $file) {
                    $this->seen->texts[] = (string) file_get_contents($file);
                }

                foreach ($args as $index => $arg) {
                    if ($arg === '-vf') {
                        $this->seen->filters[] = $args[$index + 1];
                    }
                }

                parent::run($args);
            }
        };
    });

    $episode = app(EpisodeExporter::class)->export($sequence->fresh());
    $short = app(ShortsExporter::class)->export($sequence->fresh());

    expect(is_file(Storage::disk('public')->path($episode->path)))->toBeTrue()
        ->and(is_file(Storage::disk('public')->path($short->files[0]['path'])))->toBeTrue()
        ->and($seen->texts)->toContain($plaque)
        ->and(collect($seen->filters)->contains(fn (string $filter) => str_contains($filter, 'textfile=') && str_contains($filter, 'expansion=none')))->toBeTrue()
        ->and(collect($seen->filters)->contains(fn (string $filter) => str_contains($filter, "text='{$plaque}'")))->toBeFalse()
        ->and(Drawtext::files())->toBe([]);
});

it('draws from a textfile path that contains an apostrophe', function () {
    $filter = Drawtext::filter("Iole's ring");
    $stored = Drawtext::files()[0] ?? '';
    expect(str_starts_with($stored, storage_path('app/drawtext')))->toBeTrue()
        ->and($filter)->toContain('textfile=');
    Drawtext::cleanup();

    $directory = storage_path("framework/testing/o'hara-".uniqid());
    Drawtext::useDirectory($directory);
    $output = storage_path('framework/testing/drawtext-'.uniqid().'.mp4');

    try {
        $filter = Drawtext::filter("Iole's ring");
        $file = Drawtext::files()[0] ?? '';

        expect($file)->toContain("'")
            ->and(str_starts_with($file, $directory))->toBeTrue();

        app(Ffmpeg::class)->run([
            '-f', 'lavfi',
            '-i', 'color=c=0x22232b:s=320x180:d=0.3',
            '-vf', $filter,
            '-t', '0.2',
            '-r', '12',
            $output,
        ]);

        expect(is_file($output))->toBeTrue()
            ->and(filesize($output))->toBeGreaterThan(0);
    } finally {
        Drawtext::cleanup();
        Drawtext::useDirectory(null);

        if (is_file($output)) {
            unlink($output);
        }
    }
});

it('deletes drawtext files when burn-in fails', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $shot = makeShot($sequence, 1, 0.4, 'The ring');
    TextCue::query()->create([
        'shot_id' => $shot->id,
        'type' => CueType::Plaque,
        'offset_s' => 0,
        'text' => "Iole's arrest: 1923, 50%",
        'voice' => null,
    ]);

    $this->app->bind(Ffmpeg::class, function () {
        return new class extends Ffmpeg
        {
            public function run(array $args): void
            {
                if (in_array('-vf', $args, true)) {
                    throw new RuntimeException('forced failure');
                }

                parent::run($args);
            }
        };
    });

    expect(fn () => app(EpisodeExporter::class)->export($sequence->fresh()))
        ->toThrow(RuntimeException::class, 'forced failure');

    expect(Drawtext::files())->toBe([]);
});
