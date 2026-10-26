<?php

namespace App\Enums;

enum ExportStatus: string
{
    case Queued = 'queued';
    case Running = 'running';
    case Ready = 'ready';
    case Failed = 'failed';
}
