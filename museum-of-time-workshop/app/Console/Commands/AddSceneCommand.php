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
        {--after-id= : Shot id to insert after}
        {--after-order= : Shot order to insert after}
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

            $after = $this->after($sequence);
            $shot = $after
                ? $addScene->insertAfter($sequence, $after, $attributes)
                : $addScene->append($sequence, $attributes);
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

    private function after(Sequence $sequence): ?Shot
    {
        $id = $this->blankToNull($this->option('after-id'));
        $order = $this->blankToNull($this->option('after-order'));
        $hasId = $id !== null;
        $hasOrder = $order !== null;

        if ($hasId && $hasOrder) {
            throw new \InvalidArgumentException('Pass only one of --after-id or --after-order.');
        }

        if (! $hasId && ! $hasOrder) {
            return null;
        }

        if ($hasId) {
            if (! ctype_digit($id)) {
                throw new \InvalidArgumentException('Pass --after-id as a shot id.');
            }

            $shot = $sequence->shots()->whereKey((int) $id)->first();

            if (! $shot) {
                throw new \InvalidArgumentException("No shot id {$id} on this sequence to insert after.");
            }

            return $shot;
        }

        if (! ctype_digit($order)) {
            throw new \InvalidArgumentException('Pass --after-order as an order number.');
        }

        $shot = $sequence->shots()->get()->first(fn (Shot $candidate) => (int) $candidate->order === (int) $order);

        if (! $shot) {
            throw new \InvalidArgumentException("No shot at order {$order} on this sequence to insert after.");
        }

        return $shot;
    }

    private function blankToNull(mixed $value): ?string
    {
        if ($value === null || $value === '') {
            return null;
        }

        return (string) $value;
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
