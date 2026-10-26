<?php

namespace App\Models;

use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasManyThrough;

class Wing extends Model
{
    protected $fillable = ['name', 'slug'];

    public function halls(): HasMany
    {
        return $this->hasMany(Hall::class);
    }

    public function exhibits(): HasManyThrough
    {
        return $this->hasManyThrough(Exhibit::class, Hall::class);
    }
}
