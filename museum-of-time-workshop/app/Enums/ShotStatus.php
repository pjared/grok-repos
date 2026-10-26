<?php

namespace App\Enums;

enum ShotStatus: string
{
    case Draft = 'draft';
    case Queued = 'queued';
    case Rendering = 'rendering';
    case Ready = 'ready';
    case Failed = 'failed';
}
