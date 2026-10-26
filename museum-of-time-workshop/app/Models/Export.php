<?php

namespace App\Models;

use App\Enums\ExportKind;
use App\Enums\ExportStatus;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Facades\Storage;

class Export extends Model
{
    protected $fillable = [
        'sequence_id',
        'kind',
        'status',
        'path',
        'warnings',
        'meta',
        'error',
    ];

    protected function casts(): array
    {
        return [
            'kind' => ExportKind::class,
            'status' => ExportStatus::class,
            'warnings' => 'array',
            'meta' => 'array',
        ];
    }

    public function sequence(): BelongsTo
    {
        return $this->belongsTo(Sequence::class);
    }

    public function url(): ?string
    {
        return $this->path ? Storage::disk('public')->url($this->path) : null;
    }
}
