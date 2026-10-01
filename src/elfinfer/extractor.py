"""
extractor.py — Fase 2: extracción de funciones con Radare2 (r2pipe).

Abre un binario ELF, ejecuta el análisis automático de funciones y devuelve,
por cada función, su dirección de inicio, tamaño en bytes, número de
instrucciones y su Assembly en texto plano.

Si el binario conserva símbolos (versión non-stripped), también devuelve el
nombre original de cada función: ese es el ground truth.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

import r2pipe

MIN_INSTRUCCIONES = 5       # descarta funciones triviales (anteproyecto, Fase 2)
MAX_INSTRUCCIONES = 400     # evita prompts gigantes en la laptop

# Funciones que mete el compilador/enlazador: no son código del programador.
FUNCIONES_COMPILADOR = {
    "_start", "_init", "_fini", "deregister_tm_clones", "register_tm_clones",
    "__do_global_dtors_aux", "frame_dummy", "__libc_csu_init", "__libc_csu_fini",
    "_dl_relocate_static_pie", "__x86.get_pc_thunk.bx",
}


# Nombres que Radare2 recupera aunque el binario esté stripped (por heurística),
# así que no sirven para evaluar al modelo: se excluyen del ground truth.
NO_EVALUAR = {"main"}


@dataclass
class Funcion:
    direccion: str                 # "0x1149"
    tamano_bytes: int
    num_instrucciones: int
    assembly: list[str] = field(default_factory=list)
    nombre_original: str | None = None   # solo si el binario tiene símbolos
    binario: str = ""
    # Nombre que Radare2 recupera aunque el binario esté stripped (p. ej. "main").
    # No se le pregunta al modelo ni se evalúa; se reporta tal cual.
    nombre_r2: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _limpiar_nombre_r2(nombre: str) -> str | None:
    """'sym.calculate_checksum' -> 'calculate_checksum'. None si es sintético o import."""
    if not nombre or nombre.startswith(("fcn.", "sym.imp.", "sub.", "loc.", "entry")):
        return None
    for prefijo in ("sym.", "dbg."):
        if nombre.startswith(prefijo):
            nombre = nombre[len(prefijo):]
    return nombre or None


_RE_HEX = re.compile(r"0x[0-9a-fA-F]{4,}")


def _normalizar_instruccion(op: dict) -> str | None:
    """Toma una instrucción de pdfj y la deja limpia para el prompt."""
    texto = op.get("disasm") or op.get("opcode")
    if not texto or op.get("type") == "invalid":
        return None
    # Direcciones absolutas cambian de binario a binario: las abreviamos.
    return _RE_HEX.sub("ADDR", texto)


def extraer_funciones(ruta_binario: str | Path,
                      min_ins: int = MIN_INSTRUCCIONES,
                      max_ins: int = MAX_INSTRUCCIONES) -> list[Funcion]:
    ruta = str(ruta_binario)
    r2 = r2pipe.open(ruta, flags=["-2", "-e", "bin.relocs.apply=true"])
    try:
        r2.cmd("e scr.color=0")
        r2.cmd("e asm.bytes=false")
        r2.cmd("aaa")
        crudas = json.loads(r2.cmd("aflj") or "[]")

        funciones: list[Funcion] = []
        for f in crudas:
            nombre_r2 = f.get("name", "")
            if nombre_r2.startswith("sym.imp."):
                continue  # funciones importadas (printf, malloc...): no tienen código aquí
            if nombre_r2.startswith("entry"):
                continue  # arranque del programa (_start, init/fini): lo agrega el compilador
            n_ins = int(f.get("ninstrs") or f.get("ninstr") or 0)
            if n_ins < min_ins or n_ins > max_ins:
                continue
            nombre = _limpiar_nombre_r2(nombre_r2)
            if nombre in FUNCIONES_COMPILADOR:
                continue

            addr = int(f.get("addr", f.get("offset", 0)))
            pdf = json.loads(r2.cmd(f"pdfj @ {addr}") or "{}")
            ops = [_normalizar_instruccion(op) for op in pdf.get("ops", [])]
            ops = [o for o in ops if o]

            conocido = nombre if nombre in NO_EVALUAR else None
            funciones.append(Funcion(
                direccion=hex(addr),
                tamano_bytes=int(f.get("realsz") or f.get("size") or 0),
                num_instrucciones=n_ins,
                assembly=ops,
                nombre_original=None if conocido else nombre,
                binario=Path(ruta).name,
                nombre_r2=conocido,
            ))
        return funciones
    finally:
        r2.quit()


def emparejar_con_ground_truth(stripped: list[Funcion],
                               con_simbolos: list[Funcion]) -> list[Funcion]:
    """
    `strip` no mueve el código, así que la misma función tiene la misma
    dirección en ambas versiones. Usamos eso para pegar el nombre real.
    """
    nombres = {f.direccion: f.nombre_original for f in con_simbolos if f.nombre_original}
    for f in stripped:
        f.nombre_original = nombres.get(f.direccion)
    return stripped


def guardar_json(funciones: list[Funcion], salida: str | Path) -> None:
    salida = Path(salida)
    salida.parent.mkdir(parents=True, exist_ok=True)
    salida.write_text(
        json.dumps([f.to_dict() for f in funciones], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def cargar_json(ruta: str | Path) -> list[Funcion]:
    datos = json.loads(Path(ruta).read_text(encoding="utf-8"))
    return [Funcion(**d) for d in datos]
