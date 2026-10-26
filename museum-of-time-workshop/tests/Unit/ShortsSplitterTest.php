<?php

use App\Video\ShortsSplitter;

it('packs whole shots into the 45 to 60 second window', function () {
    $groups = (new ShortsSplitter(45, 60))->split([
        ['id' => 1, 'duration' => 52],
        ['id' => 2, 'duration' => 28],
        ['id' => 3, 'duration' => 24],
        ['id' => 4, 'duration' => 26],
        ['id' => 5, 'duration' => 22],
        ['id' => 6, 'duration' => 48],
    ]);

    expect($groups)->toHaveCount(4)
        ->and(array_map(fn ($group) => array_column($group['shots'], 'id'), $groups))->toBe([
            [1],
            [2, 3],
            [4, 5],
            [6],
        ])
        ->and(array_column($groups, 'duration'))->toBe([52.0, 52.0, 48.0, 48.0])
        ->and(array_filter(array_column($groups, 'warning')))->toBe([]);
});

it('never splits a shot across shorts', function () {
    $groups = (new ShortsSplitter(45, 60))->split([
        ['id' => 'a', 'duration' => 70],
        ['id' => 'b', 'duration' => 10],
        ['id' => 'c', 'duration' => 10],
        ['id' => 'd', 'duration' => 50],
    ]);

    $membership = [];
    foreach ($groups as $group) {
        foreach ($group['shots'] as $shot) {
            $membership[$shot['id']][] = $shot['id'];
        }
    }

    expect($membership)->toHaveCount(4);
    foreach ($membership as $durations) {
        expect($durations)->toHaveCount(1);
    }

    expect($groups[0]['shots'][0]['id'])->toBe('a')
        ->and($groups[0]['warning'])->not->toBeNull()
        ->and($groups[1]['duration'])->toBe(20.0)
        ->and($groups[1]['warning'])->not->toBeNull()
        ->and($groups[2]['shots'][0]['id'])->toBe('d');
});

it('returns no shorts for an empty timeline', function () {
    expect((new ShortsSplitter(45, 60))->split([]))->toBe([]);
});
