<?php

use App\Video\Drawtext;
use App\Video\HouseStandard;
use App\Video\Stamp;

it('formats the house stamp', function () {
    expect(Stamp::text('Unit 14', 'Gala Arrest', 2, 4))
        ->toBe('Museum of Time · Unit 14 · Gala Arrest · Short 2 of 4');
});

it('puts that stamp on the burn-in filter', function () {
    $stamp = Stamp::text('Unit 14', 'Gala Arrest', 1, 4);

    expect(Drawtext::filter($stamp))->toContain($stamp);
});

it('warns when an episode is outside three to four minutes', function () {
    expect(HouseStandard::episodeWarning(200))->toBeNull()
        ->and(HouseStandard::episodeWarning(100))->toBe('Episode is 1:40, outside the 3–4 minute house standard.')
        ->and(HouseStandard::episodeWarning(250))->toBe('Episode is 4:10, outside the 3–4 minute house standard.');
});
