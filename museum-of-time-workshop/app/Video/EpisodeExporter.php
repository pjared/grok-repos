<?php

namespace App\Video;

use App\Enums\CueType;
use App\Enums\TruthTag;
use App\Models\Sequence;
use App\Models\Shot;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;

class EpisodeExporter
{
    public function __construct(
        private readonly Concatenator $concatenator,
        private readonly Ffmpeg $ffmpeg,
        private readonly ClipEnsurer $clips,
    ) {}

    public function export(Sequence $sequence): ExportResult
    {
        try {
            return $this->burn($sequence);
        } finally {
            Drawtext::cleanup();
        }
    }

    private function burn(Sequence $sequence): ExportResult
    {
        FrameGuard::assertExportable($sequence);
        $this->clips->ensure($sequence);
        $sequence->load(['exhibit.hall.wing']);
        $shots = $sequence->shots()->with('cues')->get();

        if ($shots->isEmpty()) {
            throw new \RuntimeException('Sequence has no shots.');
        }

        $warnings = [];
        $duration = (float) $shots->sum('duration_s');
        $range = HouseStandard::episodeWarning($duration);
        if ($range) {
            $warnings[] = $range;
        }

        $joined = $this->concatenator->join($shots->map(fn (Shot $shot) => $this->clip($shot))->all());

        $filters = [];
        $subtitles = [];
        $cursor = 0.0;

        foreach ($shots as $shot) {
            foreach ($shot->cues as $cue) {
                $start = $cursor + (float) $cue->offset_s;
                $end = $cursor + (float) $shot->duration_s;

                if ($cue->type === CueType::Plaque) {
                    if ($shot->truth_tag === TruthTag::Invented) {
                        $warnings[] = "Invented shot \"{$shot->title}\" has plaque text. It was left off the burn-in so invented material is not presented as museum fact.";
                    } else {
                        $filters[] = Drawtext::filter($cue->text, [
                            'size' => 28,
                            'y' => 'h-th-48',
                            'enable' => Drawtext::between($start, $end),
                        ]);
                    }
                }

                if ($cue->type === CueType::Narration && trim((string) $cue->text) !== '') {
                    $subtitles[] = ['start' => $start, 'end' => $end, 'text' => $cue->text];
                }
            }

            $cursor += (float) $shot->duration_s;
        }

        $picture = $joined;
        if ($filters !== []) {
            $picture = tempnam(sys_get_temp_dir(), 'mot-episode-').'.mp4';
            $this->ffmpeg->run([
                '-i', $joined,
                '-vf', implode(',', $filters),
                '-an',
                '-c:v', 'libx264',
                '-preset', 'ultrafast',
                '-tune', 'stillimage',
                '-crf', '28',
                '-pix_fmt', 'yuv420p',
                $picture,
            ]);
        }

        $relative = 'exports/episode-'.$sequence->id.'-'.now()->format('YmdHis').'.mp4';
        $final = Storage::disk('public')->path($relative);
        File::ensureDirectoryExists(dirname($final));
        $this->mux($picture, $subtitles, $final);

        return new ExportResult($relative, $warnings, duration: $duration);
    }

    private function clip(Shot $shot): string
    {
        if (! $shot->clip_path) {
            throw new \RuntimeException("Shot \"{$shot->title}\" has no rendered clip.");
        }

        $absolute = Storage::disk('public')->path($shot->clip_path);
        if (! is_file($absolute)) {
            throw new \RuntimeException("Clip for \"{$shot->title}\" is missing on disk.");
        }

        return $absolute;
    }

    /**
     * @param  list<array{start: float, end: float, text: string}>  $subtitles
     */
    private function mux(string $picture, array $subtitles, string $final): void
    {
        if ($subtitles === []) {
            File::copy($picture, $final);

            return;
        }

        $srt = SubtitleBuilder::write($subtitles);
        $this->ffmpeg->run([
            '-i', $picture,
            '-i', $srt,
            '-map', '0:v',
            '-map', '1:s',
            '-c:v', 'copy',
            '-c:s', 'mov_text',
            $final,
        ]);
        @unlink($srt);
    }
}
