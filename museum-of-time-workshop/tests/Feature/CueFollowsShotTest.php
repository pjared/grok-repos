<?php

use App\Enums\CueType;
use App\Models\TextCue;
use App\Sections\Editor\Livewire\Workshop;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;

it('keeps cues on their shot when shots are reordered', function () {
    Storage::fake('public');
    ['sequence' => $sequence] = museum();

    $first = makeShot($sequence, 1, 10, 'Gala');
    $second = makeShot($sequence, 2, 20, 'Empty setting');
    $third = makeShot($sequence, 3, 30, 'Doors slam');

    $moved = TextCue::query()->create([
        'shot_id' => $third->id,
        'type' => CueType::Narration,
        'offset_s' => 1,
        'text' => 'The doors slammed.',
        'voice' => 'MoT Docent 3',
    ]);
    $stays = TextCue::query()->create([
        'shot_id' => $first->id,
        'type' => CueType::Plaque,
        'offset_s' => 0,
        'text' => 'Arrested in 1923 for a murder…',
        'voice' => null,
    ]);

    expect($moved->startsAt())->toEqual(31.0)
        ->and($stays->startsAt())->toEqual(0.0);

    Livewire::test(Workshop::class)->call('reorder', $third->id, $first->id);

    expect($moved->fresh()->shot_id)->toBe($third->id)
        ->and($stays->fresh()->shot_id)->toBe($first->id)
        ->and($third->fresh()->order)->toBe(1)
        ->and($first->fresh()->order)->toBe(2)
        ->and($second->fresh()->order)->toBe(3)
        ->and($moved->fresh()->startsAt())->toEqual(1.0)
        ->and($stays->fresh()->startsAt())->toEqual(30.0);
});
