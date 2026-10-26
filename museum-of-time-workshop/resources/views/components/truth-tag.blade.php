@props(['tag'])
@php
    $value = $tag instanceof \App\Enums\TruthTag ? $tag->value : (string) $tag;
    $styles = [
        'documented' => 'bg-[#163a2c] text-[#5ee0a0]',
        'legend' => 'bg-[#3a3216] text-[#e0c25e]',
        'invented' => 'bg-[#3a1630] text-[#ff7ab8]',
    ];
@endphp
<span {{ $attributes->merge(['class' => 'inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-medium '.($styles[$value] ?? 'bg-[#22232b] text-[#b5b5c0]')]) }}>{{ $value }}</span>
