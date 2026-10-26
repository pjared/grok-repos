<?php

use App\Sections\Assets\Livewire\Index as AssetsIndex;
use App\Sections\Editor\Livewire\Workshop;
use App\Sections\Exhibits\Livewire\Index as ExhibitsIndex;
use App\Sections\Wings\Livewire\Index as WingsIndex;

return [
    [
        'key' => 'editor',
        'label' => 'Editor',
        'module' => 'Editor',
        'route' => 'editor.index',
        'icon' => 'editor',
        'placeholder' => false,
        'component' => Workshop::class,
    ],
    [
        'key' => 'exhibits',
        'label' => 'Exhibits',
        'module' => 'Exhibits',
        'route' => 'exhibits.index',
        'icon' => 'exhibits',
        'placeholder' => true,
        'component' => ExhibitsIndex::class,
    ],
    [
        'key' => 'wings',
        'label' => 'Wings & Halls',
        'module' => 'Wings',
        'route' => 'wings.index',
        'icon' => 'wings',
        'placeholder' => true,
        'component' => WingsIndex::class,
    ],
    [
        'key' => 'assets',
        'label' => 'Assets',
        'module' => 'Assets',
        'route' => 'assets.index',
        'icon' => 'assets',
        'placeholder' => false,
        'component' => AssetsIndex::class,
    ],
];
