<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Sequence extends Model
{
    protected $fillable = ['exhibit_id', 'title'];

    public function exhibit(): BelongsTo
    {
        return $this->belongsTo(Exhibit::class);
    }

    public function shots(): HasMany
    {
        return $this->hasMany(Shot::class)->orderBy('order');
    }

    public function exports(): HasMany
    {
        return $this->hasMany(Export::class)->latest();
    }

    public function durationSeconds(): float
    {
        return (float) $this->shots()->sum('duration_s');
    }
}
