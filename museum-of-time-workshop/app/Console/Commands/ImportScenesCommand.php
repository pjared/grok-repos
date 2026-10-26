<?php

namespace App\Console\Commands;

use App\Enums\CueType;
use App\Workshop\AddScene;
use App\Workshop\ScenePack;
use Illuminate\Console\Command;

class ImportScenesCommand extends Command
{
    protected $signature = 'workshop:import-scenes {file : Path to a scene pack JSON file}';

    protected $description = 'Import a scene pack JSON file into its exhibit sequence';

    public function handle(AddScene $addScene): int
    {
        try {
            $shots = ScenePack::load((string) $this->argument('file'))->import($addScene);
        } catch (\InvalidArgumentException $exception) {
            $this->error($exception->getMessage());

            return self::FAILURE;
        }

        $payload = array_map(function ($shot) {
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
        }, $shots);

        $this->line(json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES));

        return self::SUCCESS;
    }
}
