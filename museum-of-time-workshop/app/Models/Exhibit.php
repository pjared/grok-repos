<?php

namespace App\Models;

use App\Enums\TruthTag;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Exhibit extends Model
{
    protected $fillable = ['hall_id', 'name', 'slug', 'truth_tag'];

    protected function casts(): array
    {
        return [
            'truth_tag' => TruthTag::class,
        ];
    }

    public function hall(): BelongsTo
    {
        return $this->belongsTo(Hall::class);
    }

    public function sequences(): HasMany
    {
        return $this->hasMany(Sequence::class);
    }

    public function assets(): HasMany
    {
        return $this->hasMany(Asset::class);
    }

    public function wing(): ?Wing
    {
        return $this->hall?->wing;
    }
}
