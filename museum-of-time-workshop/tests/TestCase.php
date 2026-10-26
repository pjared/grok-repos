<?php

namespace Tests;

use App\Video\Drawtext;
use App\Workshop\SceneInbox;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;

abstract class TestCase extends BaseTestCase
{
    protected function setUp(): void
    {
        parent::setUp();

        $this->withoutVite();
        Drawtext::useDirectory(null);
        SceneInbox::forgetScanCache();
    }
}
