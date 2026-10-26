<?php

namespace App\Enums;

enum ScenePackStatus: string
{
    case Pending = 'pending';
    case Approved = 'approved';
    case Rejected = 'rejected';
    case Invalid = 'invalid';
}
