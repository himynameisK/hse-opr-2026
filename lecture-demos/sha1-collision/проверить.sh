#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
echo "1. SHA-1 обоих файлов:";      shasum -a 1 shattered-1.pdf shattered-2.pdf | sed 's/^/   /'
echo; echo "2. Файлы различаются:"; cmp shattered-1.pdf shattered-2.pdf || true
echo "   SHA-256:";                 shasum -a 256 shattered-1.pdf shattered-2.pdf | sed 's/^/   /'
T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
echo; echo "3. Дописали одинаковый хвост — коллизия сохранилась:"
for f in 1 2; do cat shattered-$f.pdf > "$T/app-$f"; printf 'ХВОСТ' >> "$T/app-$f"; done
shasum -a 1 "$T"/app-* | sed "s|$T/|   |"
echo; echo "4. Дописали один байт в начало — коллизия исчезла:"
for f in 1 2; do { printf 'X'; cat shattered-$f.pdf; } > "$T/pre-$f"; done
shasum -a 1 "$T"/pre-* | sed "s|$T/|   |"
echo; echo "5. Git как блобы (заголовок «blob 422435\\0» ломает атаку):"
git hash-object shattered-1.pdf shattered-2.pdf | sed 's/^/   /'
