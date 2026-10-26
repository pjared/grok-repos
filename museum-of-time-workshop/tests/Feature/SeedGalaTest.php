<?php

use App\Enums\CueType;
use App\Enums\TruthTag;
use App\Models\Character;
use App\Models\Shot;
use Illuminate\Support\Facades\Storage;

it('slices the storyboard into six ordered shots', function () {
    Storage::fake('public');

    $this->artisan('workshop:seed-gala')->assertSuccessful();

    $shots = Shot::query()->orderBy('order')->get();

    expect($shots)->toHaveCount(6)
        ->and($shots->pluck('title')->all())->toBe([
            'Gala',
            'Empty setting',
            'The pearl',
            'The glance',
            'Doors slam',
            'Still toasting',
        ])
        ->and(round((float) $shots->sum('duration_s'), 3))->toBe(200.0)
        ->and($shots[4]->truth_tag)->toBe(TruthTag::Invented)
        ->and($shots[4]->prompt)->toBe('Tung strikes table with bat…')
        ->and($shots[4]->versions)->toHaveCount(3)
        ->and($shots[5]->cues->firstWhere('type', CueType::Plaque)->text)->toBe('Arrested in 1923 for a murder…');

    $tung = Character::query()->where('name', 'Tung')->first();
    expect($tung->locked)->toBeTrue()
        ->and($shots[0]->characters()->where('name', 'Tung')->first()->pivot->reference_image)->toBe($tung->reference_image)
        ->and($tung->reference_image)->toBe($shots[5]->frame_path);

    foreach ($shots as $shot) {
        expect(Storage::disk('public')->exists($shot->frame_path))->toBeTrue();
        [$width, $height] = getimagesize(Storage::disk('public')->path($shot->frame_path));
        expect($width)->toBeGreaterThan(200)
            ->and($height)->toBeGreaterThan(150);
    }

    expect($shots[0]->sequence->exhibit->name)->toBe('Gala Arrest')
        ->and($shots[0]->sequence->exhibit->wing()->name)->toBe('Unit 14');
});
