<?php

use App\Enums\CueType;
use App\Enums\ShotStatus;
use App\Enums\TruthTag;
use App\Models\TextCue;
use App\Sections\Editor\Livewire\Workshop;
use App\Video\EpisodeExporter;
use App\Video\ShortsExporter;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;

it('appends a draft scene and selects it', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    makeShot($sequence, 1, 10, 'Gala');

    $component = Livewire::test(Workshop::class)->call('addScene');

    $shots = $sequence->shots()->orderBy('order')->get();
    $added = $shots->last();

    expect($shots)->toHaveCount(2)
        ->and($added->title)->toBe('New scene')
        ->and($added->frame_path)->toBeNull()
        ->and($added->prompt)->toBe('')
        ->and($added->model)->toBe('FLUX')
        ->and((float) $added->duration_s)->toBe(4.0)
        ->and($added->truth_tag)->toBe(TruthTag::Invented)
        ->and($added->status)->toBe(ShotStatus::Draft)
        ->and($added->order)->toBe(2);

    $component->assertSet('selectedShotId', $added->id)
        ->assertSet('prompt', '')
        ->assertSet('model', 'FLUX')
        ->assertSet('duration', '4.0')
        ->assertSet('truthTag', 'invented')
        ->assertSee('Empty frame');
});

it('inserts after the selected shot and keeps cues on their own shots', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $first = makeShot($sequence, 1, 10, 'Gala');
    $second = makeShot($sequence, 2, 20, 'The pearl');
    $narration = TextCue::query()->create([
        'shot_id' => $second->id,
        'type' => CueType::Narration,
        'offset_s' => 1,
        'text' => 'The pearl was gone.',
        'voice' => 'MoT Docent 3',
    ]);
    $plaque = TextCue::query()->create([
        'shot_id' => $first->id,
        'type' => CueType::Plaque,
        'offset_s' => 0,
        'text' => 'Arrested in 1923 for a murder…',
        'voice' => null,
    ]);

    Livewire::test(Workshop::class)
        ->call('selectShot', $first->id)
        ->call('insertAfter');

    expect($sequence->shots()->orderBy('order')->pluck('title')->all())->toBe([
        'Gala',
        'New scene',
        'The pearl',
    ])
        ->and($narration->fresh()->shot_id)->toBe($second->id)
        ->and($plaque->fresh()->shot_id)->toBe($first->id)
        ->and($first->fresh()->order)->toBe(1)
        ->and($second->fresh()->order)->toBe(3);
});

it('refuses to render or export a shot that has no frame', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    $shot = makeShot($sequence, 1, 0.4, 'New scene');
    $shot->update(['frame_path' => null]);

    expect(fn () => app(EpisodeExporter::class)->export($sequence->fresh()))
        ->toThrow(RuntimeException::class, 'no frame');

    expect(fn () => app(ShortsExporter::class)->export($sequence->fresh()))
        ->toThrow(RuntimeException::class, 'no frame');

    Livewire::test(Workshop::class)
        ->call('selectShot', $shot->id)
        ->call('regenerate')
        ->assertSet('notice', fn (string $notice) => str_contains($notice, 'has no frame'))
        ->call('queueEpisode')
        ->assertSet('notice', fn (string $notice) => str_contains($notice, 'Cannot render or export'));

    expect($shot->fresh()->clip_path)->toBeNull()
        ->and($sequence->exports()->count())->toBe(0);
});
