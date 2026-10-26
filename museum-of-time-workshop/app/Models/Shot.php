<?php

namespace App\Models;

use App\Enums\ShotStatus;
use App\Enums\TruthTag;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Facades\Storage;

class Shot extends Model
{
    protected $fillable = [
        'sequence_id',
        'order',
        'title',
        'frame_path',
        'prompt',
        'model',
        'duration_s',
        'truth_tag',
        'clip_path',
        'status',
    ];

    protected function casts(): array
    {
        return [
            'order' => 'integer',
            'duration_s' => 'float',
            'truth_tag' => TruthTag::class,
            'status' => ShotStatus::class,
        ];
    }

    public function sequence(): BelongsTo
    {
        return $this->belongsTo(Sequence::class);
    }

    public function versions(): HasMany
    {
        return $this->hasMany(ShotVersion::class)->latest();
    }

    public function cues(): HasMany
    {
        return $this->hasMany(TextCue::class)->orderBy('offset_s');
    }

    public function characters(): BelongsToMany
    {
        return $this->belongsToMany(Character::class, 'shot_character')->withPivot('reference_image');
    }

    public function pin(Character $character): void
    {
        $this->characters()->syncWithoutDetaching([
            $character->id => [
                'reference_image' => $character->locked ? $character->reference_image : null,
            ],
        ]);
    }

    public function unpin(Character $character): void
    {
        $this->characters()->detach($character->id);
    }

    public function hasFrame(): bool
    {
        if (! $this->frame_path) {
            return false;
        }

        return is_file(Storage::disk('public')->path($this->frame_path));
    }

    public function frameUrl(): ?string
    {
        return $this->frame_path ? Storage::disk('public')->url($this->frame_path) : null;
    }

    public function clipUrl(): ?string
    {
        return $this->clip_path ? Storage::disk('public')->url($this->clip_path) : null;
    }

    public function snapshotVersion(): ShotVersion
    {
        return $this->versions()->create([
            'frame_path' => $this->frame_path,
            'prompt' => $this->prompt,
            'model' => $this->model,
            'duration_s' => $this->duration_s,
            'truth_tag' => $this->truth_tag,
            'clip_path' => $this->clip_path,
        ]);
    }
}
