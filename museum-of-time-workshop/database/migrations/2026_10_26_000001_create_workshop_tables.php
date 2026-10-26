<?php

use Illuminate\Database\Migrations\Migration;
use Illuminate\Database\Schema\Blueprint;
use Illuminate\Support\Facades\Schema;

return new class extends Migration
{
    public function up(): void
    {
        Schema::create('wings', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->string('slug')->unique();
            $table->timestamps();
        });

        Schema::create('halls', function (Blueprint $table) {
            $table->id();
            $table->foreignId('wing_id')->constrained()->cascadeOnDelete();
            $table->string('name');
            $table->string('slug');
            $table->timestamps();

            $table->unique(['wing_id', 'slug']);
        });

        Schema::create('exhibits', function (Blueprint $table) {
            $table->id();
            $table->foreignId('hall_id')->constrained()->cascadeOnDelete();
            $table->string('name');
            $table->string('slug');
            $table->string('truth_tag');
            $table->timestamps();

            $table->unique(['hall_id', 'slug']);
        });

        Schema::create('characters', function (Blueprint $table) {
            $table->id();
            $table->string('name');
            $table->boolean('locked')->default(false);
            $table->string('reference_image')->nullable();
            $table->timestamps();
        });

        Schema::create('assets', function (Blueprint $table) {
            $table->id();
            $table->foreignId('exhibit_id')->nullable()->constrained()->nullOnDelete();
            $table->string('name');
            $table->string('path');
            $table->string('kind')->default('image');
            $table->string('truth_tag');
            $table->timestamps();
        });

        Schema::create('sequences', function (Blueprint $table) {
            $table->id();
            $table->foreignId('exhibit_id')->constrained()->cascadeOnDelete();
            $table->string('title');
            $table->timestamps();
        });

        Schema::create('shots', function (Blueprint $table) {
            $table->id();
            $table->foreignId('sequence_id')->constrained()->cascadeOnDelete();
            $table->unsignedInteger('order');
            $table->string('title');
            $table->string('frame_path')->nullable();
            $table->text('prompt')->nullable();
            $table->string('model')->default('FLUX');
            $table->decimal('duration_s', 8, 3)->default(4);
            $table->string('truth_tag');
            $table->string('clip_path')->nullable();
            $table->string('status')->default('draft');
            $table->timestamps();

            $table->index(['sequence_id', 'order']);
        });

        Schema::create('shot_versions', function (Blueprint $table) {
            $table->id();
            $table->foreignId('shot_id')->constrained()->cascadeOnDelete();
            $table->string('frame_path')->nullable();
            $table->text('prompt')->nullable();
            $table->string('model')->nullable();
            $table->decimal('duration_s', 8, 3)->nullable();
            $table->string('truth_tag')->nullable();
            $table->string('clip_path')->nullable();
            $table->timestamps();
        });

        Schema::create('shot_character', function (Blueprint $table) {
            $table->foreignId('shot_id')->constrained()->cascadeOnDelete();
            $table->foreignId('character_id')->constrained()->cascadeOnDelete();
            $table->string('reference_image')->nullable();

            $table->primary(['shot_id', 'character_id']);
        });

        Schema::create('text_cues', function (Blueprint $table) {
            $table->id();
            $table->foreignId('shot_id')->constrained()->cascadeOnDelete();
            $table->string('type');
            $table->decimal('offset_s', 8, 3)->default(0);
            $table->text('text');
            $table->string('voice')->nullable();
            $table->timestamps();
        });

        Schema::create('exports', function (Blueprint $table) {
            $table->id();
            $table->foreignId('sequence_id')->constrained()->cascadeOnDelete();
            $table->string('kind');
            $table->string('status')->default('queued');
            $table->string('path')->nullable();
            $table->json('warnings')->nullable();
            $table->json('meta')->nullable();
            $table->text('error')->nullable();
            $table->timestamps();
        });
    }

    public function down(): void
    {
        Schema::dropIfExists('exports');
        Schema::dropIfExists('text_cues');
        Schema::dropIfExists('shot_character');
        Schema::dropIfExists('shot_versions');
        Schema::dropIfExists('shots');
        Schema::dropIfExists('sequences');
        Schema::dropIfExists('assets');
        Schema::dropIfExists('characters');
        Schema::dropIfExists('exhibits');
        Schema::dropIfExists('halls');
        Schema::dropIfExists('wings');
    }
};
