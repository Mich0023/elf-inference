# Comparativa de entornos: Windows vs Linux vs Docker

Objetivo: medir si el sistema operativo cambia el tiempo de cada etapa del motor,
para decidir en qué entorno correr los experimentos grandes (500+ funciones).

## Entornos a comparar

| Etiqueta (`--entorno`) | Qué es | Cómo se corre |
|---|---|---|
| `windows` | Python y Radare2 instalados directo en Windows | `elfinfer bench ...` en PowerShell con el venv activo |
| `docker-windows` | Contenedor Docker sobre Windows (WSL2) | `docker compose run --rm elfinfer bench ...` |
| `ubuntu` (o `parrot`) | Python y Radare2 instalados directo en Linux | `elfinfer bench ...` en la terminal |
| `docker-ubuntu` | Contenedor Docker sobre Linux nativo | `docker compose run --rm elfinfer bench ...` |

**Importante:** para que la comparación sea justa, Linux debe correr **en la misma laptop**
(arranque dual o USB booteable). Si se usa otra máquina, se compara hardware, no sistema operativo.

## Reglas para medir

1. Mismos binarios en todos los entornos: se compilan **una vez** con Docker
   (`scripts/build_samples.sh`) y se reutiliza la carpeta `data/`.
2. Mismo modelo, misma estrategia y misma semilla (los defaults del comando).
3. Laptop conectada a la corriente, con el modo de energía en *alto rendimiento*.
4. Cerrar navegador, WhatsApp y apps pesadas (también liberan VRAM).
5. Ollama abierto y con el modelo ya descargado.
6. Correr el benchmark **3 veces** por entorno; el reporte promedia.

## Comandos

```bash
# Docker (en Windows; en Linux cambia la etiqueta a docker-ubuntu)
docker compose run --rm elfinfer bench --entorno docker-windows --repeticiones 5 --inferencia 10

# Nativo (Windows: activa .venv; Linux: igual)
pip install -e .
elfinfer bench --entorno windows --repeticiones 5 --inferencia 10

# Tabla comparativa con todo lo medido
elfinfer bench-report
```

Cada corrida se agrega a `benchmarks/benchmarks.csv`, que **sí se sube a Git**,
así las mediciones de distintas máquinas quedan juntas.

## Qué se mide

| Etapa | Qué incluye | Hipótesis |
|---|---|---|
| `extraccion` | Radare2 analizando todos los `*.stripped`, varias pasadas | Más rápida en Linux nativo; Docker en Windows paga el costo de WSL2 y del sistema de archivos compartido |
| `inferencia` | Tiempo por función en el modelo local (sin contar la carga inicial del modelo) | Casi igual en todos: depende de la GPU y su VRAM, no del SO |

## Resultados

Ver `bench-report` y la bitácora (`docs/bitacora.md`).
