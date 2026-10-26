<?php

namespace App\Models;

use App\Enums\TruthTag;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class ShotVersion extends Model
{
    protected $fillable = [
        'shot_id',
        'frame_path',
        'prompt',
        'model',
        'duration_s',
        'truth_tag',
        'clip_path',
    ];

    protected function casts(): array
    {
        return [
            'duration_s' => 'float',
            'truth_tag' => TruthTag::class,
        ];
    }

    public function shot(): BelongsTo
    {
        return $this->belongsTo(Shot::class);
    }
}
