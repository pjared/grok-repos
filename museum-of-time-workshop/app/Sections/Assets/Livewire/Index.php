<?php

namespace App\Sections\Assets\Livewire;

use App\Models\Asset;
use App\Sections\PlaceholderPage;
use Livewire\Attributes\Layout;

#[Layout('layouts.workshop')]
class Index extends PlaceholderPage
{
    protected function title(): string
    {
        return 'Assets';
    }

    protected function items(): array
    {
        return Asset::query()
            ->orderBy('name')
            ->get()
            ->map(fn (Asset $asset) => $asset->name.' · '.$asset->truth_tag->value)
            ->all();
    }
}
