<?php

namespace App\Workshop;

use App\Models\Exhibit;
use App\Models\Sequence;

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
}
