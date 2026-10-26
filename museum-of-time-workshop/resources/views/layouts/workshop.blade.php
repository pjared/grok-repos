<!DOCTYPE html>
<html lang="en" class="h-full">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>{{ config('app.name', 'Museum of Time Workshop') }}</title>
    <link rel="preconnect" href="https://fonts.bunny.net">
    <link href="https://fonts.bunny.net/css?family=inter:400,500,600,700" rel="stylesheet">
    @vite(['resources/css/app.css', 'resources/js/app.js'])
    @livewireStyles
</head>
<body class="h-full overflow-hidden bg-[#0f1014] font-sans text-[#e6e6ea] antialiased" x-data x-on:keydown.window.meta.k.prevent="document.getElementById('workshop-search')?.focus()" x-on:keydown.window.ctrl.k.prevent="document.getElementById('workshop-search')?.focus()">
    @php($sections = app(\App\Sections\SectionRegistry::class)->all())
    <div class="flex h-full flex-col">
        <header class="flex h-[52px] shrink-0 items-center gap-3 border-b border-white/5 bg-[#16171d] px-4">
            <a href="{{ route('editor.index') }}" class="flex shrink-0 items-center gap-2">
                <span class="h-5 w-5 rounded-full bg-gradient-to-br from-[#7c5cff] to-[#ff5c8a]"></span>
                <span class="text-[15px] font-semibold">Workshop</span>
            </a>
            <div class="ml-2 flex h-6 min-w-[220px] items-center rounded-full bg-[#22232b] px-3 text-sm text-[#9a9aa6]">
                {{ $breadcrumb ?? 'Museum of Time' }}
            </div>
            <div class="flex flex-1 justify-center">
                {{ $search ?? '' }}
            </div>
            <div class="flex items-center gap-3">
                <span class="flex -space-x-1.5" aria-hidden="true">
                    <span class="h-6 w-6 rounded-full bg-[#3a3b46] ring-2 ring-[#16171d]"></span>
                    <span class="h-6 w-6 rounded-full bg-[#5a4bb5] ring-2 ring-[#16171d]"></span>
                    <span class="h-6 w-6 rounded-full bg-[#b54b6e] ring-2 ring-[#16171d]"></span>
                </span>
                {{ $actions ?? '' }}
            </div>
        </header>
        <div class="flex min-h-0 flex-1">
            <nav class="flex w-16 shrink-0 flex-col items-center gap-3 bg-[#16171d] py-4" aria-label="Sections">
                @foreach ($sections as $section)
                    <a
                        href="{{ route($section['route']) }}"
                        title="{{ $section['label'] }}"
                        @class([
                            'grid h-9 w-9 place-items-center rounded-md',
                            'bg-[#5a4bb5] text-white' => request()->routeIs($section['route']),
                            'bg-[#2d2e38] text-[#9a9aa6] hover:text-white' => ! request()->routeIs($section['route']),
                        ])
                    >
                        <x-icon :name="$section['icon']" />
                        <span class="sr-only">{{ $section['label'] }}</span>
                    </a>
                @endforeach
            </nav>
            <main class="min-w-0 flex-1">
                {{ $slot }}
            </main>
        </div>
    </div>
    @livewireScripts
</body>
</html>
