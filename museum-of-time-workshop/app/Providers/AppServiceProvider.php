<?php

namespace App\Providers;

use App\Video\VideoProvider;
use App\Video\VideoProviderManager;
use Illuminate\Support\ServiceProvider;

class AppServiceProvider extends ServiceProvider
{
    /**
     * Register any application services.
     */
    public function register(): void
    {
        $this->app->bind(VideoProvider::class, function ($app) {
            return $app->make(VideoProviderManager::class)->driver();
        });
    }

    /**
     * Bootstrap any application services.
     */
    public function boot(): void
    {
        // The media library links on first use. A link failure must not stop boot.
    }
}
