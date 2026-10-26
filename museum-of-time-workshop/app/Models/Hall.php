<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;

class Hall extends Model
{
    protected $fillable = ['wing_id', 'name', 'slug'];

    public function wing(): BelongsTo
    {
        return $this->belongsTo(Wing::class);
    }

    public function exhibits(): HasMany
    {
        return $this->hasMany(Exhibit::class);
    }
}
