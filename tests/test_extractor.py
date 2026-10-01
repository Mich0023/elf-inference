"""Pruebas con binarios reales: necesitan gcc, strip y radare2 (vienen en la imagen Docker)."""
import shutil
import subprocess
from pathlib import Path

import pytest

from elfinfer.extractor import emparejar_con_ground_truth, extraer_funciones

pytestmark = pytest.mark.skipif(
    not all(shutil.which(c) for c in ("gcc", "strip")) or not (shutil.which("radare2") or shutil.which("r2")),
    reason="requiere gcc, strip y radare2")

SAMPLES = Path(__file__).resolve().parent.parent / "samples"


def _compilar(tmp_path, pie: bool):
    ref = tmp_path / "checksum_O0_nonstripped"
    flags = [] if pie else ["-fno-pie", "-no-pie"]
    subprocess.run(["gcc", "-g", "-O0", *flags, "-o", str(ref), str(SAMPLES / "checksum.c")], check=True)
    stripped = tmp_path / "checksum_O0_stripped"
    shutil.copy(ref, stripped)
    subprocess.run(["strip", "--strip-all", str(stripped)], check=True)
    return stripped, ref


@pytest.mark.parametrize("pie", [True, False])
def test_ground_truth_y_arranque(tmp_path, pie):
    stripped, ref = _compilar(tmp_path, pie)
    fs = emparejar_con_ground_truth(extraer_funciones(stripped), extraer_funciones(ref))
    nombres = {f.nombre_original for f in fs if f.nombre_original}
    assert {"crc32_compute", "adler32_checksum", "fnv1a_hash", "xor_checksum", "fletcher16"} <= nombres
    # main la reconoce Radare2 y no se evalúa
    assert [f.nombre_r2 for f in fs if f.nombre_r2] == ["main"]
    assert "main" not in nombres
    # el código de arranque (entry0, entry.init0, entry.fini0) no se extrae
    assert all(f.tamano_bytes > 0 for f in fs)
    assert len(fs) <= 7
