<?php

use App\Enums\CueType;
use App\Enums\ScenePackStatus;
use App\Enums\ShotStatus;
use App\Enums\TruthTag;
use App\Models\ScenePackSubmission;
use App\Models\Shot;
use App\Providers\AppServiceProvider;
use App\Sections\Assets\Livewire\Index;
use App\Sections\Editor\Livewire\Workshop;
use App\Video\EpisodeExporter;
use App\Video\ShortsExporter;
use App\Video\SubtitleBuilder;
use App\Workshop\AddScene;
use App\Workshop\ExhibitImporter;
use App\Workshop\ExhibitNotes;
use App\Workshop\ExhibitSequences;
use App\Workshop\MediaLibrary;
use App\Workshop\SceneInbox;
use App\Workshop\ScenePack;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;
use Symfony\Component\Process\Process;

it('lists media by exhibit and caches ffprobe by mtime', function () {
    [$archive, $media] = sampleArchive();
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
    ]);

    $library = app(MediaLibrary::class);
    $library->link();
    $groups = $library->groups();
    $probes = MediaLibrary::$probeCount;
    $library->groups();

    $sample = collect($groups)->firstWhere('exhibit', 'sample-exhibit');
    $names = collect($sample['files'])->pluck('name')->all();
    $clip = collect($sample['files'])->firstWhere('name', 'F1.mp4');

    expect(is_link(storage_path('app/public/media')))->toBeTrue()
        ->and(realpath(storage_path('app/public/media')))->toBe(realpath($media))
        ->and($sample['label'])->toBe('Sample Exhibit')
        ->and($names)->toContain('F1.mp4', 'sample-01.mp3', 'F1.jpg')
        ->and($clip['duration'])->toBeGreaterThan(0)
        ->and($clip['duration_label'])->not->toBeNull()
        ->and(MediaLibrary::$probeCount)->toBe($probes)
        ->and($probes)->toBe(2);
});

it('holds an exhibit import in the inbox until it is approved', function () {
    [$archive, $media, $inbox] = sampleArchive();
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
        'workshop.inbox' => $inbox,
    ]);

    $this->artisan('workshop:import-exhibit', ['slug' => 'sample-exhibit'])
        ->assertSuccessful()
        ->expectsOutputToContain('Waiting for approval.');

    expect(Shot::query()->count())->toBe(0);

    $submission = ScenePackSubmission::query()->first();
    expect($submission->status)->toBe(ScenePackStatus::Pending)
        ->and($submission->summary['exhibit'])->toBe('sample-exhibit');

    $shots = app(SceneInbox::class)->approve($submission);
    $shot = $shots[0];

    expect($submission->fresh()->status)->toBe(ScenePackStatus::Approved)
        ->and($shot->title)->toBe('Empty Hall')
        ->and($shot->clip_path)->toBe('media/exhibits/sample-exhibit/F1.mp4')
        ->and($shot->frame_path)->toBe('media/previews/sample-exhibit/F1.jpg')
        ->and($shot->truth_tag)->toBe(TruthTag::Legend)
        ->and($shot->hasFrame())->toBeTrue()
        ->and(is_file(storage_path('app/public/'.$shot->clip_path)))->toBeTrue()
        ->and($shot->cues()->where('type', CueType::Narration)->value('text'))->toBe('Welcome to the wing.')
        ->and($shot->cues()->where('type', CueType::Narration)->value('audio_path'))->toBe('media/assets/audio/sample-exhibit/sample-01.mp3')
        ->and($shot->cues()->where('type', CueType::Plaque)->value('text'))->toBe('She kept the feeling.');
});

it('shows a media preview and imports the exhibit as pending', function () {
    [$archive, $media, $inbox] = sampleArchive();
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
        'workshop.inbox' => $inbox,
    ]);

    Livewire::test(Index::class)
        ->assertSee('F1.mp4')
        ->assertSee('Import exhibit')
        ->call('importExhibit', 'sample-exhibit')
        ->assertSet('notice', 'sample-exhibit.json is waiting for approval.');

    expect(Shot::query()->count())->toBe(0)
        ->and(ScenePackSubmission::query()->where('status', ScenePackStatus::Pending)->count())->toBe(1);
});

it('rejects a media path that leaves the library', function () {
    [$archive, $media] = sampleArchive();
    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory);
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
    ]);
    File::put($directory.'/escape.json', json_encode([
        'exhibit' => 'gala-arrest',
        'title' => 'Sample Exhibit',
        'wing' => 'Wheel of Travelers',
        'scenes' => [[
            'title' => 'Escape',
            'clip_path' => 'media/../secret.mp4',
        ]],
    ]));

    expect(fn () => ScenePack::load($directory.'/escape.json')->import(app(AddScene::class)))
        ->toThrow(InvalidArgumentException::class, 'must stay inside the media library');
    expect(Shot::query()->count())->toBe(0);
});

it('reads the iole exhibit notes from the archive', function () {
    config(['workshop.archive' => dirname(base_path()).'/museum-of-time']);
    $pack = app(ExhibitNotes::class)->pack('iole-uncopied-canvas');
    $titles = collect($pack['scenes'])->pluck('title');
    $scenes = array_values($pack['scenes']);

    expect($pack['truth'])->toBe('legend')
        ->and($pack['wing'])->toBe('Wheel of Travelers')
        ->and($titles->contains(fn (string $title) => str_contains($title, 'Empty Hall')))->toBeTrue()
        ->and(collect($pack['scenes'])->pluck('prompt')->implode("\n"))->toContain('flawless high-resolution')
        ->and(count($scenes))->toBeGreaterThan(1)
        ->and(array_key_exists('after', $scenes[0]))->toBeFalse()
        ->and(array_key_exists('after_id', $scenes[0]))->toBeFalse()
        ->and(array_key_exists('after_order', $scenes[0]))->toBeFalse();

    foreach (array_slice($scenes, 1) as $index => $scene) {
        expect($scene['after_order'])->toBe($index + 1)
            ->and(array_key_exists('after', $scene))->toBeFalse()
            ->and(array_key_exists('after_id', $scene))->toBeFalse();
    }
});

it('emits after_id when the exhibit already has a shot', function () {
    [$archive, $media, $inbox] = sampleArchive();
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
        'workshop.inbox' => $inbox,
    ]);

    $sequence = ExhibitSequences::provision(
        'sample-exhibit',
        'Sample Exhibit',
        'Wheel of Travelers',
        'Main Hall',
        'legend',
    );
    $existing = app(AddScene::class)->append($sequence, ['title' => 'Already there']);

    $this->artisan('workshop:import-exhibit', ['slug' => 'sample-exhibit'])
        ->assertSuccessful()
        ->expectsOutputToContain('Waiting for approval.');

    $submission = ScenePackSubmission::query()->first();
    $pack = json_decode((string) file_get_contents($submission->stored_path), true, 512, JSON_THROW_ON_ERROR);

    expect($pack['scenes'][0]['after_id'])->toBe($existing->id)
        ->and(array_key_exists('after', $pack['scenes'][0]))->toBeFalse()
        ->and(array_key_exists('after_order', $pack['scenes'][0]))->toBeFalse();

    $shots = app(SceneInbox::class)->approve($submission->fresh());

    expect($shots[0]->title)->toBe('Empty Hall')
        ->and($shots[0]->order)->toBe(2)
        ->and($existing->fresh()->order)->toBe(1);
});

it('keeps an exhibit draft when the only matching clip belongs to another exhibit', function () {
    $archive = storage_path('framework/testing/archive-'.uniqid());
    $media = storage_path('framework/testing/media-'.uniqid());
    $inbox = storage_path('framework/testing/inbox-'.uniqid());
    $notes = $archive.'/exhibits/exhibit-a';
    File::ensureDirectoryExists($notes);
    File::put($notes.'/README.md', "# Exhibit A\n**Wing:** Travelers (parable)\n");
    File::put($notes.'/script.md', "### Scene 1 — Empty Hall\n**Est. duration:** 0:08\n\nA quiet room.\n");
    File::put($notes.'/flux-prompts.md', "### F1 · 8s\nOne lit pedestal.\n");
    $foreign = $media.'/exhibits/exhibit-b/wing-F1.mp4';
    renderMedia($foreign, 'mp4');

    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
        'workshop.inbox' => $inbox,
    ]);

    $this->artisan('workshop:import-exhibit', ['slug' => 'exhibit-a'])->assertSuccessful();

    $submission = ScenePackSubmission::query()->first();
    $pack = json_decode((string) file_get_contents($submission->stored_path), true, 512, JSON_THROW_ON_ERROR);
    $shots = app(SceneInbox::class)->approve($submission);

    expect($pack['scenes'][0])->not->toHaveKey('clip_path')
        ->and($shots[0]->status)->toBe(ShotStatus::Draft)
        ->and($shots[0]->clip_path)->toBeNull()
        ->and(is_file($foreign))->toBeTrue();
});

it('does not link the media library during boot', function () {
    $library = Mockery::mock(MediaLibrary::class);
    $library->shouldNotReceive('link');
    $this->app->instance(MediaLibrary::class, $library);

    (new AppServiceProvider($this->app))->boot();
});

it('links the media library once per request', function () {
    $root = storage_path('framework/testing/media-once-'.uniqid());
    File::ensureDirectoryExists($root);
    $link = storage_path('app/public/media');

    if (is_link($link)) {
        unlink($link);
    }

    config(['workshop.media_root' => $root]);
    MediaLibrary::forgetCache();
    File::partialMock()->shouldReceive('link')->once()->andReturnUsing(function (string $target, string $path) {
        symlink($target, $path);
    });

    app(MediaLibrary::class)->link();
    app(MediaLibrary::class)->link();

    expect(is_link($link))->toBeTrue()
        ->and(realpath($link))->toBe(realpath($root));
});

it('replaces a stale directory junction with rmdir', function () {
    $root = storage_path('framework/testing/media-junction-'.uniqid());
    File::ensureDirectoryExists($root);
    $link = storage_path('app/public/media');

    if (is_link($link)) {
        unlink($link);
    }

    File::ensureDirectoryExists($link);
    config(['workshop.media_root' => $root]);
    MediaLibrary::forgetCache();
    app(MediaLibrary::class)->link();

    expect(is_link($link))->toBeTrue()
        ->and(realpath($link))->toBe(realpath($root));
});

it('groups media by a path segment', function () {
    [$archive, $media] = sampleArchive();
    renderMedia($media.'/library/sample-exhibit-extra.mp4', 'mp4');
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
    ]);

    $groups = collect(app(MediaLibrary::class)->groups());
    $sample = $groups->firstWhere('exhibit', 'sample-exhibit');
    $library = $groups->firstWhere('exhibit', 'library');

    expect(collect($sample['files'])->pluck('name'))->not->toContain('sample-exhibit-extra.mp4')
        ->and(collect($library['files'])->pluck('name'))->toContain('sample-exhibit-extra.mp4');
});

it('shows the invalid exhibit error in the editor', function () {
    museum();
    $submission = new ScenePackSubmission([
        'filename' => 'gala-arrest.json',
        'status' => ScenePackStatus::Invalid,
        'error' => 'Scene pack must include an exhibit and at least one scene.',
    ]);
    $importer = Mockery::mock(ExhibitImporter::class);
    $importer->shouldReceive('submit')->once()->with('gala-arrest')->andReturn($submission);
    $this->app->instance(ExhibitImporter::class, $importer);

    Livewire::test(Workshop::class)
        ->call('importCurrentExhibit')
        ->assertSet('notice', 'Scene pack must include an exhibit and at least one scene.');
});

it('imports audio-only narration without a subtitle entry', function () {
    [$archive, $media] = sampleArchive();
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
    ]);
    app(MediaLibrary::class)->link();
    museum();

    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory);
    File::put($directory.'/audio-only.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [[
            'title' => 'Voice only',
            'frame_path' => 'media/previews/sample-exhibit/F1.jpg',
            'clip_path' => 'media/exhibits/sample-exhibit/F1.mp4',
            'narration_audio' => 'media/assets/audio/sample-exhibit/sample-01.mp3',
        ]],
    ], JSON_THROW_ON_ERROR));

    $shots = ScenePack::load($directory.'/audio-only.json')->import(app(AddScene::class));
    $cue = $shots[0]->cues()->where('type', CueType::Narration)->first();
    $srt = SubtitleBuilder::write([
        ['start' => 0.0, 'end' => 4.0, 'text' => $cue->text],
    ]);

    expect($cue->text)->toBeNull()
        ->and($cue->audio_path)->toBe('media/assets/audio/sample-exhibit/sample-01.mp3')
        ->and(trim((string) file_get_contents($srt)))->toBe('');

    $sequence = $shots[0]->sequence;
    $episode = app(EpisodeExporter::class)->export($sequence);
    $episodeProbe = ffprobe(Storage::disk('public')->path($episode->path));
    $shorts = app(ShortsExporter::class)->export($sequence->fresh());
    $shortProbe = ffprobe(Storage::disk('public')->path($shorts->files[0]['path']));

    expect(collect($episodeProbe['streams'])->pluck('codec_type'))->not->toContain('subtitle')
        ->and(collect($shortProbe['streams'])->pluck('codec_type'))->not->toContain('subtitle');

    @unlink($srt);
});

it('shows a notice on the assets page when the media link fails', function () {
    [$archive, $media, $inbox] = sampleArchive();
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
        'workshop.inbox' => $inbox,
    ]);

    $link = storage_path('app/public/media');

    if (is_link($link)) {
        unlink($link);
    }

    File::partialMock()->shouldReceive('link')->andThrow(new RuntimeException('link failed'));

    Livewire::test(Index::class)
        ->assertSee('link failed')
        ->assertSee('F1.mp4');
});

it('leaves media originals in place when an import rolls back', function () {
    [$archive, $media] = sampleArchive();
    config([
        'workshop.archive' => $archive,
        'workshop.media_root' => $media,
    ]);
    app(MediaLibrary::class)->link();

    $clip = $media.'/exhibits/sample-exhibit/F1.mp4';
    $preview = $media.'/previews/sample-exhibit/F1.jpg';
    $audio = $media.'/assets/audio/sample-exhibit/sample-01.mp3';
    $clipHash = hash_file('sha256', $clip);
    $previewHash = hash_file('sha256', $preview);
    $audioHash = hash_file('sha256', $audio);
    $scenesDir = storage_path('app/public/scenes');
    $before = is_dir($scenesDir)
        ? collect(File::allFiles($scenesDir))->map->getPathname()->sort()->values()->all()
        : [];
    museum();

    $directory = storage_path('framework/testing/scene-pack-'.uniqid());
    File::ensureDirectoryExists($directory.'/frames');
    File::copy(Storage::disk('public')->path(tinyJpeg('frames/rollback-kept.jpg')), $directory.'/frames/kept.jpg');
    File::put($directory.'/rollback.json', json_encode([
        'exhibit' => 'gala-arrest',
        'scenes' => [
            [
                'title' => 'Linked',
                'frame' => 'frames/kept.jpg',
                'clip_path' => 'media/exhibits/sample-exhibit/F1.mp4',
                'narration_audio' => 'media/assets/audio/sample-exhibit/sample-01.mp3',
            ],
            [
                'title' => 'Broken',
                'truth' => 'rumor',
                'frame_path' => 'media/previews/sample-exhibit/F1.jpg',
            ],
        ],
    ], JSON_THROW_ON_ERROR));

    expect(fn () => ScenePack::load($directory.'/rollback.json')->import(app(AddScene::class)))
        ->toThrow(InvalidArgumentException::class, 'Truth tag must be documented, legend, or invented.');

    expect(Shot::query()->count())->toBe(0)
        ->and(is_file($clip))->toBeTrue()
        ->and(is_file($preview))->toBeTrue()
        ->and(is_file($audio))->toBeTrue()
        ->and(hash_file('sha256', $clip))->toBe($clipHash)
        ->and(hash_file('sha256', $preview))->toBe($previewHash)
        ->and(hash_file('sha256', $audio))->toBe($audioHash)
        ->and(is_dir($scenesDir) ? collect(File::allFiles($scenesDir))->map->getPathname()->sort()->values()->all() : [])
        ->toBe($before);
});

/**
 * @return array{0: string, 1: string, 2: string}
 */
function sampleArchive(): array
{
    $archive = storage_path('framework/testing/archive-'.uniqid());
    $media = storage_path('framework/testing/media-'.uniqid());
    $inbox = storage_path('framework/testing/inbox-'.uniqid());
    $notes = $archive.'/exhibits/sample-exhibit';
    File::ensureDirectoryExists($notes.'/vo');
    File::put($notes.'/README.md', <<<'MD'
# Sample Exhibit
**Wing:** Travelers (parable)

## Plaque
She kept the feeling.
MD);
    File::put($notes.'/script.md', <<<'MD'
### Scene 1 — Empty Hall
**Est. duration:** 0:16

Welcome to the wing.

**Shot lock:** One lit pedestal.
MD);
    File::put($notes.'/flux-prompts.md', <<<'MD'
### F1 · 8s
A dark wing and one lit pedestal.
MD);
    File::put($notes.'/vo/sample-01.txt', 'Welcome to the wing.');

    renderMedia($media.'/exhibits/sample-exhibit/F1.mp4', 'mp4');
    renderMedia($media.'/assets/audio/sample-exhibit/sample-01.mp3', 'mp3');
    renderMedia($media.'/previews/sample-exhibit/F1.jpg', 'jpg');

    return [$archive, $media, $inbox];
}

function renderMedia(string $path, string $kind): void
{
    File::ensureDirectoryExists(dirname($path));

    if ($kind === 'jpg') {
        $image = imagecreatetruecolor(160, 90);
        imagejpeg($image, $path, 80);
        imagedestroy($image);

        return;
    }

    $source = $kind === 'mp3'
        ? ['-f', 'lavfi', '-i', 'sine=frequency=440:duration=0.4']
        : ['-f', 'lavfi', '-i', 'color=c=0x22232b:s=160x90:d=0.4', '-r', '12'];
    $process = new Process(array_merge(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error'], $source, [$path]));
    $process->setTimeout(30);
    $process->run();

    expect($process->isSuccessful())->toBeTrue();
}
