<?php

use Illuminate\Support\Facades\Storage;

it('renders the editor shell for the seeded sequence', function () {
    Storage::fake('public');
    $this->artisan('workshop:seed-gala');

    $this->get(route('editor.index'))
        ->assertOk()
        ->assertSee('Workshop')
        ->assertSee('Unit 14')
        ->assertSee('Gala Arrest')
        ->assertSee('Doors slam')
        ->assertSee('Tung')
        ->assertSee('Regenerate shot')
        ->assertSee('Narration')
        ->assertSee('Plaque')
        ->assertSee('documented')
        ->assertSee('MoT Docent 3');

    $html = $this->get(route('editor.index'))->getContent();
    $export = strpos($html, "\$dispatch('mot-export')");
    $root = strpos($html, 'wire:id');

    expect($export)->toBeInt()->toBeGreaterThan(0)
        ->and($root)->toBeInt()->toBeGreaterThan($export)
        ->and($html)->toContain('mot-export.window')
        ->and($html)->not->toContain('wire:click="$toggle(\'showExport\')"');
});
