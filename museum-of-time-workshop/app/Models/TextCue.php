<?php

namespace App\Models;

use App\Enums\CueType;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class TextCue extends Model
{
    protected $fillable = ['shot_id', 'type', 'offset_s', 'text', 'voice'];

    protected function casts(): array
    {
        return [
            'type' => CueType::class,
            'offset_s' => 'float',
        ];
    }

    public function shot(): BelongsTo
    {
        return $this->belongsTo(Shot::class);
    }

    /**
     * Absolute timeline time. The cue stores only an offset on its shot,
     * so reordering shots moves the cue with that shot.
     */
    public function startsAt(): float
    {
        $shot = $this->shot;

        $before = Shot::query()
            ->where('sequence_id', $shot->sequence_id)
            ->where('order', '<', $shot->order)
            ->sum('duration_s');

        return (float) $before + (float) $this->offset_s;
    }
}
