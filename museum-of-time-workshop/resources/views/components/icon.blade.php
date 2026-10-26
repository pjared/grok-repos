@props(['name'])
@php
    $common = 'w-4 h-4';
@endphp
@if ($name === 'editor')
    <svg {{ $attributes->merge(['class' => $common]) }} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <rect x="3" y="7" width="18" height="12" rx="2"/>
        <path d="M8 7V5h8v2M10 12h4"/>
    </svg>
@elseif ($name === 'exhibits')
    <svg {{ $attributes->merge(['class' => $common]) }} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <rect x="3" y="4" width="7" height="7" rx="1"/>
        <rect x="14" y="4" width="7" height="7" rx="1"/>
        <rect x="3" y="14" width="7" height="6" rx="1"/>
        <rect x="14" y="14" width="7" height="6" rx="1"/>
    </svg>
@elseif ($name === 'wings')
    <svg {{ $attributes->merge(['class' => $common]) }} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <path d="M4 20V9l8-5 8 5v11"/>
        <path d="M9 20v-6h6v6"/>
    </svg>
@else
    <svg {{ $attributes->merge(['class' => $common]) }} viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8">
        <rect x="3" y="5" width="18" height="14" rx="2"/>
        <path d="M8 13l2.5-2.5L14 14l2-2 3 3"/>
        <circle cx="9" cy="9" r="1"/>
    </svg>
@endif
