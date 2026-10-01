"""
cli.py — punto de entrada del motor de inferencia.

Comandos:
  check          verifica Radare2 y Ollama
  extract        extrae funciones de un binario a JSON
  build-dataset  junta todos los pares stripped/non-stripped en un dataset
  prompt         muestra el prompt que se mandaría (no necesita Ollama)
  infer          corre la inferencia y genera report.json
  evaluate       resume EM / F1 / BLEU-4 de un report.json
  bench          mide tiempos de extracción (Windows vs Linux vs Docker)
"""
from __future__ import annotations

import csv
import json
import platform
import random
import re
import shutil
import statistics
import subprocess
import time
from pathlib import Path

import click

from . import metrics
from .extractor import cargar_json, emparejar_con_ground_truth, extraer_funciones, guardar_json
from .prompt_builder import ESTRATEGIAS, construir_prompt


def _proyecto(binario: str) -> str:
    """'tinyexpr_O1.stripped' o 'tinyexpr_O1_stripped' -> 'tinyexpr'"""
    return binario.split("_O")[0]


@click.group()
def cli():
    """Motor de inferencia de nombres de funciones en binarios ELF stripped."""


# --------------------------------------------------------------------- check
@cli.command()
@click.option("--modelo", default="qwen2.5-coder:7b", show_default=True)
def check(modelo):
    """Verifica que Radare2 y Ollama respondan."""
    r2 = shutil.which("radare2") or shutil.which("r2")
    if r2:
        v = subprocess.run([r2, "-v"], capture_output=True, text=True).stdout.splitlines()[0]
        click.secho(f"[ok] Radare2: {v}", fg="green")
    else:
        click.secho("[x] Radare2 no está en el PATH", fg="red")

    from .inference import OLLAMA_HOST, verificar_ollama
    try:
        verificar_ollama(modelo)
        click.secho(f"[ok] Ollama en {OLLAMA_HOST} con {modelo}", fg="green")
    except SystemExit as e:
        click.secho(f"[x] {e}", fg="red")


# ------------------------------------------------------------------- extract
@cli.command()
@click.argument("binario", type=click.Path(exists=True, dir_okay=False))
@click.option("--ref", type=click.Path(exists=True, dir_okay=False),
              help="Versión non-stripped del mismo binario (ground truth).")
@click.option("-o", "--out", type=click.Path(dir_okay=False), required=True)
def extract(binario, ref, out):
    """Extrae las funciones de BINARIO a un JSON."""
    t0 = time.perf_counter()
    funciones = extraer_funciones(binario)
    if ref:
        funciones = emparejar_con_ground_truth(funciones, extraer_funciones(ref))
    guardar_json(funciones, out)
    con_nombre = sum(1 for f in funciones if f.nombre_original)
    click.echo(f"[+] {len(funciones)} funciones ({con_nombre} con nombre original) "
               f"en {time.perf_counter() - t0:.2f}s -> {out}")


# ------------------------------------------------------------- build-dataset
def _pares_binarios(bin_dir: str) -> list[tuple[Path, Path]]:
    """
    Encuentra pares (stripped, con_simbolos) con cualquiera de las dos convenciones:
      - elfinfer:  <proyecto>_O<n>.stripped   +  <proyecto>_O<n>
      - Fernanda:  <proyecto>_O<n>_stripped   +  <proyecto>_O<n>_nonstripped
    """
    pares = []
    for s in sorted(Path(bin_dir).glob("*.stripped")):
        pares.append((s, s.with_suffix("")))
    for s in sorted(Path(bin_dir).glob("*_stripped")):
        pares.append((s, s.with_name(s.name[: -len("_stripped")] + "_nonstripped")))
    return pares


@cli.command("build-dataset")
@click.option("--bin-dir", default="data/binaries", show_default=True,
              type=click.Path(exists=True, file_okay=False))
@click.option("-o", "--out", default="data/dataset/dataset.json", show_default=True)
def build_dataset(bin_dir, out):
    """Empareja cada binario stripped con su versión con símbolos y genera el dataset."""
    todas = []
    pares = _pares_binarios(bin_dir)
    if not pares:
        raise click.ClickException(
            f"No hay binarios stripped en {bin_dir} (X.stripped o X_stripped). "
            "Corre scripts/build_samples.sh o copia los de binarios/ del servidor.")
    for stripped, ref in pares:
        if not ref.exists():
            click.echo(f"[!] Falta la versión con símbolos de {stripped.name}, la salto")
            continue
        fs = emparejar_con_ground_truth(extraer_funciones(stripped), extraer_funciones(ref))
        fs = [f for f in fs if f.nombre_original]
        click.echo(f"  {stripped.name:35s} {len(fs):4d} funciones")
        todas.extend(fs)
    guardar_json(todas, out)
    click.secho(f"[+] Dataset: {len(todas)} funciones -> {out}", fg="green")


# -------------------------------------------------------------------- prompt
@cli.command()
@click.argument("funciones_json", type=click.Path(exists=True, dir_okay=False))
@click.option("--estrategia", type=click.Choice(ESTRATEGIAS), default="few-shot")
@click.option("--indice", default=0, show_default=True, help="Qué función del JSON mostrar.")
@click.option("--pool", type=click.Path(exists=True, dir_okay=False),
              help="Dataset para ejemplos few-shot.")
def prompt(funciones_json, estrategia, indice, pool):
    """Muestra el prompt exacto (útil para depurar sin gastar GPU)."""
    funciones = cargar_json(funciones_json)
    f = funciones[indice]
    pool_fs = [p for p in cargar_json(pool) if _proyecto(p.binario) != _proyecto(f.binario)] if pool else []
    for m in construir_prompt(f, estrategia, pool_fs):
        click.secho(f"--- {m['role']} ---", fg="cyan")
        click.echo(m["content"])


# --------------------------------------------------------------------- infer
@cli.command()
@click.argument("entrada", type=click.Path(exists=True, dir_okay=False))
@click.option("--ref", type=click.Path(exists=True, dir_okay=False),
              help="Binario non-stripped para evaluar (si ENTRADA es un binario).")
@click.option("--modelo", "modelos", multiple=True, default=["qwen2.5-coder:7b"], show_default=True)
@click.option("--estrategia", "estrategias", multiple=True, type=click.Choice(ESTRATEGIAS),
              default=["few-shot"], show_default=True)
@click.option("--pool", type=click.Path(exists=True, dir_okay=False),
              default="data/dataset/dataset.json", show_default=True,
              help="Dataset del que salen los ejemplos few-shot.")
@click.option("--limite", type=int, help="Procesa solo N funciones (para pruebas rápidas).")
@click.option("--semilla", default=42, show_default=True)
@click.option("-o", "--out", default="results/report.json", show_default=True)
def infer(entrada, ref, modelos, estrategias, pool, limite, semilla, out):
    """
    ENTRADA puede ser un binario ELF o un JSON de funciones (de extract/build-dataset).
    Genera report.json con dirección, tamaño, nombre inferido y confianza.
    """
    from .inference import inferir_funcion, verificar_ollama

    if entrada.endswith(".json"):
        funciones = cargar_json(entrada)
    else:
        funciones = extraer_funciones(entrada)
        if ref:
            funciones = emparejar_con_ground_truth(funciones, extraer_funciones(ref))

    if limite and limite < len(funciones):
        random.Random(semilla).shuffle(funciones)
        funciones = funciones[:limite]

    pool_total = cargar_json(pool) if Path(pool).exists() else []
    if "few-shot" in estrategias and not pool_total:
        raise click.ClickException(f"few-shot necesita un dataset en {pool}. Corre build-dataset primero.")

    for m in modelos:
        verificar_ollama(m)

    filas = []
    total = len(funciones) * len(modelos) * len(estrategias)
    with click.progressbar(length=total, label="Infiriendo") as barra:
        for modelo in modelos:
            for estrategia in estrategias:
                for f in funciones:
                    # nunca usar ejemplos del mismo proyecto que la función evaluada
                    pool_fs = [p for p in pool_total if _proyecto(p.binario) != _proyecto(f.binario)]
                    filas.append(inferir_funcion(f, modelo, estrategia, pool_fs))
                    barra.update(1)

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps(filas, indent=2, ensure_ascii=False), encoding="utf-8")
    click.secho(f"[+] {len(filas)} inferencias -> {out}", fg="green")

    res = metrics.resumen(filas)
    if res:
        _imprimir_resumen(res)


# ------------------------------------------------------------------ evaluate
@cli.command()
@click.argument("report", type=click.Path(exists=True, dir_okay=False))
def evaluate(report):
    """Imprime EM / F1 / BLEU-4 promedio por modelo y estrategia."""
    filas = json.loads(Path(report).read_text(encoding="utf-8"))
    res = metrics.resumen(filas)
    if not res:
        raise click.ClickException("El reporte no tiene ground truth (no se usó --ref ni dataset).")
    _imprimir_resumen(res)


def _imprimir_resumen(res: dict) -> None:
    click.echo(f"\n{'modelo | estrategia':45s} {'n':>4} {'EM':>7} {'F1':>7} {'BLEU4':>7} {'s/fn':>6} {'tok/resp':>8}")
    for k, v in res.items():
        tok = f"{v['tokens_resp_prom']:8.1f}" if v.get("tokens_resp_prom") is not None else f"{'-':>8}"
        click.echo(f"{k:45s} {v['n']:4d} {v['EM']:7.3f} {v['F1']:7.3f} {v['BLEU4']:7.3f} {v['seg_promedio']:6.2f} {tok}")


# ------------------------------------------------------------------- export
_RE_SIMBOLO = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@cli.command()
@click.argument("report", type=click.Path(exists=True, dir_okay=False))
@click.option("--binario", required=True,
              help="Ruta del binario stripped al que corresponde (se escribe en el campo 'binary').")
@click.option("--modelo", default=None, help="Si el reporte tiene varios modelos, cuál exportar.")
@click.option("--estrategia", type=click.Choice(ESTRATEGIAS), default=None,
              help="Si el reporte tiene varias estrategias, cuál exportar.")
@click.option("-o", "--out", required=True, type=click.Path(dir_okay=False))
def export(report, binario, modelo, estrategia, out):
    """
    Convierte un report.json de elfinfer al contrato de la capa de reconstrucción:

    \b
    {"binary": ..., "functions": [{"address", "size", "inferred_name",
                                   "confidence", "prompt_strategy"}]}
    """
    filas = json.loads(Path(report).read_text(encoding="utf-8"))
    nombre_bin = Path(binario).name
    filas = [f for f in filas if f.get("binario") == nombre_bin]
    if not filas:
        raise click.ClickException(f"El reporte no tiene funciones del binario {nombre_bin}.")

    combos = sorted({(f["modelo"], f["estrategia"]) for f in filas})
    if modelo:
        filas = [f for f in filas if f["modelo"] == modelo]
    if estrategia:
        filas = [f for f in filas if f["estrategia"] == estrategia]
    if len({(f["modelo"], f["estrategia"]) for f in filas}) != 1:
        opciones = ", ".join(f"{m} | {e}" for m, e in combos)
        raise click.ClickException(
            f"Elige UNA combinación con --modelo y --estrategia. Disponibles: {opciones}")

    funciones, invalidas = [], 0
    for f in sorted(filas, key=lambda x: int(x["direccion"], 16)):
        nombre = f.get("nombre_inferido")
        if not nombre or not _RE_SIMBOLO.match(nombre):
            invalidas += 1
            continue
        funciones.append({
            "address": f["direccion"],
            "size": int(f["tamano_bytes"]),
            "inferred_name": nombre,
            "confidence": f.get("confianza"),
            "prompt_strategy": "chain-of-thought" if f["estrategia"] == "cot" else f["estrategia"],
        })

    Path(out).parent.mkdir(parents=True, exist_ok=True)
    Path(out).write_text(json.dumps({"binary": binario, "functions": funciones}, indent=2,
                                    ensure_ascii=False), encoding="utf-8")
    click.secho(f"[+] {len(funciones)} funciones -> {out}", fg="green")
    if invalidas:
        click.echo(f"[!] {invalidas} sin nombre válido (no se exportan)")


# --------------------------------------------------------------------- bench
def _entorno_auto() -> str:
    if Path("/.dockerenv").exists():
        return "docker"
    return platform.system().lower()


def _guardar_bench(out: str, fila: dict) -> None:
    columnas = ["fecha", "entorno", "etapa", "detalle", "n", "repeticiones",
                "media_s", "desv_s", "total_s", "radare2", "python", "plataforma"]
    nuevo = not Path(out).exists()
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    with open(out, "a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=columnas)
        if nuevo:
            w.writeheader()
        w.writerow(fila)


def _version_r2() -> str:
    r2 = shutil.which("radare2") or shutil.which("r2")
    if not r2:
        return "?"
    salida = subprocess.run([r2, "-v"], capture_output=True, text=True).stdout.split()
    return salida[1] if len(salida) > 1 else "?"


@cli.command()
@click.option("--entorno", default=None,
              help="Etiqueta del entorno, p. ej. windows, docker-windows, ubuntu, docker-ubuntu.")
@click.option("--bin-dir", default="data/binaries", show_default=True,
              type=click.Path(exists=True, file_okay=False))
@click.option("--repeticiones", default=5, show_default=True, help="Pasadas de extracción.")
@click.option("--inferencia", "n_inferencia", default=0, show_default=True,
              help="Nº de funciones a inferir para medir el LLM (0 = no medir).")
@click.option("--modelo", default="qwen2.5-coder:7b", show_default=True)
@click.option("--estrategia", type=click.Choice(ESTRATEGIAS), default="few-shot", show_default=True)
@click.option("--pool", default="data/dataset/dataset.json", show_default=True)
@click.option("--semilla", default=42, show_default=True)
@click.option("-o", "--out", default="benchmarks/benchmarks.csv", show_default=True)
def bench(entorno, bin_dir, repeticiones, n_inferencia, modelo, estrategia, pool, semilla, out):
    """
    Mide tiempos por etapa para comparar Windows, Linux y Docker.

    \b
    - extraccion: Radare2 sobre TODOS los *.stripped de --bin-dir, varias pasadas.
    - inferencia: las mismas N funciones (semilla fija) en el modelo local.
    Cada medición se agrega a benchmarks/benchmarks.csv (fecha en UTC).
    """
    entorno = entorno or _entorno_auto()
    comun = {"fecha": time.strftime("%Y-%m-%d %H:%M", time.gmtime()), "entorno": entorno,
             "radare2": _version_r2(), "python": platform.python_version(),
             "plataforma": platform.platform()}

    # ---- extracción
    binarios = [s for s, _ in _pares_binarios(bin_dir)]
    if not binarios:
        raise click.ClickException(f"No hay *.stripped en {bin_dir}. Corre scripts/build_samples.sh")
    click.secho(f"[extracción] {len(binarios)} binarios × {repeticiones} pasadas", fg="cyan")
    tiempos, n_fn = [], 0
    for i in range(repeticiones):
        t0 = time.perf_counter()
        n_fn = sum(len(extraer_funciones(b)) for b in binarios)
        tiempos.append(time.perf_counter() - t0)
        click.echo(f"  pasada {i + 1}: {tiempos[-1]:.2f}s ({n_fn} funciones)")
    media = statistics.mean(tiempos)
    desv = statistics.stdev(tiempos) if len(tiempos) > 1 else 0.0
    click.secho(f"  => {media:.2f}s ± {desv:.2f}s por pasada", fg="green")
    _guardar_bench(out, {**comun, "etapa": "extraccion", "detalle": f"{len(binarios)} binarios",
                         "n": n_fn, "repeticiones": repeticiones, "media_s": f"{media:.3f}",
                         "desv_s": f"{desv:.3f}", "total_s": f"{sum(tiempos):.3f}"})

    # ---- inferencia
    if n_inferencia > 0:
        from .inference import inferir_funcion, verificar_ollama
        verificar_ollama(modelo)
        pool_total = cargar_json(pool)
        muestra = list(pool_total)
        random.Random(semilla).shuffle(muestra)
        muestra = muestra[:n_inferencia]
        click.secho(f"[inferencia] {modelo} | {estrategia} | {len(muestra)} funciones", fg="cyan")

        # calentamiento: la primera llamada carga el modelo en memoria y no se cuenta
        inferir_funcion(muestra[0], modelo, estrategia, pool_total)

        t_fn = []
        for f in muestra:
            pool_fs = [p for p in pool_total if _proyecto(p.binario) != _proyecto(f.binario)]
            t0 = time.perf_counter()
            inferir_funcion(f, modelo, estrategia, pool_fs)
            t_fn.append(time.perf_counter() - t0)
            click.echo(f"  {f.nombre_original or f.direccion:25s} {t_fn[-1]:.2f}s")
        media = statistics.mean(t_fn)
        desv = statistics.stdev(t_fn) if len(t_fn) > 1 else 0.0
        click.secho(f"  => {media:.2f}s ± {desv:.2f}s por función", fg="green")
        _guardar_bench(out, {**comun, "etapa": "inferencia", "detalle": f"{modelo} | {estrategia}",
                             "n": len(t_fn), "repeticiones": 1, "media_s": f"{media:.3f}",
                             "desv_s": f"{desv:.3f}", "total_s": f"{sum(t_fn):.3f}"})

    click.echo(f"[+] Guardado en {out}")


@cli.command("bench-report")
@click.option("-i", "--entrada", default="benchmarks/benchmarks.csv", show_default=True,
              type=click.Path(exists=True, dir_okay=False))
@click.option("--desde", default=None,
              help='Solo mediciones desde esta fecha UTC, p. ej. "2026-10-01 06:24".')
def bench_report(entrada, desde):
    """Tabla comparativa de entornos a partir de benchmarks.csv."""
    with open(entrada, encoding="utf-8") as fh:
        filas = list(csv.DictReader(fh))
    if desde:
        filas = [f for f in filas if f["fecha"] >= desde]
    grupos: dict[tuple, list[float]] = {}
    for f in filas:
        grupos.setdefault((f["etapa"], f["detalle"], f["entorno"]), []).append(float(f["media_s"]))
    if desde:
        click.echo(f"(mediciones desde {desde} UTC)")
    click.echo(f"\n{'etapa':11s} {'detalle':30s} {'entorno':16s} {'corridas':>8} {'media_s':>8} {'desv_s':>7} {'min':>6} {'max':>6}")
    for (etapa, detalle, ent), v in sorted(grupos.items()):
        desv = statistics.stdev(v) if len(v) > 1 else 0.0
        click.echo(f"{etapa:11s} {detalle:30s} {ent:16s} {len(v):8d} {statistics.mean(v):8.3f} "
                   f"{desv:7.3f} {min(v):6.2f} {max(v):6.2f}")


if __name__ == "__main__":
    cli()
