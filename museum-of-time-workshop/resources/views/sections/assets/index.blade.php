<div class="h-full p-3" x-on:mot-search.window="$wire.set('search', $event.detail)">
    <x-slot:breadcrumb>Assets</x-slot:breadcrumb>
    <x-slot:search>
        <label class="block w-[320px]">
            <input id="workshop-search" x-on:input.debounce.200ms="$dispatch('mot-search', $event.target.value)" type="search" placeholder="⌘K  Search media" class="h-6 w-full rounded-full bg-[#22232b] px-3 text-xs text-[#e6e6ea] placeholder:text-[#6c6c78] focus:outline-none">
        </label>
    </x-slot:search>
    <x-slot:actions>
        <a href="{{ route('editor.index') }}" class="inline-flex h-7 items-center rounded-lg bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a] px-4 text-sm font-semibold text-white">Editor</a>
    </x-slot:actions>

    <section class="h-full overflow-auto rounded-[14px] bg-[#16171d] p-6">
        <h1 class="text-xl font-semibold">Assets</h1>
        <p class="mt-2 max-w-2xl text-sm text-[#8a8a96]">Rendered media from MEDIA_ROOT, grouped by exhibit. Files stay outside the repo and are linked for preview.</p>
        @if ($notice)
            <p class="mt-4 max-w-2xl rounded-lg bg-[#3a1630] px-3 py-2 text-xs text-[#ff7ab8]">{{ $notice }}</p>
        @endif
        @if ($linkNotice)
            <p class="mt-4 max-w-2xl rounded-lg bg-[#3a1630] px-3 py-2 text-xs text-[#ff7ab8]">{{ $linkNotice }}</p>
        @endif
        @if (! $hasRoot)
            <p class="mt-6 text-sm text-[#6c6c78]">Set MEDIA_ROOT to the folder of rendered exhibits, video, audio, and previews.</p>
        @endif
        <div class="mt-6 space-y-8">
            @forelse ($groups as $group)
                <section wire:key="media-{{ $group['exhibit'] }}">
                    <div class="flex flex-wrap items-center gap-3">
                        <h2 class="text-base font-semibold">{{ $group['label'] }}</h2>
                        @if ($group['importable'])
                            <button type="button" wire:click="importExhibit('{{ $group['exhibit'] }}')" class="h-7 rounded-lg bg-[#22232b] px-3 text-xs text-[#d7ccff]">Import exhibit</button>
                        @endif
                    </div>
                    <div class="mt-3 grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
                        @foreach ($group['files'] as $file)
                            <article wire:key="file-{{ $file['relative'] }}" class="overflow-hidden rounded-lg bg-[#22232b]">
                                @if ($file['kind'] === 'image')
                                    <img src="{{ $file['url'] }}" alt="" class="h-36 w-full object-cover">
                                @elseif ($file['kind'] === 'video')
                                    <video src="{{ $file['url'] }}" preload="metadata" controls class="h-36 w-full bg-black object-cover"></video>
                                @else
                                    <div class="flex h-36 items-center px-3">
                                        <audio src="{{ $file['url'] }}" controls class="w-full"></audio>
                                    </div>
                                @endif
                                <div class="flex items-center justify-between gap-2 px-3 py-2 text-xs">
                                    <span class="truncate">{{ $file['name'] }}</span>
                                    @if ($file['duration_label'])
                                        <span class="shrink-0 text-[#8a8a96]">{{ $file['duration_label'] }}</span>
                                    @endif
                                </div>
                            </article>
                        @endforeach
                    </div>
                </section>
            @empty
                @if ($hasRoot)
                    <p class="text-sm text-[#6c6c78]">No mp4, mov, mp3, jpg, or png files in the media folder.</p>
                @endif
            @endforelse
        </div>
    </section>
</div>
