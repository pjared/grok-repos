<?php

namespace App\Sections\Exhibits\Livewire;

use App\Models\Exhibit;
use App\Sections\PlaceholderPage;
use Livewire\Attributes\Layout;

#[Layout('layouts.workshop')]
class Index extends PlaceholderPage
{
    protected function title(): string
    {
        return 'Exhibits';
    }

    protected function items(): array
    {
        return Exhibit::query()
            ->with('hall.wing')
            ->orderBy('name')
            ->get()
            ->map(fn (Exhibit $exhibit) => $exhibit->wing()?->name.' / '.$exhibit->hall->name.' / '.$exhibit->name.' · '.$exhibit->truth_tag->value)
            ->all();
    }
}
