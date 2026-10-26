<?php

use App\Video\FakeProvider;
use App\Video\VideoProvider;
use App\Video\VideoProviderDisabled;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Storage;

it('uses the fake provider unless a real one is selected', function () {
    expect(app(VideoProvider::class))->toBeInstanceOf(FakeProvider::class);
});

it('does not call the network for the runway or kling stubs', function (string $name, string $flag) {
    Storage::fake('public');
    Http::fake();

    $frame = Storage::disk('public')->path(tinyJpeg());
    config([
        'video.provider' => $name,
        "video.providers.{$name}.enabled" => false,
    ]);

    expect(fn () => app(VideoProvider::class)->generate($frame, null, 'prompt', 1))
        ->toThrow(VideoProviderDisabled::class);

    config(["video.providers.{$name}.enabled" => true, "video.providers.{$name}.api_key" => 'test-key']);

    expect(fn () => app(VideoProvider::class)->generate($frame, null, 'prompt', 1))
        ->toThrow(VideoProviderDisabled::class);

    Http::assertNothingSent();
})->with([
    'runway' => ['runway', 'RUNWAY_ENABLED'],
    'kling' => ['kling', 'KLING_ENABLED'],
]);
