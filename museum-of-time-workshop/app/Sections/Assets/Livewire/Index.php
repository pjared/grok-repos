<?php

namespace App\Sections\Assets\Livewire;

use App\Enums\ScenePackStatus;
use App\Workshop\ExhibitImporter;
use App\Workshop\MediaLibrary;
use Livewire\Attributes\Layout;
use Livewire\Component;

#[Layout('layouts.workshop')]
class Index extends Component
{
    public string $search = '';

    public ?string $notice = null;

    public function importExhibit(string $slug, ExhibitImporter $importer): void
    {
        try {
            $submission = $importer->submit($slug);
            $this->notice = $submission->status === ScenePackStatus::Invalid
                ? ($submission->error ?: 'Exhibit pack could not be imported.')
                : $submission->filename.' is waiting for approval.';
        } catch (\Throwable $exception) {
            $this->notice = $exception->getMessage() !== ''
                ? $exception->getMessage()
                : 'Exhibit pack could not be imported.';
        }
    }

    public function render(MediaLibrary $library)
    {
        $needle = mb_strtolower(trim($this->search));
        $groups = [];

        foreach ($library->groups() as $group) {
            $files = array_values(array_filter(
                $group['files'],
                fn (array $file) => $needle === ''
                    || str_contains(mb_strtolower($file['name'].' '.$group['label'].' '.$group['exhibit']), $needle),
            ));

            if ($needle !== '' && $files === [] && ! str_contains(mb_strtolower($group['label'].' '.$group['exhibit']), $needle)) {
                continue;
            }

            $group['files'] = $files;
            $groups[] = $group;
        }

        return view('sections.assets.index', [
            'groups' => $groups,
            'hasRoot' => $library->root() !== null,
            'linkNotice' => $library->linkNotice,
        ]);
    }
}
