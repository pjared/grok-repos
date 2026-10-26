<?php

use App\Sections\Assets\Livewire\Index;
use Illuminate\Support\Facades\Route;

Route::get('/assets', Index::class)->name('assets.index');
