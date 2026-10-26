<div
    @class(['flex h-full flex-col gap-3 p-3', 'min-h-0'])
    x-on:mot-search.window="$wire.set('search', $event.detail)"
    x-on:mot-export.window="$wire.$toggle('showExport')"
    @if ($selected && in_array($selected->status->value, ['queued', 'rendering'], true)) wire:poll.2s @endif
>
    <x-slot:breadcrumb>{{ $breadcrumb }}</x-slot:breadcrumb>
    <x-slot:search>
        <label class="block w-[320px]">
            <input id="workshop-search" x-on:input.debounce.200ms="$dispatch('mot-search', $event.target.value)" type="search" placeholder="⌘K  Search shots, characters, plaques" class="h-6 w-full rounded-full bg-[#22232b] px-3 text-xs text-[#e6e6ea] placeholder:text-[#6c6c78] focus:outline-none">
        </label>
    </x-slot:search>
    <x-slot:actions>
        <button type="button" x-on:click="$dispatch('mot-export')" class="inline-flex h-7 items-center rounded-lg bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a] px-4 text-sm font-semibold text-white">Export</button>
    </x-slot:actions>

    @if (! $sequence)
        <section class="grid flex-1 place-items-center rounded-[14px] bg-[#16171d] text-center">
            <div>
                <h1 class="text-lg font-semibold">No sequence yet</h1>
                <p class="mt-2 text-sm text-[#8a8a96]">Run <code class="text-[#b5b5c0]">php artisan workshop:seed-gala</code> to load the Gala Arrest storyboard.</p>
            </div>
        </section>
    @else
        @php
            $transport = ['shots' => $timeline, 'shorts' => $shorts, 'duration' => $total];
        @endphp
        <script type="application/json" id="mot-transport">@json($transport)</script>
        <div
            class="flex min-h-0 flex-1 flex-col gap-3"
            wire:key="transport-{{ md5(json_encode($transport)) }}"
            x-data="{
                playing: false,
                time: window.__motTime || 0,
                duration: {{ $total }},
                shots: [],
                shorts: [],
                dragId: null,
                pointer: null,
                init() {
                    const data = JSON.parse(document.getElementById('mot-transport').textContent);
                    this.shots = data.shots;
                    this.shorts = data.shorts;
                    this.duration = data.duration;
                },
                toggle() { this.playing = !this.playing; if (this.playing) this.loop(); },
                loop() {
                    let last = performance.now();
                    const step = (now) => {
                        if (!this.playing) return;
                        this.time = Math.min(this.duration, this.time + (now - last) / 1000);
                        last = now;
                        window.__motTime = this.time;
                        if (this.time >= this.duration) { this.playing = false; return; }
                        requestAnimationFrame(step);
                    };
                    requestAnimationFrame(step);
                },
                clock(value) {
                    const s = Math.max(0, Math.floor(value || 0));
                    return String(Math.floor(s / 60)).padStart(2, '0') + ':' + String(s % 60).padStart(2, '0');
                },
                currentShot() {
                    return this.shots.find((shot) => this.time >= shot.start && this.time < shot.start + shot.duration) || this.shots[this.shots.length - 1] || null;
                },
                currentStamp() {
                    const hit = this.shorts.find((item) => this.time >= item.start && this.time < item.start + item.duration) || this.shorts[this.shorts.length - 1];
                    return hit ? hit.stamp : '';
                },
                playhead() { return this.duration ? (this.time / this.duration * 100) + '%' : '0%'; },
                seek(event) {
                    const rect = event.currentTarget.getBoundingClientRect();
                    const ratio = Math.min(1, Math.max(0, (event.clientX - rect.left) / rect.width));
                    this.time = ratio * this.duration;
                    window.__motTime = this.time;
                },
                startDrag(event, id) {
                    if (event.button !== undefined && event.button !== 0) return;
                    this.dragId = id;
                    this.pointer = { x: event.clientX, y: event.clientY, moved: false };
                    const move = (e) => {
                        if (!this.pointer) return;
                        if (Math.hypot(e.clientX - this.pointer.x, e.clientY - this.pointer.y) > 4) this.pointer.moved = true;
                    };
                    const up = (e) => {
                        window.removeEventListener('pointermove', move);
                        window.removeEventListener('pointerup', up);
                        const el = document.elementFromPoint(e.clientX, e.clientY)?.closest('[data-shot-id]');
                        this.finishDrag(Number(el?.dataset.shotId || 0));
                    };
                    window.addEventListener('pointermove', move);
                    window.addEventListener('pointerup', up);
                },
                finishDrag(target) {
                    const dragged = this.dragId;
                    this.dragId = null;
                    this.pointer = null;
                    if (!dragged || !target || dragged === target) return;
                    this.$wire.reorder(dragged, target);
                }
            }"
        >
            <div class="flex min-h-0 flex-1 gap-3">
                <aside class="flex w-[240px] shrink-0 flex-col rounded-[14px] bg-[#16171d] p-4">
                    <div class="flex items-center justify-between">
                        <h2 class="font-semibold">Characters</h2>
                        <button type="button" wire:click="$toggle('addingCharacter')" class="text-[#7c5cff]" aria-label="Add character">+</button>
                    </div>
                    @if ($addingCharacter)
                        <form wire:submit="addCharacter" class="mt-3 flex gap-2">
                            <input wire:model="newCharacter" type="text" placeholder="Name" class="h-8 min-w-0 flex-1 rounded-lg bg-[#0f1014] px-2 text-sm focus:outline-none">
                            <button class="rounded-lg bg-[#2a2450] px-2 text-xs text-[#a993ff]" type="submit">Add</button>
                        </form>
                    @endif
                    <div class="mt-3 flex-1 space-y-2 overflow-auto pr-1">
                        @foreach ($characters as $character)
                            @php($pinned = $selected && $selected->characters->contains('id', $character->id))
                            <button type="button" wire:click="togglePin({{ $character->id }})" class="w-full rounded-[10px] bg-[#22232b] text-left {{ $pinned ? 'ring-1 ring-[#7c5cff]' : '' }}">
                                @if ($character->reference_image)
                                    <img src="{{ $character->referenceUrl() }}" alt="" class="h-16 w-full rounded-t-[10px] object-cover">
                                @endif
                                <span class="flex items-center justify-between px-3 py-3">
                                    <span class="truncate text-sm">{{ $character->name }}</span>
                                    @if ($character->locked)
                                        <span class="rounded-full bg-[#2a2450] px-2 py-0.5 text-[11px] text-[#a993ff]">ref</span>
                                    @endif
                                </span>
                            </button>
                            <div class="flex justify-end">
                                <button type="button" wire:click="toggleLock({{ $character->id }})" class="text-[11px] text-[#6c6c78] hover:text-[#b5b5c0]">
                                    {{ $character->locked ? 'Unlock reference' : 'Lock reference' }}
                                </button>
                            </div>
                        @endforeach
                    </div>
                    <div class="mt-4">
                        <h2 class="font-semibold">Truth tags</h2>
                        <div class="mt-2 flex flex-wrap gap-2">
                            <x-truth-tag tag="documented" />
                            <x-truth-tag tag="legend" />
                            <x-truth-tag tag="invented" />
                        </div>
                    </div>
                </aside>

                <section class="flex min-w-0 flex-1 flex-col gap-3">
                    <div class="relative min-h-0 flex-1 overflow-hidden rounded-[14px] bg-black">
                        <div class="absolute left-4 top-4 z-10 flex h-6 items-center rounded-full bg-[#22232b]/90 p-0.5 text-xs">
                            <button type="button" wire:click="setAspect('16:9')" class="rounded-full px-2 py-0.5 {{ $aspect === '16:9' ? 'bg-[#2d2e38] text-white' : 'text-[#9a9aa6]' }}">16:9</button>
                            <button type="button" wire:click="setAspect('9:16')" class="rounded-full px-2 py-0.5 {{ $aspect === '9:16' ? 'bg-[#2d2e38] text-white' : 'text-[#9a9aa6]' }}">9:16</button>
                        </div>
                        <div class="flex h-full items-center justify-center p-8">
                            <div class="{{ $aspect === '9:16' ? 'aspect-[9/16] h-full' : 'aspect-video w-full' }} max-h-full max-w-full overflow-hidden bg-black">
                                <img x-show="currentShot() && currentShot().frame" :src="currentShot() ? currentShot().frame : ''" alt="" class="h-full w-full object-contain">
                                <div x-show="!currentShot() || !currentShot().frame" class="grid h-full place-items-center text-[#555]">Preview</div>
                            </div>
                        </div>
                    </div>
                    <div class="flex h-[90px] shrink-0 items-center gap-4 rounded-[14px] bg-[#16171d] px-4">
                        <button type="button" x-on:click="toggle()" class="grid h-9 w-9 place-items-center rounded-full bg-white text-black" aria-label="Play">
                            <span x-text="playing ? '❚❚' : '▶'" class="text-sm"></span>
                        </button>
                        <div class="min-w-0">
                            <div class="font-semibold" x-text="clock(time) + ' / ' + clock(duration)"></div>
                            <div class="truncate text-xs text-[#8a8a96]" x-text="currentStamp()"></div>
                        </div>
                        <div class="ml-auto h-1.5 w-[280px] overflow-hidden rounded-full bg-[#2d2e38]">
                            <div class="h-full rounded-full bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a]" :style="`width: ${playhead()}`"></div>
                        </div>
                    </div>
                </section>

                <aside class="flex w-[340px] shrink-0 flex-col overflow-auto rounded-[14px] bg-[#16171d] p-4">
                    @if ($selected)
                        <div class="flex items-start justify-between gap-3">
                            <h2 class="text-[15px] font-semibold">Shot {{ $selected->order }} · {{ $selected->title }}</h2>
                            <x-truth-tag :tag="$selected->truth_tag" />
                        </div>
                        <div class="mt-3 h-[140px] overflow-hidden rounded-[10px] bg-[#22232b]">
                            @if ($selected->frame_path)
                                <img src="{{ $selected->frameUrl() }}" alt="" class="h-full w-full object-cover">
                            @else
                                <div class="grid h-full place-items-center text-xs text-[#6c6c78]">Empty frame</div>
                            @endif
                        </div>
                        <form wire:submit="uploadFrame" class="mt-2 flex items-center gap-2">
                            <input wire:model="frameUpload" type="file" accept="image/*" class="min-w-0 flex-1 text-[11px] text-[#8a8a96] file:mr-2 file:rounded-md file:border-0 file:bg-[#22232b] file:px-2 file:py-1 file:text-[11px] file:text-[#d7ccff]">
                            <button type="submit" class="h-7 shrink-0 rounded-lg bg-[#22232b] px-2 text-[11px] text-[#d7ccff]">Upload frame</button>
                        </form>
                        <button type="button" wire:click="insertAfter" class="mt-2 h-8 w-full rounded-[10px] bg-[#22232b] text-xs text-[#d7ccff]">Insert after</button>
                        @if ($notice)
                            <p class="mt-3 rounded-lg bg-[#3a1630] px-3 py-2 text-xs text-[#ff7ab8]">{{ $notice }}</p>
                        @endif
                        <label class="mt-4 block text-xs tracking-wide text-[#8a8a96]">PROMPT</label>
                        <textarea wire:model.blur="prompt" rows="3" class="mt-1 w-full rounded-[10px] border border-[#2d2e38] bg-[#0f1014] px-3 py-2 text-sm text-[#b5b5c0] focus:outline-none"></textarea>
                        <div class="mt-4 grid grid-cols-2 gap-3">
                            <label class="block text-xs text-[#8a8a96]">
                                MODEL
                                <select wire:model.live="model" class="mt-1 h-8 w-full rounded-lg bg-[#22232b] px-2 text-sm text-[#e6e6ea] focus:outline-none">
                                    @foreach ($models as $option)
                                        <option value="{{ $option }}">{{ $option }}</option>
                                    @endforeach
                                </select>
                            </label>
                            <label class="block text-xs text-[#8a8a96]">
                                DURATION
                                <input wire:model.blur="duration" type="number" min="0.2" step="0.1" class="mt-1 h-8 w-full rounded-lg bg-[#22232b] px-2 text-sm focus:outline-none">
                            </label>
                        </div>
                        <label class="mt-3 block text-xs text-[#8a8a96]">
                            TRUTH TAG
                            <select wire:model.live="truthTag" class="mt-1 h-8 w-full rounded-lg bg-[#22232b] px-2 text-sm focus:outline-none">
                                <option value="documented">documented</option>
                                <option value="legend">legend</option>
                                <option value="invented">invented</option>
                            </select>
                        </label>
                        <button type="button" wire:click="regenerate" wire:loading.attr="disabled" class="mt-4 h-10 w-full rounded-[10px] bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a] text-sm font-semibold text-white disabled:opacity-60">
                            <span wire:loading.remove wire:target="regenerate">Regenerate shot</span>
                            <span wire:loading wire:target="regenerate">Queuing…</span>
                        </button>
                        <p class="mt-2 text-center text-[11px] uppercase tracking-wide text-[#6c6c78]">{{ $selected->status->value }}</p>
                        <button type="button" wire:click="$toggle('showVersions')" class="mt-2 h-9 w-full rounded-[10px] bg-[#22232b] text-sm text-[#b5b5c0]">
                            Version history ({{ $selected->versions->count() }})
                        </button>
                        @if ($showVersions)
                            <ul class="mt-2 space-y-2">
                                @forelse ($selected->versions as $version)
                                    <li class="rounded-lg bg-[#0f1014] p-2 text-xs">
                                        <div class="text-[#8a8a96]">{{ $version->created_at?->format('H:i:s') }} · {{ $version->model }}</div>
                                        <div class="mt-1 line-clamp-2 text-[#b5b5c0]">{{ $version->prompt }}</div>
                                        <button type="button" wire:click="restoreVersion({{ $version->id }})" class="mt-1 text-[#a993ff]">Restore</button>
                                    </li>
                                @empty
                                    <li class="text-xs text-[#6c6c78]">No earlier versions yet.</li>
                                @endforelse
                            </ul>
                        @endif
                        @if ($selected->clip_path)
                            <video src="{{ $selected->clipUrl() }}" controls class="mt-3 w-full rounded-lg"></video>
                        @endif
                    @endif
                </aside>
            </div>

            @if ($pendingPacks->isNotEmpty())
                <section class="shrink-0 rounded-[14px] bg-[#16171d] px-4 py-3">
                    <h2 class="font-semibold">Inbox</h2>
                    <p class="mt-1 text-xs text-[#6c6c78]">Dropped packs stay pending until you approve them.</p>
                    <ul class="mt-3 space-y-2">
                        @foreach ($pendingPacks as $pack)
                            <li class="flex flex-wrap items-center gap-3 rounded-lg bg-[#22232b] px-3 py-2 text-sm" wire:key="pack-{{ $pack->id }}">
                                <span class="font-medium">{{ $pack->filename }}</span>
                                @if ($pack->status->value === 'invalid')
                                    <span class="text-xs text-[#ff7ab8]">{{ $pack->error }}</span>
                                    <button type="button" wire:click="rejectPack({{ $pack->id }})" class="ml-auto h-7 rounded-lg bg-[#3a1630] px-3 text-xs text-[#ff7ab8]">Reject</button>
                                @else
                                    <span class="text-xs text-[#8a8a96]">{{ $pack->summary['scenes'] ?? 0 }} scene(s) · {{ $pack->summary['exhibit'] ?? '' }}</span>
                                    <button type="button" wire:click="approvePack({{ $pack->id }})" class="ml-auto h-7 rounded-lg bg-[#163a2c] px-3 text-xs text-[#5ee0a0]">Approve</button>
                                    <button type="button" wire:click="rejectPack({{ $pack->id }})" class="h-7 rounded-lg bg-[#3a1630] px-3 text-xs text-[#ff7ab8]">Reject</button>
                                @endif
                            </li>
                        @endforeach
                    </ul>
                </section>
            @endif

            <section class="relative min-h-[292px] shrink-0 rounded-[14px] bg-[#16171d] px-4 py-3">
                <div class="flex items-center justify-between gap-3">
                    <h2 class="font-semibold">Timeline</h2>
                    <form wire:submit="importPack" class="flex items-center gap-2">
                        <input wire:model="packUpload" type="file" accept="application/json,.json" class="max-w-[180px] text-[11px] text-[#8a8a96] file:mr-2 file:rounded-md file:border-0 file:bg-[#22232b] file:px-2 file:py-1 file:text-[11px] file:text-[#d7ccff]">
                        <button type="submit" class="h-7 shrink-0 rounded-lg bg-[#22232b] px-2 text-xs text-[#d7ccff]">Import scenes</button>
                    </form>
                </div>
                <div class="pointer-events-none absolute bottom-3 top-16 w-px bg-[#ff5c8a]" style="left: calc(1rem + 4.5rem)" :style="`left: calc(1rem + 4.5rem + (100% - 2rem - 4.5rem) * ${duration ? time / duration : 0})`"></div>
                <div class="mt-3 grid grid-cols-[4.5rem_1fr] items-center gap-y-3">
                    <div class="text-xs text-[#8a8a96]">Shots</div>
                    <div class="flex items-center gap-2">
                    <div class="relative h-12 min-w-0 flex-1" x-on:click="seek($event)">
                        @foreach ($timeline as $shot)
                            <button
                                type="button"
                                draggable="true"
                                data-shot-id="{{ $shot['id'] }}"
                                wire:key="shot-block-{{ $shot['id'] }}"
                                x-on:pointerdown="startDrag($event, {{ $shot['id'] }})"
                                x-on:dragstart="dragId = {{ $shot['id'] }}; $event.dataTransfer.setData('text/plain', '{{ $shot['id'] }}'); $event.dataTransfer.effectAllowed = 'move'"
                                x-on:dragover.prevent
                                x-on:drop.prevent="finishDrag({{ $shot['id'] }})"
                                x-on:click.stop="$wire.selectShot({{ $shot['id'] }}); time = {{ $shot['start'] }}; window.__motTime = time"
                                style="left: {{ $total > 0 ? $shot['start'] / $total * 100 : 0 }}%; width: {{ $total > 0 ? $shot['duration'] / $total * 100 : 0 }}%;"
                                class="absolute inset-y-0 px-0.5 text-left"
                                :class="dragId === {{ $shot['id'] }} && pointer?.moved ? 'opacity-70' : ''"
                            >
                                <span @class([
                                    'flex h-full items-center truncate rounded-lg px-2 text-xs',
                                    'border-2 border-[#ff5c8a] bg-[#4a2450]' => $selected && $selected->id === $shot['id'],
                                    'bg-[#2a2450]' => ! $selected || $selected->id !== $shot['id'],
                                    'opacity-40' => ! $shot['match'],
                                ])>{{ $shot['order'] }} · {{ $shot['title'] }}</span>
                            </button>
                        @endforeach
                    </div>
                    <button type="button" wire:click="addScene" class="h-8 shrink-0 rounded-lg bg-[#2a2450] px-2 text-xs font-semibold text-[#d7ccff]">+ Add scene</button>
                    </div>

                    <div class="text-xs text-[#8a8a96]">Narration</div>
                    <div class="relative h-8">
                        @foreach ($narration as $cue)
                            <div style="left: {{ $total > 0 ? $cue['start'] / $total * 100 : 0 }}%; width: {{ $total > 0 ? $cue['duration'] / $total * 100 : 0 }}%;" class="absolute inset-y-0 px-0.5">
                                <div class="flex h-full items-center truncate rounded-lg bg-[#163a2c] px-2 text-xs text-[#5ee0a0]" title="{{ $cue['text'] }}">VO · {{ $cue['voice'] }}</div>
                            </div>
                        @endforeach
                    </div>

                    <div class="text-xs text-[#8a8a96]">Plaque</div>
                    <div class="relative h-8">
                        @foreach ($plaques as $cue)
                            <div style="left: {{ $total > 0 ? $cue['start'] / $total * 100 : 0 }}%; width: {{ $total > 0 ? $cue['duration'] / $total * 100 : 0 }}%;" class="absolute inset-y-0 px-0.5">
                                <div class="flex h-full items-center truncate rounded-lg bg-[#3a3216] px-2 text-[11px] text-[#e0c25e]" title="{{ $cue['text'] }}">"{{ $cue['text'] }}"</div>
                            </div>
                        @endforeach
                    </div>

                    <div class="text-xs text-[#8a8a96]">Shorts</div>
                    <div class="relative h-8">
                        @foreach ($shorts as $short)
                            <div style="left: {{ $total > 0 ? $short['start'] / $total * 100 : 0 }}%; width: {{ $total > 0 ? $short['duration'] / $total * 100 : 0 }}%;" class="absolute inset-y-0 px-0.5">
                                <div @class([
                                    'flex h-full items-center truncate rounded-lg px-2 text-xs text-[#b5b5c0]',
                                    'border border-[#7c5cff] bg-[#2d2e38]' => $short['active'],
                                    'bg-[#22232b]' => ! $short['active'],
                                ]) title="{{ $short['stamp'] }}">{{ $short['label'] }}</div>
                            </div>
                        @endforeach
                    </div>
                </div>
            </section>
        </div>

        @if ($showExport)
            <div class="fixed inset-0 z-40 grid place-items-center bg-black/60 p-6" wire:click.self="$set('showExport', false)">
                <div class="max-h-[80vh] w-full max-w-lg overflow-auto rounded-[14px] bg-[#16171d] p-6 shadow-xl">
                    <div class="flex items-center justify-between">
                        <h2 class="text-lg font-semibold">Export</h2>
                        <button type="button" wire:click="$set('showExport', false)" class="text-[#8a8a96]">Close</button>
                    </div>
                    <p class="mt-1 text-xs text-[#6c6c78]">Episode is 16:9, 3–4 minutes. Shorts are 9:16, 45–60 seconds, cut on shot boundaries. Narration is a subtitle track. No voiceover audio in v0.</p>
                    @if ($notice)
                        <p class="mt-3 rounded-lg bg-[#3a1630] px-3 py-2 text-xs text-[#ff7ab8]">{{ $notice }}</p>
                    @endif
                    <div class="mt-4 rounded-lg bg-[#22232b] p-4">
                        <div class="text-sm font-semibold">Episode · 16:9 · {{ \App\Video\HouseStandard::clock($total) }}</div>
                        @if ($episodeWarning)
                            <p class="mt-1 text-xs text-[#e0c25e]">{{ $episodeWarning }}</p>
                        @endif
                        <button type="button" wire:click="queueEpisode" class="mt-3 h-9 rounded-lg bg-gradient-to-r from-[#7c5cff] to-[#ff5c8a] px-4 text-sm font-semibold text-white">Queue episode export</button>
                    </div>
                    <div class="mt-3 rounded-lg bg-[#22232b] p-4">
                        <div class="text-sm font-semibold">Shorts · 9:16 · {{ count($shorts) }}</div>
                        <ul class="mt-2 space-y-1 text-xs text-[#b5b5c0]">
                            @foreach ($shorts as $short)
                                <li>{{ $short['stamp'] }} · {{ round($short['duration']) }}s</li>
                                @if ($short['warning'])
                                    <li class="text-[#e0c25e]">{{ $short['warning'] }}</li>
                                @endif
                            @endforeach
                        </ul>
                        <button type="button" wire:click="queueShorts" class="mt-3 h-9 rounded-lg bg-[#2a2450] px-4 text-sm font-semibold text-[#d7ccff]">Queue shorts export</button>
                    </div>
                    <p class="mt-3 text-[11px] text-[#6c6c78]">Jobs use the database queue. Keep <code>php artisan queue:work</code> running, or use <code>composer dev</code> / <code>php artisan native:run</code>.</p>
                    <ul class="mt-3 space-y-2 text-xs">
                        @foreach ($exports as $export)
                            <li class="rounded-lg bg-[#0f1014] px-3 py-2">
                                <div class="flex items-center justify-between">
                                    <span>{{ $export->kind->value }} · {{ $export->status->value }}</span>
                                    @if ($export->url())
                                        <a href="{{ $export->url() }}" class="text-[#a993ff]">Open</a>
                                    @endif
                                </div>
                                @foreach ($export->warnings ?? [] as $warning)
                                    <div class="mt-1 text-[#e0c25e]">{{ $warning }}</div>
                                @endforeach
                                @if ($export->error)
                                    <div class="mt-1 text-[#ff7ab8]">{{ $export->error }}</div>
                                @endif
                                @foreach ($export->meta['files'] ?? [] as $file)
                                    <div class="mt-1"><a class="text-[#a993ff]" href="{{ \Illuminate\Support\Facades\Storage::disk('public')->url($file['path']) }}">{{ $file['stamp'] }}</a></div>
                                @endforeach
                            </li>
                        @endforeach
                    </ul>
                </div>
            </div>
        @endif
    @endif
</div>
