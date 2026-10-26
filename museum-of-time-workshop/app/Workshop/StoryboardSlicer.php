<?php

namespace App\Workshop;

/**
 * Cuts a 3x2 storyboard sheet into six panels, dropping the white gutters
 * and the caption band under each drawing.
 */
class StoryboardSlicer
{
    /**
     * @return list<string> Absolute paths of the six panel JPEGs, left to right, top to bottom.
     */
    public function slice(string $source): array
    {
        if (! function_exists('imagecreatefromjpeg')) {
            throw new \RuntimeException('The GD extension is required to slice storyboards.');
        }

        $image = @imagecreatefromjpeg($source);
        if ($image === false) {
            throw new \RuntimeException("Could not read storyboard [{$source}].");
        }

        $width = imagesx($image);
        $height = imagesy($image);
        $rows = $this->spans($this->gutterFlags($image, 'row', $width, $height));
        $cols = $this->spans($this->gutterFlags($image, 'column', $width, $height));

        if (count($rows) !== 2 || count($cols) !== 3) {
            $rows = [[0, intdiv($height, 2) - 1], [intdiv($height, 2), $height - 1]];
            $third = intdiv($width, 3);
            $cols = [[0, $third - 1], [$third, ($third * 2) - 1], [$third * 2, $width - 1]];
        }

        $directory = sys_get_temp_dir().'/mot-storyboard-slices';
        if (! is_dir($directory) && ! mkdir($directory, 0775, true) && ! is_dir($directory)) {
            throw new \RuntimeException("Could not create [{$directory}].");
        }

        $paths = [];
        $index = 1;

        foreach ($rows as [$y0, $y1]) {
            foreach ($cols as [$x0, $x1]) {
                [$x0, $y0c, $x1, $y1c] = $this->trim($image, $x0, $y0, $x1, $y1);
                $panelWidth = max(1, $x1 - $x0 + 1);
                $panelHeight = max(1, $y1c - $y0c + 1);
                $panel = imagecreatetruecolor($panelWidth, $panelHeight);
                imagecopy($panel, $image, 0, 0, $x0, $y0c, $panelWidth, $panelHeight);
                $path = $directory.'/panel-'.$index.'.jpg';
                imagejpeg($panel, $path, 85);
                imagedestroy($panel);
                $paths[] = $path;
                $index++;
            }
        }

        imagedestroy($image);

        return $paths;
    }

    /**
     * @return list<bool>
     */
    private function gutterFlags(\GdImage $image, string $axis, int $width, int $height): array
    {
        $flags = [];
        $length = $axis === 'row' ? $height : $width;

        for ($i = 0; $i < $length; $i++) {
            $flags[] = $this->mean($image, $axis, $i, $width, $height) > 248;
        }

        return $flags;
    }

    private function mean(\GdImage $image, string $axis, int $index, int $width, int $height): float
    {
        $sum = 0.0;
        $count = 0;

        if ($axis === 'row') {
            for ($x = 0; $x < $width; $x += 2) {
                $sum += $this->brightness($image, $x, $index);
                $count++;
            }
        } else {
            for ($y = 0; $y < $height; $y += 2) {
                $sum += $this->brightness($image, $index, $y);
                $count++;
            }
        }

        return $count === 0 ? 0 : $sum / $count;
    }

    private function brightness(\GdImage $image, int $x, int $y): float
    {
        $rgb = imagecolorat($image, $x, $y);

        return ((($rgb >> 16) & 0xFF) + (($rgb >> 8) & 0xFF) + ($rgb & 0xFF)) / 3;
    }

    /**
     * @param  list<bool>  $white
     * @return list<array{0: int, 1: int}>
     */
    private function spans(array $white, int $minimum = 30): array
    {
        $spans = [];
        $start = null;

        foreach ($white as $index => $isWhite) {
            if (! $isWhite && $start === null) {
                $start = $index;
            }

            if ($isWhite && $start !== null) {
                if ($index - $start >= $minimum) {
                    $spans[] = [$start, $index - 1];
                }
                $start = null;
            }
        }

        if ($start !== null && count($white) - $start >= $minimum) {
            $spans[] = [$start, count($white) - 1];
        }

        return $spans;
    }

    /**
     * @return array{0: int, 1: int, 2: int, 3: int}
     */
    private function trim(\GdImage $image, int $x0, int $y0, int $x1, int $y1): array
    {
        $width = imagesx($image);
        $height = imagesy($image);

        while ($y0 < $y1 && $this->edgeMean($image, 'row', $y0, $x0, $x1, $width, $height) > 242) {
            $y0++;
        }
        while ($y1 > $y0 && $this->edgeMean($image, 'row', $y1, $x0, $x1, $width, $height) > 242) {
            $y1--;
        }
        while ($x0 < $x1 && $this->edgeMean($image, 'column', $x0, $y0, $y1, $width, $height) > 242) {
            $x0++;
        }
        while ($x1 > $x0 && $this->edgeMean($image, 'column', $x1, $y0, $y1, $width, $height) > 242) {
            $x1--;
        }

        return [$x0, $y0, $x1, $y1];
    }

    private function edgeMean(\GdImage $image, string $axis, int $index, int $from, int $to, int $width, int $height): float
    {
        $sum = 0.0;
        $count = 0;

        if ($axis === 'row') {
            for ($x = $from; $x <= $to; $x += 2) {
                $sum += $this->brightness($image, min($x, $width - 1), min($index, $height - 1));
                $count++;
            }
        } else {
            for ($y = $from; $y <= $to; $y += 2) {
                $sum += $this->brightness($image, min($index, $width - 1), min($y, $height - 1));
                $count++;
            }
        }

        return $count === 0 ? 0 : $sum / $count;
    }
}
