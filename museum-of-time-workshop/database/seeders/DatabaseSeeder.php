<?php

namespace Database\Seeders;

use App\Workshop\SeedGala;
use Illuminate\Database\Seeder;

class DatabaseSeeder extends Seeder
{
    public function run(): void
    {
        app(SeedGala::class)->run();
    }
}
