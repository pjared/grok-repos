<?php

namespace App\Video;

class ExportResult
{
    /**
     * @param  list<string>  $warnings
     * @param  list<array{path: string, stamp: ?string, duration: float, number: int, total: int}>  $files
     */
    public function __construct(
        public ?string $path,
        public array $warnings = [],
        public array $files = [],
        public float $duration = 0,
    ) {}
}
