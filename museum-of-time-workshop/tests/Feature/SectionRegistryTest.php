<?php

use App\Sections\SectionRegistry;
use Illuminate\Support\Facades\Storage;
use Livewire\Mechanisms\ComponentRegistry;

it('registers the admin sections and their routes', function () {
    $registry = app(SectionRegistry::class);

    expect($registry->keys())->toBe(['editor', 'exhibits', 'wings', 'assets'])
        ->and($registry->get('editor')['placeholder'])->toBeFalse()
        ->and($registry->get('wings')['label'])->toBe('Wings & Halls')
        ->and($registry->get('assets')['placeholder'])->toBeFalse()
        ->and($registry->placeholders())->toHaveCount(2);

    foreach ($registry->all() as $section) {
        expect(is_file($registry->routesPath($section)))->toBeTrue()
            ->and(class_exists($section['component']))->toBeTrue()
            ->and(is_dir(app_path('Sections/'.$section['module'].'/Livewire')))->toBeTrue();

        $this->get(route($section['route']))
            ->assertOk()
            ->assertSee($section['label']);
    }
});

it('resolves each section component after a livewire round trip', function () {
    $registry = app(ComponentRegistry::class);

    foreach (app(SectionRegistry::class)->all() as $section) {
        $name = $registry->getName($section['component']);

        expect(ltrim($registry->getClass($name), '\\'))->toBe($section['component']);
    }

    Storage::fake('public');
    ['sequence' => $sequence] = museum();
    makeShot($sequence, 1, 10, 'Gala');

    $page = $this->get(route('editor.index'));
    $page->assertOk();

    preg_match('/wire:snapshot="([^"]+)"/', $page->getContent(), $snapshot);
    preg_match('/data-csrf="([^"]+)"/', $page->getContent(), $csrf);

    $this->withHeader('X-Livewire', 'true')
        ->postJson('/livewire/update', [
            'components' => [[
                'snapshot' => html_entity_decode($snapshot[1], ENT_QUOTES),
                'updates' => [],
                'calls' => [[
                    'path' => '',
                    'method' => 'setAspect',
                    'params' => ['9:16'],
                ]],
            ]],
        ], [
            'X-CSRF-TOKEN' => $csrf[1],
        ])
        ->assertOk()
        ->assertSee('9:16', false);
});

it('shows placeholder copy for the sections that are not the editor', function () {
    $this->get(route('exhibits.index'))->assertOk()->assertSee('Placeholder');
    $this->get(route('wings.index'))->assertOk()->assertSee('Wings & Halls');
    $this->get(route('assets.index'))->assertOk()->assertSee('grouped by exhibit')->assertDontSee('This section is on the admin rail');
});
