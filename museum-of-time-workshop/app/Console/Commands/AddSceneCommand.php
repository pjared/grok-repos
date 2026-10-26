<?php

namespace App\Console\Commands;

use App\Enums\CueType;
use App\Models\Sequence;
use App\Models\Shot;
use App\Workshop\AddScene;
use App\Workshop\ExhibitSequences;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

class AddSceneCommand extends Command
{
    protected $signature = 'workshop:add-scene
        {--exhibit= : Exhibit slug or id}
        {--after= : Shot id on that sequence, or its order number}
        {--prompt= : Prompt for the new scene}
        {--duration=4 : Duration in seconds}
        {--truth=invented : documented, legend, or invented}
        {--frame= : Path to a frame image}
        {--narration= : Narration cue}
        {--plaque= : Plaque cue}';

    protected $description = 'Add one scene to an exhibit sequence and print the shot as JSON';

    public function handle(AddScene $addScene): int
    {
        try {
            $sequence = ExhibitSequences::find((string) $this->option('exhibit'));
            $attributes = [
                'prompt' => (string) ($this->option('prompt') ?? ''),
                'duration' => $this->option('duration'),
                'truth' => (string) $this->option('truth'),
                'frame_path' => $this->frame($sequence->id),
                'narration' => $this->option('narration'),
                'plaque' => $this->option('plaque'),
            ];

            $after = $this->option('after');
            $shot = ($after === null || $after === '')
                ? $addScene->append($sequence, $attributes)
                : $addScene->insertAfter($sequence, $this->after($sequence, (string) $after), $attributes);
        } catch (\InvalidArgumentException $exception) {
            $this->error($exception->getMessage());

            return self::FAILURE;
        }

        $this->line(json_encode($this->payload($shot), JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));

        return self::SUCCESS;
    }

    private function frame(int $sequenceId): ?string
    {
        $path = $this->option('frame');

        if ($path === null || $path === '') {
            return null;
        }

        if (! is_file($path)) {
            throw new \InvalidArgumentException("Frame not found: {$path}");
        }

        $extension = strtolower(pathinfo($path, PATHINFO_EXTENSION) ?: 'jpg');

        if (! in_array($extension, ['jpg', 'jpeg', 'png', 'webp', 'gif'], true)) {
            throw new \InvalidArgumentException('Frame must be a jpg, png, webp, or gif.');
        }

        $relative = 'scenes/'.$sequenceId.'/'.Str::uuid().'.'.$extension;
        Storage::disk('public')->put($relative, File::get($path));

        return $relative;
    }

    private function after(Sequence $sequence, string $after): Shot
    {
        if (! ctype_digit($after)) {
            throw new \InvalidArgumentException('Pass --after as a shot id or order number.');
        }

        $needle = (int) $after;
        $shots = $sequence->shots()->get();
        $byId = $shots->firstWhere('id', $needle);

        if ($byId) {
            return $byId;
        }

        $byOrder = $shots->first(fn (Shot $shot) => (int) $shot->order === $needle);

        if ($byOrder) {
            return $byOrder;
        }

        throw new \InvalidArgumentException("No shot {$after} on this sequence to insert after.");
    }

    /**
     * @return array<string, mixed>
     */
    private function payload(Shot $shot): array
    {
        $shot->load(['cues', 'sequence.exhibit']);

        return [
            'id' => $shot->id,
            'sequence_id' => $shot->sequence_id,
            'exhibit' => $shot->sequence->exhibit->slug,
            'order' => $shot->order,
            'title' => $shot->title,
            'frame_path' => $shot->frame_path,
            'prompt' => $shot->prompt,
            'model' => $shot->model,
            'duration_s' => (float) $shot->duration_s,
            'truth_tag' => $shot->truth_tag->value,
            'status' => $shot->status->value,
            'narration' => $shot->cues->firstWhere('type', CueType::Narration)?->text,
            'plaque' => $shot->cues->firstWhere('type', CueType::Plaque)?->text,
        ];
    }
}
