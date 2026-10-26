<?php

namespace App\Video;

use App\Enums\CueType;
use App\Enums\TruthTag;
use App\Models\Sequence;
use App\Models\Shot;
use Illuminate\Support\Collection;
use Illuminate\Support\Facades\File;
use Illuminate\Support\Facades\Storage;

class ShortsExporter
{
    public function __construct(
        private readonly Concatenator $concatenator,
        private readonly Ffmpeg $ffmpeg,
        private readonly ShortsSplitter $splitter,
        private readonly ClipEnsurer $clips,
    ) {}

    public function export(Sequence $sequence): ExportResult
    {
        $this->clips->ensure($sequence);
        $sequence->load(['exhibit.hall.wing']);
        $shots = $sequence->shots()->with('cues')->get();

        if ($shots->isEmpty()) {
            throw new \RuntimeException('Sequence has no shots.');
        }

        $groups = $this->splitter->split(
            $shots->map(fn (Shot $shot) => [
                'id' => $shot->id,
                'duration' => (float) $shot->duration_s,
            ])->all(),
        );

        $wing = $sequence->exhibit->wing()?->name ?? 'Wing';
        $exhibit = $sequence->exhibit->name;
        $total = count($groups);
        $stampTime = now()->format('YmdHis');
        $warnings = [];
        $files = [];

        foreach ($groups as $index => $group) {
            $number = $index + 1;
            $stamp = Stamp::text($wing, $exhibit, $number, $total);

            if ($group['warning']) {
                $warnings[] = "Short {$number} of {$total}: {$group['warning']}";
            }

            $groupShots = collect($group['shots'])
                ->map(fn (array $entry) => $shots->firstWhere('id', $entry['id']))
                ->filter();

            $picture = $this->renderShort($groupShots, $stamp, $warnings);
            $relative = sprintf('exports/short-%d-%d-of-%d-%s.mp4', $sequence->id, $number, $total, $stampTime);
            $final = Storage::disk('public')->path($relative);
            File::ensureDirectoryExists(dirname($final));

            $subtitles = $this->subtitles($groupShots);
            if ($subtitles === []) {
                File::copy($picture, $final);
                @unlink($picture);
            } else {
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
                @unlink($picture);
            }

            $files[] = [
                'path' => $relative,
                'stamp' => $stamp,
                'duration' => (float) $group['duration'],
                'number' => $number,
                'total' => $total,
            ];
        }

        return new ExportResult($files[0]['path'] ?? null, $warnings, $files, (float) $shots->sum('duration_s'));
    }

    /**
     * @param  Collection<int, Shot>  $shots
     * @param  list<string>  $warnings
     */
    private function renderShort(Collection $shots, string $stamp, array &$warnings): string
    {
        $joined = $this->concatenator->join(
            $shots->map(function (Shot $shot) {
                if (! $shot->clip_path || ! is_file(Storage::disk('public')->path($shot->clip_path))) {
                    throw new \RuntimeException("Shot \"{$shot->title}\" has no rendered clip.");
                }

                return Storage::disk('public')->path($shot->clip_path);
            })->all(),
        );

        $width = (int) config('video.short.width', 720);
        $height = (int) config('video.short.height', 1280);
        $filters = [
            "scale={$width}:{$height}:force_original_aspect_ratio=decrease,pad={$width}:{$height}:(ow-iw)/2:(oh-ih)/2:color=0x0f1014",
            Drawtext::filter($stamp, ['size' => 22, 'y' => 'h-th-28']),
        ];

        $cursor = 0.0;
        foreach ($shots as $shot) {
            foreach ($shot->cues as $cue) {
                if ($cue->type !== CueType::Plaque) {
                    continue;
                }

                $start = $cursor + (float) $cue->offset_s;
                $end = $cursor + (float) $shot->duration_s;

                if ($shot->truth_tag === TruthTag::Invented) {
                    $warnings[] = "Invented shot \"{$shot->title}\" has plaque text. It was left off the burn-in so invented material is not presented as museum fact.";

                    continue;
                }

                $filters[] = Drawtext::filter($cue->text, [
                    'size' => 24,
                    'y' => 'h-th-84',
                    'enable' => Drawtext::between($start, $end),
                ]);
            }

            $cursor += (float) $shot->duration_s;
        }

        $output = tempnam(sys_get_temp_dir(), 'mot-short-').'.mp4';
        $this->ffmpeg->run([
            '-i', $joined,
            '-vf', implode(',', $filters),
            '-an',
            '-c:v', 'libx264',
            '-preset', 'ultrafast',
            '-tune', 'stillimage',
            '-crf', '28',
            '-pix_fmt', 'yuv420p',
            $output,
        ]);
        @unlink($joined);

        return $output;
    }

    /**
     * @param  Collection<int, Shot>  $shots
     * @return list<array{start: float, end: float, text: string}>
     */
    private function subtitles(Collection $shots): array
    {
        $cues = [];
        $cursor = 0.0;

        foreach ($shots as $shot) {
            foreach ($shot->cues as $cue) {
                if ($cue->type !== CueType::Narration) {
                    continue;
                }

                $cues[] = [
                    'start' => $cursor + (float) $cue->offset_s,
                    'end' => $cursor + (float) $shot->duration_s,
                    'text' => $cue->text,
                ];
            }

            $cursor += (float) $shot->duration_s;
        }

        return $cues;
    }
}
