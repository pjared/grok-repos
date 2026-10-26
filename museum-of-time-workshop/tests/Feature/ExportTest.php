<?php

use App\Enums\CueType;
use App\Enums\TruthTag;
use App\Jobs\GenerateShotJob;
use App\Models\Sequence;
use App\Models\TextCue;
use App\Video\EpisodeExporter;
use App\Video\ShortsExporter;
use App\Video\Stamp;
use App\Video\VideoProvider;
use Illuminate\Support\Facades\Storage;

it('seeds, renders with the fake provider, and exports the episode and the shorts', function () {
    Storage::fake('public');

    $this->artisan('workshop:seed-gala')->assertSuccessful();

    $sequence = Sequence::query()->firstOrFail();
    $provider = app(VideoProvider::class);

    foreach ($sequence->shots()->orderBy('order')->get() as $shot) {
        (new GenerateShotJob($shot->id))->handle($provider);
        expect(is_file(Storage::disk('public')->path($shot->fresh()->clip_path)))->toBeTrue();
    }

    $episode = app(EpisodeExporter::class)->export($sequence->fresh());
    $episodePath = Storage::disk('public')->path($episode->path);
    $episodeProbe = ffprobe($episodePath);

    expect(is_file($episodePath))->toBeTrue()
        ->and($episode->warnings)->toBe([])
        ->and(collect($episodeProbe['streams'])->pluck('codec_type')->all())->toContain('video', 'subtitle')
        ->and((float) $episodeProbe['format']['duration'])->toBeGreaterThan(190)
        ->and((float) $episodeProbe['format']['duration'])->toBeLessThan(210);

    $shorts = app(ShortsExporter::class)->export($sequence->fresh());

    expect($shorts->files)->toHaveCount(4)
        ->and($shorts->warnings)->toBe([]);

    foreach ($shorts->files as $file) {
        expect($file['stamp'])->toBe(Stamp::text('Unit 14', 'Gala Arrest', $file['number'], $file['total']));
        $path = Storage::disk('public')->path($file['path']);
        $probe = ffprobe($path);
        expect(is_file($path))->toBeTrue()
            ->and(collect($probe['streams'])->pluck('codec_type'))->toContain('video', 'subtitle')
            ->and((float) $probe['format']['duration'])->toBeGreaterThanOrEqual(45)
            ->and((float) $probe['format']['duration'])->toBeLessThanOrEqual(62);
    }
});

it('warns and skips plaque burn-in when the shot is invented', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $shot = makeShot($sequence, 1, 0.6, 'Doors slam');
    $shot->update(['truth_tag' => TruthTag::Invented]);
    TextCue::query()->create([
        'shot_id' => $shot->id,
        'type' => CueType::Plaque,
        'offset_s' => 0,
        'text' => 'This invented line must not be presented as fact.',
        'voice' => null,
    ]);

    $result = app(EpisodeExporter::class)->export($sequence->fresh());

    expect(implode(' ', $result->warnings))->toContain('Invented shot "Doors slam"')
        ->and(is_file(Storage::disk('public')->path($result->path)))->toBeTrue();

    $shot->refresh();
    expect($shot->clip_path)->not->toBeNull();
});
