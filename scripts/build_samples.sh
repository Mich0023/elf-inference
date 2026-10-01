#!/usr/bin/env bash
# Compila cada samples/*.c (o la carpeta que pases) en O0, O1 y O2,
# y genera su versión stripped. Salida: data/binaries/<proyecto>_O<n>[.stripped]
#
#   ./scripts/build_samples.sh            # usa samples/
#   ./scripts/build_samples.sh mis_fuentes/
set -euo pipefail

SRC_DIR="${1:-samples}"
OUT_DIR="${OUT_DIR:-data/binaries}"
mkdir -p "$OUT_DIR"

shopt -s nullglob
fuentes=("$SRC_DIR"/*.c)
if [ ${#fuentes[@]} -eq 0 ]; then
  echo "No hay archivos .c en $SRC_DIR" >&2; exit 1
fi

for src in "${fuentes[@]}"; do
  name="$(basename "$src" .c)"
  for opt in 0 1 2; do
    out="$OUT_DIR/${name}_O${opt}"
    gcc -g -O"$opt" -fno-pie -no-pie -o "$out" "$src"
    cp "$out" "$out.stripped"
    strip --strip-all "$out.stripped"
    echo "  $out  +  $out.stripped"
  done
done
echo "[+] Binarios listos en $OUT_DIR"
