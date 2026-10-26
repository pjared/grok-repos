<?php

namespace App\Console\Commands;

use App\Workshop\SeedGala;
use Illuminate\Console\Command;

class SeedGalaCommand extends Command
{
    protected $signature = 'workshop:seed-gala';

    protected $description = 'Seed the Gala Arrest sequence from the storyboard fixture';

    public function handle(SeedGala $seed): int
    {
        $sequence = $seed->run();
        $count = $sequence->shots()->count();

        $this->info("Seeded {$sequence->title} ({$count} shots).");

        return self::SUCCESS;
    }
}
