<?php

use App\Enums\CueType;
use App\Enums\TruthTag;
use App\Models\Asset;
use App\Models\Character;
use App\Models\ShotVersion;
use App\Models\TextCue;
use Illuminate\Support\Facades\Storage;

it('relates wings, halls, exhibits, sequences, shots, assets, and characters', function () {
    Storage::fake('public');
    ['wing' => $wing, 'hall' => $hall, 'exhibit' => $exhibit, 'sequence' => $sequence] = museum();

    $shot = makeShot($sequence, 1, 4, 'Doors slam');
    $shot->update(['truth_tag' => TruthTag::Invented]);

    $version = ShotVersion::query()->create([
        'shot_id' => $shot->id,
        'prompt' => 'Earlier prompt',
        'model' => 'FLUX',
        'duration_s' => 4,
        'truth_tag' => TruthTag::Invented,
        'frame_path' => $shot->frame_path,
    ]);

    $cue = TextCue::query()->create([
        'shot_id' => $shot->id,
        'type' => CueType::Narration,
        'offset_s' => 1.5,
        'text' => 'The doors slammed.',
        'voice' => 'MoT Docent 3',
    ]);

    $character = Character::query()->create([
        'name' => 'Tung',
        'locked' => true,
        'reference_image' => 'gala/frames/06.jpg',
    ]);
    $shot->pin($character);

    $asset = Asset::query()->create([
        'exhibit_id' => $exhibit->id,
        'name' => 'Storyboard',
        'path' => 'gala/storyboard.jpg',
        'kind' => 'storyboard',
        'truth_tag' => TruthTag::Documented,
    ]);

    expect($wing->halls)->toHaveCount(1)
        ->and($wing->exhibits->first()->is($exhibit))->toBeTrue()
        ->and($hall->exhibits->first()->is($exhibit))->toBeTrue()
        ->and($exhibit->hall->is($hall))->toBeTrue()
        ->and($exhibit->wing()->is($wing))->toBeTrue()
        ->and($exhibit->sequences->first()->is($sequence))->toBeTrue()
        ->and($sequence->exhibit->is($exhibit))->toBeTrue()
        ->and($shot->sequence->is($sequence))->toBeTrue()
        ->and($shot->versions->first()->is($version))->toBeTrue()
        ->and($shot->cues->first()->is($cue))->toBeTrue()
        ->and($cue->type)->toBe(CueType::Narration)
        ->and($shot->truth_tag)->toBe(TruthTag::Invented)
        ->and($asset->truth_tag)->toBe(TruthTag::Documented)
        ->and($asset->exhibit->is($exhibit))->toBeTrue()
        ->and($character->locked)->toBeTrue()
        ->and($shot->characters->first()->pivot->reference_image)->toBe('gala/frames/06.jpg')
        ->and($character->shots->first()->is($shot))->toBeTrue();
});
