<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('scene_pack_submissions', function (Blueprint $table) {
            $table->id();
            $table->string('fingerprint')->unique();
            $table->string('filename');
            $table->string('stored_path');
            $table->string('status');
            $table->text('error')->nullable();
            $table->json('summary')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('scene_pack_submissions');
    }
};
