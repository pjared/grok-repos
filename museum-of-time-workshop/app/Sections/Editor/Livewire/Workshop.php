<?php

namespace App\Sections\Editor\Livewire;

use App\Enums\CueType;
use App\Enums\ExportKind;
use App\Enums\ExportStatus;
use App\Enums\ScenePackStatus;
use App\Enums\ShotStatus;
use App\Enums\TruthTag;
use App\Jobs\ExportEpisodeJob;
use App\Jobs\ExportShortsJob;
use App\Jobs\GenerateShotJob;
use App\Models\Character;
use App\Models\Export;
use App\Models\ScenePackSubmission;
use App\Models\Sequence;
use App\Models\Shot;
use App\Video\FrameGuard;
use App\Video\HouseStandard;
use App\Video\ShortsSplitter;
use App\Video\Stamp;
use App\Workshop\AddScene;
use App\Workshop\ExhibitImporter;
use App\Workshop\SceneInbox;
use Illuminate\Validation\ValidationException;
use Livewire\Attributes\Layout;
use Livewire\Component;
use Livewire\Features\SupportFileUploads\TemporaryUploadedFile;
use Livewire\WithFileUploads;

#[Layout('layouts.workshop')]
class Workshop extends Component
{
    use WithFileUploads;

    public ?int $sequenceId = null;

    public ?int $selectedShotId = null;

    public string $aspect = '16:9';

    public string $search = '';

    public bool $showVersions = false;

    public bool $showExport = false;

    public bool $addingCharacter = false;

    public string $newCharacter = '';

    public string $prompt = '';

    public string $model = 'FLUX';

    public string $duration = '4.0';

    public string $truthTag = 'documented';

    public ?string $notice = null;

    public ?TemporaryUploadedFile $frameUpload = null;

    public ?TemporaryUploadedFile $packUpload = null;

    public function mount(): void
    {
        $sequence = Sequence::query()->latest('id')->first();
        $this->sequenceId = $sequence?->id;
        $first = $sequence?->shots()->orderBy('order')->first();

        if ($first) {
            $this->fillFromShot($first);
        }
    }

    public function selectShot(int $shotId): void
    {
        $shot = $this->findShot($shotId);
        $this->fillFromShot($shot);
        $this->showVersions = false;
    }

    public function setAspect(string $aspect): void
    {
        if (in_array($aspect, ['16:9', '9:16'], true)) {
            $this->aspect = $aspect;
        }
    }

    public function updatedPrompt(): void
    {
        $this->persist();
    }

    public function updatedModel(): void
    {
        $this->persist();
    }

    public function updatedDuration(): void
    {
        $this->persist();
    }

    public function updatedTruthTag(): void
    {
        $this->persist();
    }

    public function regenerate(): void
    {
        $shot = $this->persist();

        if (! $shot->hasFrame()) {
            $this->notice = FrameGuard::message($shot);

            return;
        }

        $this->notice = null;
        $shot->snapshotVersion();
        $shot->update(['status' => ShotStatus::Queued]);
        GenerateShotJob::dispatch($shot->id);
    }

    public function addScene(AddScene $addScene): void
    {
        $sequence = $this->sequence();

        if (! $sequence) {
            return;
        }

        $this->fillFromShot($addScene->append($sequence));
        $this->notice = null;
        $this->showVersions = false;
    }

    public function insertAfter(AddScene $addScene): void
    {
        $sequence = $this->sequence();

        if (! $sequence || ! $this->selectedShotId) {
            return;
        }

        $this->fillFromShot($addScene->insertAfter($sequence, $this->findShot($this->selectedShotId)));
        $this->notice = null;
        $this->showVersions = false;
    }

    public function uploadFrame(): void
    {
        if (! $this->selectedShotId) {
            return;
        }

        $this->validate([
            'frameUpload' => 'required|image|max:10240',
        ]);

        $shot = $this->findShot($this->selectedShotId);
        $path = $this->frameUpload->store('frames/'.$shot->sequence_id, 'public');
        $shot->update([
            'frame_path' => $path,
            'clip_path' => null,
            'status' => ShotStatus::Draft,
        ]);
        $this->frameUpload = null;
        $this->notice = null;
    }

    public function importCurrentExhibit(ExhibitImporter $importer): void
    {
        $sequence = $this->sequence();

        if (! $sequence) {
            $this->notice = 'Open an exhibit before importing one.';

            return;
        }

        try {
            $submission = $importer->submit($sequence->exhibit->slug);
            $this->notice = $submission->filename.' is waiting for approval.';
        } catch (\Throwable $exception) {
            $this->notice = $exception->getMessage() !== ''
                ? $exception->getMessage()
                : 'Exhibit pack could not be imported.';
        }
    }

    public function importPack(SceneInbox $inbox): void
    {
        try {
            $this->validate([
                'packUpload' => 'required|file|mimes:zip|max:51200',
            ]);

            $submission = $inbox->receive(
                $this->packUpload->getRealPath(),
                $this->packUpload->getClientOriginalName(),
            );
            $this->packUpload = null;

            if ($submission->status === ScenePackStatus::Invalid) {
                $this->notice = $submission->error ?: 'Scene pack could not be imported.';

                return;
            }

            $this->notice = $submission->filename.' is waiting for approval.';
        } catch (ValidationException $exception) {
            $this->notice = $exception->validator->errors()->first() ?: 'Scene pack could not be imported.';
        } catch (\Throwable $exception) {
            $this->notice = $exception->getMessage() !== ''
                ? $exception->getMessage()
                : 'Scene pack could not be imported.';
        }
    }

    public function approvePack(int $submissionId, SceneInbox $inbox): void
    {
        $submission = ScenePackSubmission::query()->findOrFail($submissionId);

        try {
            $shots = $inbox->approve($submission);
        } catch (\Throwable $exception) {
            $this->notice = $exception->getMessage();

            return;
        }

        $shot = $shots[array_key_last($shots)];
        $this->sequenceId = $shot->sequence_id;
        $this->fillFromShot($shot);
        $this->notice = 'Approved '.$submission->filename.'.';
        $this->showVersions = false;
    }

    public function rejectPack(int $submissionId, SceneInbox $inbox): void
    {
        $submission = ScenePackSubmission::query()->findOrFail($submissionId);
        $inbox->reject($submission);
        $this->notice = 'Rejected '.$submission->filename.'.';
    }

    public function restoreVersion(int $versionId): void
    {
        $shot = $this->findShot((int) $this->selectedShotId);
        $version = $shot->versions()->findOrFail($versionId);
        $shot->snapshotVersion();
        $shot->update([
            'prompt' => $version->prompt,
            'model' => $version->model ?? $shot->model,
            'duration_s' => $version->duration_s ?? $shot->duration_s,
            'truth_tag' => $version->truth_tag ?? $shot->truth_tag,
            'frame_path' => $version->frame_path ?: $shot->frame_path,
            'clip_path' => $version->clip_path,
            'status' => $version->clip_path ? ShotStatus::Ready : ShotStatus::Draft,
        ]);
        $this->fillFromShot($shot->fresh());
    }

    public function reorder(int $draggedId, int $targetId): void
    {
        if ($draggedId === $targetId || ! $this->sequenceId) {
            return;
        }

        $shots = Shot::query()->where('sequence_id', $this->sequenceId)->orderBy('order')->get()->values();
        $dragged = $shots->firstWhere('id', $draggedId);
        if (! $dragged) {
            return;
        }

        $remaining = $shots->reject(fn (Shot $shot) => $shot->id === $draggedId)->values();
        $targetIndex = $remaining->search(fn (Shot $shot) => $shot->id === $targetId);
        if ($targetIndex === false) {
            return;
        }

        $remaining->splice($targetIndex, 0, [$dragged]);

        foreach ($remaining->values() as $index => $shot) {
            $shot->update(['order' => $index + 1]);
        }
    }

    public function addCharacter(): void
    {
        $name = trim($this->newCharacter);
        if ($name === '') {
            return;
        }

        Character::query()->create([
            'name' => $name,
            'locked' => false,
        ]);

        $this->newCharacter = '';
        $this->addingCharacter = false;
    }

    public function toggleLock(int $characterId): void
    {
        $character = Character::query()->findOrFail($characterId);
        $character->locked = ! $character->locked;

        if ($character->locked && ! $character->reference_image && $this->selectedShotId) {
            $character->reference_image = Shot::query()->find($this->selectedShotId)?->frame_path;
        }

        $character->save();
    }

    public function togglePin(int $characterId): void
    {
        if (! $this->selectedShotId) {
            return;
        }

        $shot = $this->findShot($this->selectedShotId);
        $character = Character::query()->findOrFail($characterId);

        if ($shot->characters()->whereKey($character->id)->exists()) {
            $shot->unpin($character);
        } else {
            $shot->pin($character);
        }
    }

    public function queueEpisode(): void
    {
        $this->queue(ExportKind::Episode, ExportEpisodeJob::class);
    }

    public function queueShorts(): void
    {
        $this->queue(ExportKind::Shorts, ExportShortsJob::class);
    }

    public function render()
    {
        $sequence = $this->sequence();
        $shots = $sequence?->shots()->with(['cues', 'characters', 'versions'])->get() ?? collect();
        $selected = $shots->firstWhere('id', $this->selectedShotId);
        $needle = mb_strtolower(trim($this->search));

        $characters = Character::query()->orderBy('name')->get();
        if ($needle !== '') {
            $characters = $characters->filter(
                fn (Character $character) => str_contains(mb_strtolower($character->name), $needle),
            )->values();
        }

        $total = (float) $shots->sum('duration_s');
        $cursor = 0.0;
        $timeline = [];
        $narration = [];
        $plaques = [];

        foreach ($shots as $shot) {
            $haystack = mb_strtolower($shot->title.' '.$shot->prompt.' '.$shot->cues->pluck('text')->implode(' ').' '.$shot->characters->pluck('name')->implode(' '));
            $timeline[] = [
                'id' => $shot->id,
                'order' => $shot->order,
                'title' => $shot->title,
                'start' => $cursor,
                'duration' => (float) $shot->duration_s,
                'frame' => $shot->frameUrl(),
                'clip' => $shot->clipUrl(),
                'truth' => $shot->truth_tag->value,
                'match' => $needle === '' || str_contains($haystack, $needle),
            ];

            foreach ($shot->cues as $cue) {
                $item = [
                    'id' => $cue->id,
                    'start' => $cursor + (float) $cue->offset_s,
                    'duration' => max(0.1, (float) $shot->duration_s - (float) $cue->offset_s),
                    'text' => $cue->text,
                    'voice' => $cue->voice,
                ];

                if ($cue->type === CueType::Narration) {
                    $narration[] = $item;
                } else {
                    $plaques[] = $item;
                }
            }

            $cursor += (float) $shot->duration_s;
        }

        $wing = $sequence?->exhibit?->wing()?->name;
        $exhibit = $sequence?->exhibit?->name;
        $split = $shots->isEmpty() ? [] : app(ShortsSplitter::class)->split(
            $shots->map(fn (Shot $shot) => ['id' => $shot->id, 'duration' => (float) $shot->duration_s])->all(),
        );

        $shorts = [];
        $shortCursor = 0.0;
        $shortTotal = count($split);
        foreach ($split as $index => $group) {
            $number = $index + 1;
            $shorts[] = [
                'number' => $number,
                'total' => $shortTotal,
                'start' => $shortCursor,
                'duration' => $group['duration'],
                'warning' => $group['warning'],
                'stamp' => Stamp::text($wing ?? 'Wing', $exhibit ?? 'Exhibit', $number, $shortTotal),
                'label' => 'Short '.$number.' of '.$shortTotal.' · '.round($group['duration']).'s',
                'active' => $selected && collect($group['shots'])->contains(fn ($entry) => $entry['id'] === $selected->id),
            ];
            $shortCursor += $group['duration'];
        }

        $episodeWarning = $total > 0 ? HouseStandard::episodeWarning($total) : null;

        return view('sections.editor.workshop', [
            'sequence' => $sequence,
            'shots' => $shots,
            'selected' => $selected,
            'characters' => $characters,
            'timeline' => $timeline,
            'narration' => $narration,
            'plaques' => $plaques,
            'shorts' => $shorts,
            'total' => $total,
            'episodeWarning' => $episodeWarning,
            'breadcrumb' => $wing && $exhibit ? $wing.'  /  '.$exhibit : 'Workshop',
            'exports' => $sequence
                ? Export::query()->where('sequence_id', $sequence->id)->latest()->limit(6)->get()
                : collect(),
            'models' => ['FLUX', 'Runway', 'Kling'],
            'pendingPacks' => app(SceneInbox::class)->scan(),
        ]);
    }

    private function queue(ExportKind $kind, string $job): void
    {
        $sequence = $this->sequence();

        if (! $sequence) {
            return;
        }

        try {
            FrameGuard::assertExportable($sequence);
        } catch (\RuntimeException $exception) {
            $this->notice = $exception->getMessage();
            $this->showExport = true;

            return;
        }

        $this->notice = null;

        $export = Export::query()->create([
            'sequence_id' => $this->sequenceId,
            'kind' => $kind,
            'status' => ExportStatus::Queued,
        ]);

        $job::dispatch($export->id);
        $this->showExport = true;
    }

    private function persist(): Shot
    {
        $shot = $this->findShot((int) $this->selectedShotId);
        $shot->update([
            'prompt' => $this->prompt,
            'model' => $this->model,
            'duration_s' => max(0.2, (float) $this->duration),
            'truth_tag' => TruthTag::from($this->truthTag),
        ]);

        return $shot;
    }

    private function fillFromShot(Shot $shot): void
    {
        $this->selectedShotId = $shot->id;
        $this->prompt = (string) $shot->prompt;
        $this->model = (string) $shot->model;
        $this->duration = number_format((float) $shot->duration_s, 1, '.', '');
        $this->truthTag = $shot->truth_tag->value;
    }

    private function findShot(int $shotId): Shot
    {
        return Shot::query()
            ->where('sequence_id', $this->sequenceId)
            ->findOrFail($shotId);
    }

    private function sequence(): ?Sequence
    {
        if (! $this->sequenceId) {
            return null;
        }

        return Sequence::query()->with(['exhibit.hall.wing'])->find($this->sequenceId);
    }
}
