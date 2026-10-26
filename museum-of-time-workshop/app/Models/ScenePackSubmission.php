<?php

namespace App\Models;

use App\Enums\ScenePackStatus;
use Illuminate\Database\Eloquent\Model;

class ScenePackSubmission extends Model
{
    protected $fillable = [
        'fingerprint',
        'filename',
        'stored_path',
        'status',
        'error',
        'summary',
    ];

    protected function casts(): array
    {
        return [
            'status' => ScenePackStatus::class,
            'summary' => 'array',
        ];
    }
}
