"""
inference.py — Fase 4: consulta al modelo local vía Ollama y arma el report.json.

El report.json es la interfaz con la capa de reconstrucción. Cada entrada trae:
  direccion, tamano_bytes, nombre_inferido, confianza, estrategia, modelo
(+ campos de evaluación si hay ground truth).

Ollama corre en la máquina anfitriona (usa la GPU). Desde Docker se llega a él
con OLLAMA_HOST=http://host.docker.internal:11434.
"""
from __future__ import annotations

import os
import re
import time

import ollama

from . import metrics
from .extractor import Funcion
from .prompt_builder import construir_prompt

# 127.0.0.1 y no "localhost": en Windows "localhost" intenta primero IPv6 (::1),
# Ollama solo escucha en IPv4 y cada llamada pierde ~2 s esperando el fallback.
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
# OLLAMA_HOST=0.0.0.0 sirve para que el *servidor* escuche en todas las interfaces,
# pero como dirección de *cliente* no es válida: se traduce a 127.0.0.1.
if "0.0.0.0" in OLLAMA_HOST or "localhost" in OLLAMA_HOST:
    OLLAMA_HOST = OLLAMA_HOST.replace("0.0.0.0", "127.0.0.1").replace("localhost", "127.0.0.1")
if not OLLAMA_HOST.startswith("http"):
    OLLAMA_HOST = "http://" + OLLAMA_HOST
if OLLAMA_HOST.count(":") == 1:  # sin puerto
    OLLAMA_HOST += ":11434"

# temperatura baja = respuestas reproducibles (BinMetric usa 0.1)
# num_predict acota la respuesta (CoT necesita espacio para razonar)
OPCIONES = {"temperature": 0.1, "top_p": 1.0, "num_ctx": 4096, "num_predict": 512, "seed": 42}

# Acepta variantes que usa el modelo: "NAME: x", "**NAME:** x", "### NAME:\nx",
# "NAME: `x`" y hasta "### NAME:\nNAME: x" (por eso se descarta la palabra "name").
_RE_NAME = re.compile(r"NAME\s*:[\s*`#]*([A-Za-z_][A-Za-z0-9_]*)")
_RE_IDENT = re.compile(r"\b([a-z][a-z0-9]*(?:_[a-z0-9]+)+)\b")


def _cliente() -> ollama.Client:
    return ollama.Client(host=OLLAMA_HOST)


def parsear_nombre(respuesta: str) -> str | None:
    """Saca el nombre de la respuesta del modelo. Prefiere la línea NAME: final."""
    encontrados = [n for n in _RE_NAME.findall(respuesta) if n.lower() != "name"]
    if encontrados:
        return encontrados[-1].lower()
    # Plan B: último identificador snake_case que aparezca.
    ident = _RE_IDENT.findall(respuesta)
    return ident[-1] if ident else None


def confianza_sin_referencia(nombre: str | None) -> str:
    """
    Cuando no hay ground truth (binario real desconocido) no se puede usar F1.
    Heurística simple: nombre válido y descriptivo -> media; si no -> baja.
    """
    if not nombre:
        return "baja"
    tokens = metrics.tokenizar(nombre)
    genericos = {"func", "function", "sub", "fcn", "unknown", "helper", "main"}
    if len(tokens) >= 2 and not set(tokens) <= genericos:
        return "media"
    return "baja"


def verificar_ollama(modelo: str) -> None:
    try:
        modelos = {m.model for m in _cliente().list().models}
    except Exception as e:  # noqa: BLE001
        raise SystemExit(
            f"No pude conectar con Ollama en {OLLAMA_HOST}.\n"
            "  - ¿Está abierto Ollama en tu máquina?\n"
            "  - Desde Docker debe ser http://host.docker.internal:11434\n"
            f"  Detalle: {e}"
        ) from e
    if modelo not in modelos and f"{modelo}:latest" not in modelos:
        raise SystemExit(f"El modelo '{modelo}' no está descargado. Corre: ollama pull {modelo}")


def inferir_funcion(f: Funcion, modelo: str, estrategia: str,
                    pool: list[Funcion] | None = None) -> dict:
    mensajes = construir_prompt(f, estrategia, pool)
    t0 = time.perf_counter()
    resp = _cliente().chat(model=modelo, messages=mensajes, options=OPCIONES)
    segundos = time.perf_counter() - t0
    texto = resp.message.content or ""
    nombre = parsear_nombre(texto)

    fila = {
        "direccion": f.direccion,
        "tamano_bytes": f.tamano_bytes,
        "nombre_inferido": nombre,
        "estrategia": estrategia,
        "modelo": modelo,
        "segundos": round(segundos, 3),
        "binario": f.binario,
    }

    if f.nombre_original:  # modo evaluación
        f1 = metrics.f1_tokens(nombre, f.nombre_original)
        fila.update({
            "nombre_original": f.nombre_original,
            "em": metrics.exact_match(nombre, f.nombre_original),
            "f1": round(f1, 4),
            "bleu4": round(metrics.bleu4(nombre, f.nombre_original), 4),
            "confianza": metrics.nivel_confianza(f1),
        })
    else:
        fila["confianza"] = confianza_sin_referencia(nombre)

    fila["respuesta_cruda"] = texto[-1500:]  # para depurar prompts
    return fila
