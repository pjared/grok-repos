<?php

namespace App\Sections;

class SectionRegistry
{
    /**
     * @return list<array{key: string, label: string, module: string, route: string, icon: string, placeholder: bool, component: class-string}>
     */
    public function all(): array
    {
        return array_values(config('sections', []));
    }

    public function get(string $key): array
    {
        foreach ($this->all() as $section) {
            if ($section['key'] === $key) {
                return $section;
            }
        }

        throw new \InvalidArgumentException("Unknown section [{$key}].");
    }

    /**
     * @return list<string>
     */
    public function keys(): array
    {
        return array_column($this->all(), 'key');
    }

    /**
     * @return list<array{key: string, label: string, module: string, route: string, icon: string, placeholder: bool, component: class-string}>
     */
    public function placeholders(): array
    {
        return array_values(array_filter(
            $this->all(),
            fn (array $section) => $section['placeholder'] === true,
        ));
    }

    public function routesPath(array $section): string
    {
        return app_path('Sections/'.$section['module'].'/routes.php');
    }
}
