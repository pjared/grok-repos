<?php

namespace App\Sections;

use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.workshop')]
abstract class PlaceholderPage extends Component
{
    public string $search = '';

    abstract protected function title(): string;

    /**
     * @return list<string>
     */
    abstract protected function items(): array;

    public function render()
    {
        $needle = mb_strtolower(trim($this->search));
        $items = array_values(array_filter(
            $this->items(),
            fn (string $item) => $needle === '' || str_contains(mb_strtolower($item), $needle),
        ));

        return view('sections.placeholder', [
            'title' => $this->title(),
            'items' => $items,
        ]);
    }
}
