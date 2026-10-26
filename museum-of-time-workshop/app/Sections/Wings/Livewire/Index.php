<?php

namespace App\Sections\Wings\Livewire;

use App\Models\Wing;
use App\Sections\PlaceholderPage;
use Livewire\Attributes\Layout;

#[Layout('layouts.workshop')]
class Index extends PlaceholderPage
{
    protected function title(): string
    {
        return 'Wings & Halls';
    }

    protected function items(): array
    {
        $items = [];

        foreach (Wing::query()->with('halls')->orderBy('name')->get() as $wing) {
            $items[] = $wing->name;
            foreach ($wing->halls as $hall) {
                $items[] = $wing->name.' / '.$hall->name;
            }
        }

        return $items;
    }
}
