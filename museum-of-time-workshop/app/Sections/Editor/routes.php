<?php

use App\Sections\Editor\Livewire\Workshop;
use Illuminate\Support\Facades\Route;

Route::get('/', Workshop::class)->name('editor.index');
