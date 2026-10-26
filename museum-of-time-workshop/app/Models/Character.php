<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Support\Facades\Storage;

class Character extends Model
{
    protected $fillable = ['name', 'locked', 'reference_image'];

    protected function casts(): array
    {
        return [
            'locked' => 'boolean',
        ];
    }

    public function shots(): BelongsToMany
    {
        return $this->belongsToMany(Shot::class, 'shot_character')->withPivot('reference_image');
    }

    public function referenceUrl(): ?string
    {
        if (! $this->reference_image) {
            return null;
        }

        return Storage::disk('public')->url($this->reference_image);
    }
}
