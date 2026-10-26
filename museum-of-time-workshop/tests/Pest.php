<?php

use App\Enums\TruthTag;
use App\Models\Exhibit;
use App\Models\Hall;
use App\Models\Sequence;
use App\Models\Shot;
use App\Models\Wing;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Symfony\Component\Process\Process;
use Tests\TestCase;

pest()->extend(TestCase::class)
    ->use(RefreshDatabase::class)
    ->in('Feature');

pest()->extend(TestCase::class)
    ->in('Unit');

function museum(): array
{
    $wing = Wing::query()->create(['name' => 'Unit 14', 'slug' => 'unit-14']);
    $hall = Hall::query()->create(['wing_id' => $wing->id, 'name' => 'Main Hall', 'slug' => 'main-hall']);
    $exhibit = Exhibit::query()->create([
        'hall_id' => $hall->id,
        'name' => 'Gala Arrest',
        'slug' => 'gala-arrest',
        'truth_tag' => TruthTag::Documented,
    ]);
    $sequence = Sequence::query()->create([
        'exhibit_id' => $exhibit->id,
        'title' => 'Gala Arrest',
    ]);

    return compact('wing', 'hall', 'exhibit', 'sequence');
}

function tinyJpeg(string $relative = 'frames/tiny.jpg'): string
{
    $image = imagecreatetruecolor(320, 180);
    $color = imagecolorallocate($image, 48, 32, 64);
    imagefill($image, 0, 0, $color);
    $absolute = Storage::disk('public')->path($relative);
    File::ensureDirectoryExists(dirname($absolute));
    imagejpeg($image, $absolute, 85);
    imagedestroy($image);

    return $relative;
}

function makeShot(Sequence $sequence, int $order, float $duration, string $title = 'Shot'): Shot
{
    return Shot::query()->create([
        'sequence_id' => $sequence->id,
        'order' => $order,
        'title' => $title,
        'frame_path' => tinyJpeg('frames/shot-'.$order.'.jpg'),
        'prompt' => $title,
        'model' => 'FLUX',
        'duration_s' => $duration,
        'truth_tag' => TruthTag::Documented,
    ]);
}

function ffprobe(string $path): array
{
    $process = new Process([
        (string) config('video.ffprobe', 'ffprobe'),
        '-v', 'error',
        '-show_streams',
        '-show_format',
        '-of', 'json',
        $path,
    ]);
    $process->mustRun();

    return json_decode($process->getOutput(), true, 512, JSON_THROW_ON_ERROR);
}
