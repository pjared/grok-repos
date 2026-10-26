<?php

use App\Sections\Exhibits\Livewire\Index;
use Illuminate\Support\Facades\Route;

Route::get('/exhibits', Index::class)->name('exhibits.index');
