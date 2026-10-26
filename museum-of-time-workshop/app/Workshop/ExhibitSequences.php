<?php

namespace App\Workshop;

use App\Enums\TruthTag;
use App\Models\Exhibit;
use App\Models\Hall;
use App\Models\Sequence;
use App\Models\Wing;
use Illuminate\Support\Str;

class ExhibitSequences
{
    public static function find(string $exhibit): Sequence
    {
        $exhibit = trim($exhibit);

        if ($exhibit === '') {
            throw new \InvalidArgumentException('Pass an exhibit slug or id.');
        }

        $model = ctype_digit($exhibit)
            ? Exhibit::query()->find($exhibit)
            : Exhibit::query()->where('slug', $exhibit)->orWhere('name', $exhibit)->first();

        if (! $model) {
            throw new \InvalidArgumentException("Exhibit \"{$exhibit}\" was not found.");
        }

        $sequence = $model->sequences()->latest('id')->first();

        if (! $sequence) {
            throw new \InvalidArgumentException("Exhibit \"{$model->name}\" has no sequence.");
        }

        return $sequence;
    }

    public static function provision(string $slug, string $title, string $wingName, string $hallName, string $truth): Sequence
    {
        $existing = Exhibit::query()->where('slug', $slug)->first();

        if ($existing) {
            return $existing->sequences()->latest('id')->first()
                ?? $existing->sequences()->create(['title' => $title]);
        }

        $wing = Wing::query()->firstOrCreate(
            ['slug' => Str::slug($wingName)],
            ['name' => $wingName],
        );
        $hall = Hall::query()->firstOrCreate(
            ['wing_id' => $wing->id, 'slug' => Str::slug($hallName)],
            ['name' => $hallName],
        );
        $exhibit = Exhibit::query()->create([
            'hall_id' => $hall->id,
            'name' => $title,
            'slug' => $slug,
            'truth_tag' => TruthTag::tryFrom($truth) ?? TruthTag::Legend,
        ]);

        return $exhibit->sequences()->create(['title' => $title]);
    }
}
