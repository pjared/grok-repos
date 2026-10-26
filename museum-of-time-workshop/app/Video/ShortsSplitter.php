<?php

namespace App\Video;

class ShortsSplitter
{
    public function __construct(
        public ?float $minSeconds = null,
        public ?float $maxSeconds = null,
    ) {
        $this->minSeconds ??= (float) config('video.short.min_seconds', HouseStandard::SHORT_MIN);
        $this->maxSeconds ??= (float) config('video.short.max_seconds', HouseStandard::SHORT_MAX);
    }

    /**
     * Pack whole shots into 45–60s shorts. A shot is never divided.
     *
     * @param  list<array{id: int|string, duration: float}>  $shots
     * @return list<array{shots: list<array{id: int|string, duration: float}>, duration: float, warning: ?string}>
     */
    public function split(array $shots): array
    {
        $groups = [];
        $current = [];
        $duration = 0.0;

        $close = function () use (&$groups, &$current, &$duration): void {
            if ($current === []) {
                return;
            }

            $warning = null;
            if ($duration < $this->minSeconds - 0.001 || $duration > $this->maxSeconds + 0.001) {
                $warning = sprintf(
                    'Short is %.0fs, outside the 45–60 second house standard.',
                    $duration,
                );
            }

            $groups[] = [
                'shots' => $current,
                'duration' => $duration,
                'warning' => $warning,
            ];

            $current = [];
            $duration = 0.0;
        };

        foreach ($shots as $shot) {
            $shotDuration = (float) $shot['duration'];

            if ($current !== [] && ($duration + $shotDuration) > $this->maxSeconds + 0.001) {
                $close();
            }

            $current[] = $shot;
            $duration += $shotDuration;

            if ($duration > $this->maxSeconds + 0.001) {
                $close();
            }
        }

        $close();

        return $groups;
    }
}
