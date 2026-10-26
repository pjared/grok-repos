<?php

use App\Enums\CueType;
use App\Enums\ScenePackStatus;
use App\Models\ScenePackSubmission;
use App\Models\Shot;
use App\Workshop\SceneInbox;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;

it('adds a scene from the command and prints it as json', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $first = makeShot($sequence, 1, 10, 'Gala');
    $frame = Storage::disk('public')->path(tinyJpeg('frames/ring.jpg'));

    $this->artisan('workshop:add-scene', [
        '--exhibit' => 'gala-arrest',
        '--after' => $first->id,
        '--prompt' => "Iole's ring",
        '--duration' => '4',
        '--truth' => 'invented',
        '--frame' => $frame,
        '--narration' => 'She kept the ring.',
        '--plaque' => "Iole's arrest: 1923, 50%",
    ])->assertSuccessful()
        ->expectsOutputToContain("Iole's arrest: 1923, 50%");

    $added = $sequence->shots()->where('order', 2)->first();

    expect($added)->not->toBeNull()
        ->and($added->prompt)->toBe("Iole's ring")
        ->and($added->hasFrame())->toBeTrue()
        ->and($added->cues()->where('type', CueType::Narration)->value('text'))->toBe('She kept the ring.')
        ->and($added->cues()->where('type', CueType::Plaque)->value('text'))->toBe("Iole's arrest: 1923, 50%")
        ->and($first->fresh()->order)->toBe(1);
});

it('rejects a scene pack that is not json or is missing its frame', function () {
    Storage::fake('public');
    museum();
    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory);

    $broken = $directory.'/broken.json';
    File::put($broken, '{');

    $this->artisan('workshop:import-scenes', ['file' => $broken])
        ->assertFailed()
        ->expectsOutputToContain('Scene pack is not valid JSON');

    $missing = $directory.'/missing.json';
    File::put($missing, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [
            ['title' => 'The ring', 'frame' => 'frames/missing.jpg'],
        ],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $missing])
        ->assertFailed()
        ->expectsOutputToContain('missing frame "frames/missing.jpg"');

    expect(Shot::query()->count())->toBe(0);
});

it('leaves a pending inbox pack off the sequence until it is approved', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    makeShot($sequence, 1, 10, 'Gala');

    $inbox = storage_path('framework/testing/inbox-'.uniqid());
    File::ensureDirectoryExists($inbox.'/frames');
    config(['workshop.inbox' => $inbox]);

    $frame = $inbox.'/frames/ring.jpg';
    File::copy(Storage::disk('public')->path(tinyJpeg('frames/source-ring.jpg')), $frame);
    File::put($inbox.'/ring.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [[
            'title' => 'The ring',
            'prompt' => "Iole's ring",
            'narration' => 'She kept the ring.',
            'plaque' => "Iole's arrest: 1923, 50%",
            'frame' => 'frames/ring.jpg',
        ]],
    ]));

    $scanner = app(SceneInbox::class);
    $pending = $scanner->scan();

    expect($pending)->toHaveCount(1)
        ->and($pending->first()->status)->toBe(ScenePackStatus::Pending)
        ->and($sequence->shots()->count())->toBe(1);

    $scanner->reject($pending->first());

    expect($sequence->shots()->count())->toBe(1)
        ->and($pending->first()->fresh()->status)->toBe(ScenePackStatus::Rejected);

    File::put($inbox.'/again.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [[
            'title' => 'The ring',
            'narration' => 'She kept the ring.',
            'plaque' => "Iole's arrest: 1923, 50%",
            'frame' => 'frames/ring.jpg',
        ]],
    ]));

    $again = $scanner->scan()->first();
    $shots = $scanner->approve($again);

    expect($shots)->toHaveCount(1)
        ->and($sequence->shots()->count())->toBe(2)
        ->and($shots[0]->title)->toBe('The ring')
        ->and($shots[0]->cues()->where('type', CueType::Plaque)->value('text'))->toBe("Iole's arrest: 1923, 50%")
        ->and($again->fresh()->status)->toBe(ScenePackStatus::Approved);

    $invalid = $inbox.'/bad.json';
    File::put($invalid, '{');
    $row = $scanner->scan()->firstWhere('filename', 'bad.json');

    expect($row->status)->toBe(ScenePackStatus::Invalid)
        ->and($row->error)->toContain('not valid JSON')
        ->and($sequence->shots()->count())->toBe(2);

    expect(fn () => $scanner->approve($row))->toThrow(RuntimeException::class);

    expect(ScenePackSubmission::query()->where('status', ScenePackStatus::Pending)->count())->toBe(0);
});
