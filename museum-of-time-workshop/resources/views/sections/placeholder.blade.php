<div class="h-full p-3" x-on:mot-search.window="$wire.set('search', $event.detail)">
    <x-slot:breadcrumb>{{ $title }}</x-slot:breadcrumb>
    <x-slot:search>
        <label class="block w-[320px]">
            <input id="workshop-search" x-on:input.debounce.200ms="$dispatch('mot-search', $event.target.value)" type="search" placeholder="⌘K  Search" class="h-6 w-full rounded-full bg-[#22232b] px-3 text-xs text-[#e6e6ea] placeholder:text-[#6c6c78] focus:outline-none">
        </label>
    </x-slot:search>
    <x-slot:actions>
        <a href="{{ route('editor.index') }}" class="inline-flex h-7 items-center rounded-lg bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a] px-4 text-sm font-semibold text-white">Export</a>
    </x-slot:actions>

    <section class="h-full overflow-auto rounded-[14px] bg-[#16171d] p-8">
        <div class="flex items-center gap-3">
            <h1 class="text-xl font-semibold">{{ $title }}</h1>
            <span class="rounded-full bg-[#2a2450] px-2 py-0.5 text-xs text-[#a993ff]">Placeholder</span>
        </div>
        <p class="mt-2 max-w-xl text-sm text-[#8a8a96]">This section is on the admin rail. The editor is the first working module.</p>
        <ul class="mt-6 max-w-2xl space-y-2">
            @forelse ($items as $item)
                <li class="rounded-lg bg-[#22232b] px-4 py-3 text-sm">{{ $item }}</li>
            @empty
                <li class="text-sm text-[#6c6c78]">Nothing here yet.</li>
            @endforelse
        </ul>
    </section>
</div>
