<?php

namespace App\Workshop;

use App\Enums\CueType;
use App\Enums\ShotStatus;
use App\Enums\TruthTag;
use App\Models\Sequence;
use App\Models\Shot;
use App\Models\TextCue;
use Illuminate\Support\Facades\DB;

class AddScene
{
    public const DEFAULT_MODEL = 'FLUX';

    public const DEFAULT_DURATION = 4.0;

    public function append(Sequence $sequence, array $attributes = []): Shot
    {
        return $this->create($sequence, null, $attributes);
    }

    public function insertAfter(Sequence $sequence, Shot $after, array $attributes = []): Shot
    {
        if ($after->sequence_id !== $sequence->id) {
            throw new \InvalidArgumentException('That shot is not on this sequence.');
        }

        return $this->create($sequence, $after, $attributes);
    }

    /**
     * @param  array<string, mixed>  $attributes
     */
    private function create(Sequence $sequence, ?Shot $after, array $attributes): Shot
    {
        return DB::transaction(function () use ($sequence, $after, $attributes) {
            $position = $after
                ? ((int) $after->order + 1)
                : ((int) $sequence->shots()->max('order') + 1);

            Shot::query()
                ->where('sequence_id', $sequence->id)
                ->where('order', '>=', $position)
                ->increment('order');

            $shot = Shot::query()->create([
                'sequence_id' => $sequence->id,
                'order' => $position,
                'title' => $this->title($attributes['title'] ?? null),
                'frame_path' => $attributes['frame_path'] ?? null,
                'prompt' => (string) ($attributes['prompt'] ?? ''),
                'model' => (string) ($attributes['model'] ?? self::DEFAULT_MODEL),
                'duration_s' => $this->duration($attributes['duration'] ?? $attributes['duration_s'] ?? self::DEFAULT_DURATION),
                'truth_tag' => $this->tag($attributes['truth'] ?? $attributes['truth_tag'] ?? TruthTag::Invented),
                'clip_path' => $attributes['clip_path'] ?? null,
                'status' => filled($attributes['clip_path'] ?? null) ? ShotStatus::Ready : ShotStatus::Draft,
            ]);

            $this->cue($shot, CueType::Narration, $attributes['narration'] ?? null, $attributes['voice'] ?? null, $attributes['narration_audio'] ?? null);
            $this->cue($shot, CueType::Plaque, $attributes['plaque'] ?? null, null);

            $this->renumber($sequence);

            return $shot->fresh(['cues']);
        });
    }

    public function renumber(Sequence $sequence): void
    {
        $shots = Shot::query()
            ->where('sequence_id', $sequence->id)
            ->orderBy('order')
            ->orderBy('id')
            ->get();

        foreach ($shots->values() as $index => $shot) {
            $order = $index + 1;

            if ((int) $shot->order !== $order) {
                $shot->update(['order' => $order]);
            }
        }
    }

    private function title(mixed $title): string
    {
        $title = trim((string) ($title ?? ''));

        if ($title === '') {
            $title = 'New scene';
        }

        return mb_substr($title, 0, 120);
    }

    private function duration(mixed $value): float
    {
        if (! is_numeric($value)) {
            throw new \InvalidArgumentException('Duration must be a number of seconds.');
        }

        $duration = (float) $value;

        if ($duration < 0.2) {
            throw new \InvalidArgumentException('Duration must be at least 0.2 seconds.');
        }

        return $duration;
    }

    private function tag(TruthTag|string $value): TruthTag
    {
        if ($value instanceof TruthTag) {
            return $value;
        }

        $tag = TruthTag::tryFrom($value);

        if (! $tag) {
            throw new \InvalidArgumentException('Truth tag must be documented, legend, or invented.');
        }

        return $tag;
    }

    private function cue(Shot $shot, CueType $type, mixed $text, mixed $voice, mixed $audio = null): void
    {
        $text = trim((string) ($text ?? ''));
        $audio = is_string($audio) && $audio !== '' ? $audio : null;

        if ($text === '' && $audio === null) {
            return;
        }

        TextCue::query()->create([
            'shot_id' => $shot->id,
            'type' => $type,
            'offset_s' => 0,
            'text' => $text !== '' ? $text : 'Narration',
            'voice' => $type === CueType::Narration ? ($voice !== null && $voice !== '' ? (string) $voice : null) : null,
            'audio_path' => $type === CueType::Narration ? $audio : null,
        ]);
    }
}
