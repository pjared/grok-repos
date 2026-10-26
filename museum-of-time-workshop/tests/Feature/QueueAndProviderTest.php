<?php

use App\Enums\ShotStatus;
use App\Jobs\GenerateShotJob;
use App\Video\FakeProvider;
use App\Video\VideoProvider;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;

it('renders a ken burns clip and a crossfade clip', function () {
    Storage::fake('public');
    $start = Storage::disk('public')->path(tinyJpeg('frames/a.jpg'));
    $end = Storage::disk('public')->path(tinyJpeg('frames/b.jpg'));

    $provider = app(FakeProvider::class);
    $single = $provider->generate($start, null, 'ken burns', 0.6);
    $pair = $provider->generate($start, $end, 'crossfade', 0.8);

    expect(is_file($single))->toBeTrue()
        ->and(is_file($pair))->toBeTrue()
        ->and(collect(ffprobe($single)['streams'])->pluck('codec_type'))->toContain('video')
        ->and(collect(ffprobe($pair)['streams'])->pluck('codec_type'))->toContain('video')
        ->and((float) ffprobe($single)['format']['duration'])->toBeGreaterThan(0.4);
});

it('queues generation on the database driver and the worker finishes the clip', function () {
    Storage::fake('public');
    config(['queue.default' => 'database']);

    ['sequence' => $sequence] = museum();
    $shot = makeShot($sequence, 1, 0.5, 'Gala');

    GenerateShotJob::dispatch($shot->id);

    expect(DB::table('jobs')->count())->toBe(1);

    $this->artisan('queue:work', ['--once' => true, '--stop-when-empty' => true])->assertSuccessful();

    $shot->refresh();
    expect($shot->status)->toBe(ShotStatus::Ready)
        ->and($shot->clip_path)->not->toBeNull()
        ->and(is_file(Storage::disk('public')->path($shot->clip_path)))->toBeTrue();

    expect(app(VideoProvider::class))->toBeInstanceOf(FakeProvider::class);
});
