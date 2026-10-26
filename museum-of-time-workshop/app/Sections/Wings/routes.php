<?php

use App\Sections\Wings\Livewire\Index;
use Illuminate\Support\Facades\Route;

Route::get('/wings', Index::class)->name('wings.index');
