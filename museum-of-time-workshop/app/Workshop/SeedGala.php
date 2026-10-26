<?php

namespace App\Workshop;

use App\Enums\CueType;
use App\Enums\ShotStatus;
use App\Enums\TruthTag;
use App\Models\Asset;
use App\Models\Character;
use App\Models\Exhibit;
use App\Models\Hall;
use App\Models\Sequence;
use App\Models\Shot;
use App\Models\TextCue;
use App\Models\Wing;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

class SeedGala
{
    public function __construct(private readonly StoryboardSlicer $slicer) {}

    public function run(): Sequence
    {
        $source = base_path('fixtures/gala_arrest_storyboard.jpg');
        if (! is_file($source)) {
            throw new \RuntimeException('Missing fixture fixtures/gala_arrest_storyboard.jpg.');
        }

        $wing = Wing::query()->updateOrCreate(
            ['slug' => 'unit-14'],
            ['name' => 'Unit 14'],
        );
        $hall = Hall::query()->updateOrCreate(
            ['wing_id' => $wing->id, 'slug' => 'main-hall'],
            ['name' => 'Main Hall'],
        );
        $exhibit = Exhibit::query()->updateOrCreate(
            ['hall_id' => $hall->id, 'slug' => 'gala-arrest'],
            ['name' => 'Gala Arrest', 'truth_tag' => TruthTag::Documented],
        );

        $sequence = Sequence::query()->updateOrCreate(
            ['exhibit_id' => $exhibit->id, 'title' => 'Gala Arrest'],
        );

        Shot::query()->where('sequence_id', $sequence->id)->delete();
        Asset::query()->where('exhibit_id', $exhibit->id)->delete();

        $sheet = 'gala/storyboard.jpg';
        Storage::disk('public')->put($sheet, File::get($source));
        Asset::query()->create([
            'exhibit_id' => $exhibit->id,
            'name' => 'Gala arrest storyboard',
            'path' => $sheet,
            'kind' => 'storyboard',
            'truth_tag' => TruthTag::Documented,
        ]);

        $panels = $this->slicer->slice($source);
        $shots = [];

        foreach ($this->definitions() as $index => $definition) {
            $relative = sprintf('gala/frames/%02d-%s.jpg', $index + 1, Str::slug($definition['title']));
            Storage::disk('public')->put($relative, File::get($panels[$index]));

            $shot = Shot::query()->create([
                'sequence_id' => $sequence->id,
                'order' => $index + 1,
                'title' => $definition['title'],
                'frame_path' => $relative,
                'prompt' => $definition['prompt'],
                'model' => 'FLUX',
                'duration_s' => $definition['duration'],
                'truth_tag' => $definition['tag'],
                'status' => ShotStatus::Draft,
            ]);

            TextCue::query()->create([
                'shot_id' => $shot->id,
                'type' => CueType::Narration,
                'offset_s' => 0,
                'text' => $definition['narration'],
                'voice' => 'MoT Docent 3',
            ]);

            if (isset($definition['plaque'])) {
                TextCue::query()->create([
                    'shot_id' => $shot->id,
                    'type' => CueType::Plaque,
                    'offset_s' => 0,
                    'text' => $definition['plaque'],
                    'voice' => null,
                ]);
            }

            Asset::query()->create([
                'exhibit_id' => $exhibit->id,
                'name' => 'Panel '.($index + 1).' · '.$definition['title'],
                'path' => $relative,
                'kind' => 'frame',
                'truth_tag' => $definition['tag'],
            ]);

            $shots[$definition['key']] = $shot;
        }

        $tung = Character::query()->updateOrCreate(
            ['name' => 'Tung'],
            ['locked' => true, 'reference_image' => $shots['toast']->frame_path],
        );
        $man = Character::query()->updateOrCreate(
            ['name' => 'White-tux man'],
            ['locked' => false, 'reference_image' => null],
        );
        $wife = Character::query()->updateOrCreate(
            ['name' => "Tycoon's wife"],
            ['locked' => false, 'reference_image' => null],
        );

        foreach ($shots as $shot) {
            $shot->pin($tung);
        }

        foreach (['gala', 'glance', 'doors'] as $key) {
            $shots[$key]->pin($man);
        }

        foreach (['gala', 'pearl', 'glance', 'toast'] as $key) {
            $shots[$key]->pin($wife);
        }

        $doors = $shots['doors'];
        foreach ([
            'Tung reaches for the table.',
            'The doors open on the foyer.',
            'Tung strikes table with bat…',
        ] as $prompt) {
            $doors->versions()->create([
                'frame_path' => $doors->frame_path,
                'prompt' => $prompt,
                'model' => 'FLUX',
                'duration_s' => $doors->duration_s,
                'truth_tag' => $doors->truth_tag,
            ]);
        }

        return $sequence->fresh(['shots']);
    }

    /**
     * Durations sum to 3:20 and pack into four shorts on shot boundaries:
     * 52 | 28+24=52 | 26+22=48 | 48.
     *
     * @return list<array{key: string, title: string, duration: float, tag: TruthTag, prompt: string, narration: string, plaque?: string}>
     */
    private function definitions(): array
    {
        return [
            [
                'key' => 'gala',
                'title' => 'Gala',
                'duration' => 52,
                'tag' => TruthTag::Documented,
                'prompt' => 'Wide ballroom, orchestra on the balcony, couples dancing, Tung in a white tuxedo at the edge of the floor.',
                'narration' => 'The night of the gala, the ballroom was full and the orchestra was still playing.',
            ],
            [
                'key' => 'setting',
                'title' => 'Empty setting',
                'duration' => 28,
                'tag' => TruthTag::Documented,
                'prompt' => 'One empty place setting. The soup is untouched and a chair is pulled out.',
                'narration' => 'One empty setting. The places were laid, and nobody had touched the soup.',
            ],
            [
                'key' => 'pearl',
                'title' => 'The pearl',
                'duration' => 24,
                'tag' => TruthTag::Legend,
                'prompt' => 'Close on the pearl at her throat, the only jewelry she kept on.',
                'narration' => 'She wore the pearl he had given her that spring. It was the only jewelry she kept on.',
            ],
            [
                'key' => 'glance',
                'title' => 'The glance',
                'duration' => 26,
                'tag' => TruthTag::Legend,
                'prompt' => 'He looks across the table once. She does not look back.',
                'narration' => 'He looked across the table once. She did not look back.',
            ],
            [
                'key' => 'doors',
                'title' => 'Doors slam',
                'duration' => 22,
                'tag' => TruthTag::Invented,
                'prompt' => 'Tung strikes table with bat…',
                'narration' => 'The doors slammed. Someone said the police were in the foyer.',
            ],
            [
                'key' => 'toast',
                'title' => 'Still toasting',
                'duration' => 48,
                'tag' => TruthTag::Documented,
                'prompt' => 'The far table is still toasting as he is taken out through the doors.',
                'narration' => 'They were still toasting at the far table when he was taken out.',
                'plaque' => 'Arrested in 1923 for a murder…',
            ],
        ];
    }
}
