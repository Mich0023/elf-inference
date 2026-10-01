"""
prompt_builder.py — Fase 3: construcción de prompts.

Tres estrategias:
  - zero-shot:        solo el Assembly de la función objetivo.
  - few-shot:         3 ejemplos etiquetados elegidos dinámicamente
                      (tamaño parecido + mnemónicos parecidos).
  - chain-of-thought: el modelo razona paso a paso antes de dar el nombre.

Todas piden la respuesta final en la forma  NAME: <snake_case>
para poder parsearla de forma fiable.
"""
from __future__ import annotations

from .extractor import Funcion

ESTRATEGIAS = ("zero-shot", "few-shot", "cot")

SISTEMA = (
    "You are an expert reverse engineer specialized in x86-64 binaries "
    "compiled from C. You receive the disassembly of ONE function from a "
    "stripped ELF binary and you must propose the most likely original "
    "function name, in snake_case, as a C programmer would have written it."
)

FORMATO = "Answer with a single final line exactly in this form:\nNAME: <function_name>"

MAX_LINEAS_EJEMPLO = 60   # recorta ejemplos largos para no reventar el contexto


def _asm(f: Funcion, max_lineas: int | None = None) -> str:
    lineas = f.assembly if max_lineas is None else f.assembly[:max_lineas]
    texto = "\n".join(lineas)
    if max_lineas is not None and len(f.assembly) > max_lineas:
        texto += "\n; ... (truncated)"
    return texto


def _mnemonicos(f: Funcion) -> set[str]:
    return {linea.split()[0] for linea in f.assembly if linea.split()}


def seleccionar_ejemplos(objetivo: Funcion, pool: list[Funcion], k: int = 3) -> list[Funcion]:
    """
    Few-shot dinámico: elige k funciones con nombre conocido que más se
    parecen a la objetivo (Jaccard de mnemónicos + cercanía en nº de instrucciones).
    Nunca usa la propia función objetivo como ejemplo.
    """
    m_obj = _mnemonicos(objetivo)
    candidatos = []
    for f in pool:
        if not f.nombre_original:
            continue
        if f.nombre_original == objetivo.nombre_original:
            continue  # evita "chivatearle" la respuesta al modelo
        m = _mnemonicos(f)
        jaccard = len(m_obj & m) / max(1, len(m_obj | m))
        tam = 1 - abs(f.num_instrucciones - objetivo.num_instrucciones) / max(
            f.num_instrucciones, objetivo.num_instrucciones, 1)
        candidatos.append((0.6 * jaccard + 0.4 * tam, f))
    candidatos.sort(key=lambda t: t[0], reverse=True)
    return [f for _, f in candidatos[:k]]


def construir_prompt(objetivo: Funcion, estrategia: str,
                     pool: list[Funcion] | None = None) -> list[dict]:
    """Devuelve la lista de mensajes (formato chat) para Ollama."""
    if estrategia not in ESTRATEGIAS:
        raise ValueError(f"Estrategia desconocida: {estrategia}. Usa {ESTRATEGIAS}")

    asm = _asm(objetivo)

    if estrategia == "zero-shot":
        usuario = f"Disassembly:\n```asm\n{asm}\n```\n\n{FORMATO}"

    elif estrategia == "few-shot":
        ejemplos = seleccionar_ejemplos(objetivo, pool or [])
        bloques = []
        for i, e in enumerate(ejemplos, 1):
            bloques.append(
                f"### Example {i}\n```asm\n{_asm(e, MAX_LINEAS_EJEMPLO)}\n```\n"
                f"NAME: {e.nombre_original}"
            )
        usuario = (
            "Here are labeled examples of functions and their real names:\n\n"
            + "\n\n".join(bloques)
            + f"\n\n### Target function\n```asm\n{asm}\n```\n\n{FORMATO}"
        )

    else:  # cot
        usuario = (
            f"Disassembly:\n```asm\n{asm}\n```\n\n"
            "Think step by step before answering:\n"
            "1. Describe the main operations the function performs "
            "(loops, comparisons, calls, memory accesses).\n"
            "2. Infer the probable arguments and the return type.\n"
            "3. Propose a descriptive name that summarizes that behaviour.\n\n"
            f"{FORMATO}"
        )

    return [
        {"role": "system", "content": SISTEMA},
        {"role": "user", "content": usuario},
    ]
