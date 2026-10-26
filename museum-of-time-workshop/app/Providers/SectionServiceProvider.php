<?php

namespace App\Providers;

use App\Sections\SectionRegistry;
use Illuminate\Support\Facades\Route;
use Illuminate\Support\ServiceProvider;

class SectionServiceProvider extends ServiceProvider
{
    public function register(): void
    {
        // Section Livewire classes live under App\Sections, not App\Livewire.
        // The default namespace would name them in a way that cannot resolve
        // back to the class, so every subsequent request 419s.
        config(['livewire.class_namespace' => 'App']);
    }

    public function boot(SectionRegistry $sections): void
    {
        foreach ($sections->all() as $section) {
            $routes = $sections->routesPath($section);

            if (! is_file($routes)) {
                throw new \RuntimeException("Section [{$section['key']}] is missing {$routes}.");
            }

            Route::middleware('web')->group($routes);
        }
    }
}
