"""
metrics.py — métricas de evaluación (Fase 4).

  - EM:      exactitud exacta (normalizada a minúsculas).
  - F1:      por sub-tokens (separados por '_' o por cambio de mayúscula).
  - BLEU-4:  sobre sub-tokens, con suavizado (los nombres son muy cortos).

Sin dependencias externas: así corre igual en Windows, Linux y Docker.
"""
from __future__ import annotations

import math
import re
from collections import Counter

_RE_CAMEL = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def tokenizar(nombre: str | None) -> list[str]:
    """'calculateCheck_sum2' -> ['calculate', 'check', 'sum2']"""
    if not nombre:
        return []
    nombre = _RE_CAMEL.sub("_", nombre)
    return [t for t in re.split(r"[_\W]+", nombre.lower()) if t]


def exact_match(pred: str | None, ref: str | None) -> float:
    if not pred or not ref:
        return 0.0
    return float(pred.strip().lower() == ref.strip().lower())


def f1_tokens(pred: str | None, ref: str | None) -> float:
    p, r = Counter(tokenizar(pred)), Counter(tokenizar(ref))
    comunes = sum((p & r).values())
    if comunes == 0:
        return 0.0
    precision = comunes / sum(p.values())
    recall = comunes / sum(r.values())
    return 2 * precision * recall / (precision + recall)


def bleu4(pred: str | None, ref: str | None) -> float:
    """BLEU-4 con suavizado add-one (método 1 de Chen & Cherry)."""
    p, r = tokenizar(pred), tokenizar(ref)
    if not p or not r:
        return 0.0
    log_precisiones = 0.0
    for n in range(1, 5):
        ng_p = Counter(tuple(p[i:i + n]) for i in range(len(p) - n + 1))
        ng_r = Counter(tuple(r[i:i + n]) for i in range(len(r) - n + 1))
        total = sum(ng_p.values())
        coincide = sum((ng_p & ng_r).values())
        precision = (coincide + 1) / (total + 1) if n > 1 else (coincide / total if total else 0)
        if precision == 0:
            return 0.0
        log_precisiones += math.log(precision) / 4
    bp = 1.0 if len(p) > len(r) else math.exp(1 - len(r) / len(p))
    return bp * math.exp(log_precisiones)


def nivel_confianza(f1: float) -> str:
    """Umbrales definidos en el anteproyecto."""
    if f1 > 0.75:
        return "alta"
    if f1 >= 0.40:
        return "media"
    return "baja"


def resumen(filas: list[dict]) -> dict:
    """Promedios por (modelo, estrategia) a partir de filas con em/f1/bleu4."""
    grupos: dict[tuple, list[dict]] = {}
    for fila in filas:
        if fila.get("f1") is None:
            continue
        grupos.setdefault((fila["modelo"], fila["estrategia"]), []).append(fila)
    salida = {}
    for (modelo, estrategia), g in sorted(grupos.items()):
        n = len(g)
        salida[f"{modelo} | {estrategia}"] = {
            "n": n,
            "EM": round(sum(x["em"] for x in g) / n, 4),
            "F1": round(sum(x["f1"] for x in g) / n, 4),
            "BLEU4": round(sum(x["bleu4"] for x in g) / n, 4),
            "seg_promedio": round(sum(x["segundos"] for x in g) / n, 2),
        }
    return salida
