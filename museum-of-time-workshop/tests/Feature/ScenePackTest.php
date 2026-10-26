<?php

use App\Enums\CueType;
use App\Enums\ScenePackStatus;
use App\Models\ScenePackSubmission;
use App\Models\Shot;
use App\Sections\Editor\Livewire\Workshop;
use App\Workshop\SceneInbox;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;

it('adds a scene from the command and prints it as json', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $first = makeShot($sequence, 1, 10, 'Gala');
    $frame = Storage::disk('public')->path(tinyJpeg('frames/ring.jpg'));

    $this->artisan('workshop:add-scene', [
        '--exhibit' => 'gala-arrest',
        '--after-id' => $first->id,
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

it('inserts with after_id or after_order and does not guess between them', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $removed = makeShot($sequence, 1, 10, 'Gone');
    $removed->delete();
    $first = makeShot($sequence, 1, 10, 'Gala');
    $second = makeShot($sequence, 2, 8, 'The pearl');
    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory);

    expect($first->id)->not->toBe(1);

    $orderPack = $directory.'/order.json';
    File::put($orderPack, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'After order', 'after_order' => 1]],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $orderPack])->assertSuccessful();

    expect($sequence->shots()->orderBy('order')->pluck('title')->all())
        ->toBe(['Gala', 'After order', 'The pearl']);

    $missingId = $directory.'/missing-id.json';
    File::put($missingId, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'Missing', 'after_id' => 1]],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $missingId])
        ->assertFailed()
        ->expectsOutputToContain('No shot id 1');

    $idPack = $directory.'/id.json';
    File::put($idPack, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'After id', 'after_id' => $second->id]],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $idPack])->assertSuccessful();

    expect($sequence->shots()->orderBy('order')->pluck('title')->all())
        ->toBe(['Gala', 'After order', 'The pearl', 'After id']);

    $both = $directory.'/both.json';
    File::put($both, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'Both', 'after_id' => $first->id, 'after_order' => 1]],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $both])
        ->assertFailed()
        ->expectsOutputToContain('cannot set both after_id and after_order');

    $legacy = $directory.'/legacy.json';
    File::put($legacy, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'Legacy', 'after' => 1]],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $legacy])
        ->assertFailed()
        ->expectsOutputToContain('ambiguous "after"');
});

it('rejects frame paths that leave the pack', function () {
    Storage::fake('public');
    museum();
    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory.'/frames');
    $outside = storage_path('framework/testing/outside-'.uniqid().'.jpg');
    File::copy(Storage::disk('public')->path(tinyJpeg('frames/outside-source.jpg')), $outside);

    $parent = $directory.'/parent.json';
    File::put($parent, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'Escape', 'frame' => '../secret.jpg']],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $parent])
        ->assertFailed()
        ->expectsOutputToContain('must stay inside the pack');

    $absolute = $directory.'/absolute.json';
    File::put($absolute, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'Escape', 'frame' => $outside]],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $absolute])
        ->assertFailed()
        ->expectsOutputToContain('must stay inside the pack');

    symlink($outside, $directory.'/frames/link.jpg');
    $linked = $directory.'/link.json';
    File::put($linked, json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'Escape', 'frame' => 'frames/link.jpg']],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $linked])
        ->assertFailed()
        ->expectsOutputToContain('must stay inside the pack');

    expect(Shot::query()->count())->toBe(0)
        ->and(Storage::disk('public')->allFiles())->not->toContain('frames/link.jpg');
});

it('removes copied frames when a pack import rolls back', function () {
    Storage::fake('public');
    museum();
    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory.'/frames');
    File::copy(Storage::disk('public')->path(tinyJpeg('frames/kept.jpg')), $directory.'/frames/kept.jpg');
    File::put($directory.'/rollback.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [
            ['title' => 'Kept', 'frame' => 'frames/kept.jpg'],
            ['title' => 'Broken', 'truth' => 'rumor'],
        ],
    ]));

    $this->artisan('workshop:import-scenes', ['file' => $directory.'/rollback.json'])
        ->assertFailed()
        ->expectsOutputToContain('Truth tag must be documented, legend, or invented.');

    expect(Shot::query()->count())->toBe(0)
        ->and(collect(Storage::disk('public')->allFiles())->filter(fn (string $path) => str_starts_with($path, 'scenes/'))->all())
        ->toBe([]);
});

it('keeps a zipped import pending until it is approved', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    makeShot($sequence, 1, 10, 'Gala');

    $inbox = storage_path('framework/testing/inbox-'.uniqid());
    config(['workshop.inbox' => $inbox]);

    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory);
    $frame = $directory.'/ring.jpg';
    File::copy(Storage::disk('public')->path(tinyJpeg('frames/zip-ring.jpg')), $frame);

    $zipPath = $directory.'/ring.zip';
    $zip = new \ZipArchive;
    $zip->open($zipPath, \ZipArchive::CREATE);
    $zip->addFromString('pack.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [[
            'title' => 'The ring',
            'frame' => 'ring.jpg',
            'plaque' => "Iole's arrest: 1923, 50%",
        ]],
    ]));
    $zip->addFile($frame, 'ring.jpg');
    $zip->close();

    $upload = UploadedFile::fake()->createWithContent('ring.zip', file_get_contents($zipPath));

    Livewire::test(Workshop::class)
        ->set('packUpload', $upload)
        ->call('importPack')
        ->assertSet('notice', 'ring.zip is waiting for approval.')
        ->assertSee('Approve');

    expect($sequence->shots()->count())->toBe(1);

    $submission = ScenePackSubmission::query()->first();
    expect($submission->status)->toBe(ScenePackStatus::Pending)
        ->and($submission->filename)->toBe('ring.zip');

    Livewire::test(Workshop::class)->call('approvePack', $submission->id);

    $added = $sequence->shots()->orderBy('order')->get()->last();

    expect($sequence->shots()->count())->toBe(2)
        ->and($added->title)->toBe('The ring')
        ->and($added->hasFrame())->toBeTrue()
        ->and($added->cues()->where('type', CueType::Plaque)->value('text'))->toBe("Iole's arrest: 1923, 50%");
});

it('shows a notice when importing a pack throws', function () {
    Storage::fake('public');
    museum();
    $inbox = storage_path('framework/testing/inbox-'.uniqid());
    config(['workshop.inbox' => $inbox]);

    Livewire::test(Workshop::class)
        ->set('packUpload', UploadedFile::fake()->create('notes.txt', 10, 'text/plain'))
        ->call('importPack')
        ->assertSet('notice', 'The pack upload field must be a file of type: zip.');

    $scanner = Mockery::mock(SceneInbox::class);
    $scanner->shouldReceive('scan')->andReturn(collect());
    $scanner->shouldReceive('receive')->andThrow(new RuntimeException('disk full'));
    app()->instance(SceneInbox::class, $scanner);

    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory);
    $zipPath = $directory.'/pack.zip';
    $zip = new \ZipArchive;
    $zip->open($zipPath, \ZipArchive::CREATE);
    $zip->addFromString('pack.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'The ring']],
    ]));
    $zip->close();

    Livewire::test(Workshop::class)
        ->set('packUpload', UploadedFile::fake()->createWithContent('pack.zip', file_get_contents($zipPath)))
        ->call('importPack')
        ->assertSet('notice', 'disk full');

    expect(Shot::query()->count())->toBe(0)
        ->and(ScenePackSubmission::query()->count())->toBe(0);
});

it('does not rehash an unchanged inbox file', function () {
    Storage::fake('public');
    museum();
    $inbox = storage_path('framework/testing/inbox-'.uniqid());
    File::ensureDirectoryExists($inbox);
    config(['workshop.inbox' => $inbox]);
    File::put($inbox.'/ring.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [['title' => 'The ring']],
    ]));

    $scanner = app(SceneInbox::class);
    $scanner->scan();
    $hashed = SceneInbox::$hashCount;
    $scanner->scan();

    expect($hashed)->toBe(1)
        ->and(SceneInbox::$hashCount)->toBe(1)
        ->and(ScenePackSubmission::query()->count())->toBe(1);
});

it('rejects a zip entry that leaves the pack', function () {
    Storage::fake('public');
    museum();
    $inbox = storage_path('framework/testing/inbox-'.uniqid());
    File::ensureDirectoryExists($inbox);
    config(['workshop.inbox' => $inbox]);

    $zipPath = $inbox.'/evil.zip';
    $zip = new \ZipArchive;
    $zip->open($zipPath, \ZipArchive::CREATE);
    $zip->addFromString('../secret.txt', 'nope');
    $zip->close();

    $row = app(SceneInbox::class)->scan()->firstWhere('filename', 'evil.zip');

    expect($row->status)->toBe(ScenePackStatus::Invalid)
        ->and($row->error)->toContain('inside the pack')
        ->and(is_file(dirname($inbox).'/secret.txt'))->toBeFalse();
});
