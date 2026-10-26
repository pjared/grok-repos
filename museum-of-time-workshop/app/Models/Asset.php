<?php

namespace App\Models;

use App\Enums\TruthTag;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

class Asset extends Model
{
    protected $fillable = ['exhibit_id', 'name', 'path', 'kind', 'truth_tag'];

    protected function casts(): array
    {
        return [
            'truth_tag' => TruthTag::class,
        ];
    }

    public function exhibit(): BelongsTo
    {
        return $this->belongsTo(Exhibit::class);
    }
}
