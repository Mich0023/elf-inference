# elf-inference

Motor de inferencia de nombres de funciones en binarios **ELF stripped** (x86-64)
mediante *prompt engineering* sobre modelos de lenguaje locales con **Ollama**.

**Autor:** Reyes Castillo, Brayan Michel · Residencia Profesional, Instituto Tecnológico de Mérida
**Asesores:** Carlos Bermejo Sabbagh (interno) · María Italia Jiménez Ochoa (externo)

```
binario stripped ──► extractor.py ──► prompt_builder.py ──► inference.py ──► report.json
                     (Radare2)        zero-shot / few-shot    (Ollama local)   dirección, tamaño,
                                      / chain-of-thought                      nombre, confianza
```

---

## Cómo está pensado

| Pieza | Dónde corre | Por qué |
|---|---|---|
| Python, Radare2, GCC | **Contenedor Docker** | Mismo entorno en Windows, Ubuntu, Parrot o Mac |
| Ollama + modelos | **Tu máquina (host)** | Necesita la GPU; meterlo a Docker en Windows complica todo |

El contenedor habla con Ollama por HTTP en `host.docker.internal:11434`.

---

## Requisitos

1. **Docker** (Docker Desktop en Windows/Mac, Docker Engine en Linux).
2. **Ollama** instalado en la máquina, con los modelos:
   ```bash
   ollama pull qwen2.5-coder:7b
   ollama pull deepseek-coder:6.7b
   ```
3. **Git**.

No necesitas instalar Python ni Radare2 en tu máquina: vienen en la imagen.

---

## Inicio rápido

```bash
git clone <url-de-tu-repo> elf-inference
cd elf-inference

# 1) Construir la imagen (solo la primera vez o si cambias dependencias)
docker compose build

# 2) Verificar Radare2 y Ollama
docker compose run --rm elfinfer check

# 3) Compilar los programas de ejemplo en O0/O1/O2 (+ versión stripped)
docker compose run --rm --entrypoint bash elfinfer scripts/build_samples.sh

# 4) Armar el dataset con ground truth
docker compose run --rm elfinfer build-dataset

# 5) Inferir nombres y evaluar (prueba rápida con 5 funciones)
docker compose run --rm elfinfer infer data/dataset/dataset.json \
    --estrategia zero-shot --estrategia few-shot --estrategia cot --limite 5
```

> En PowerShell, cambia la `\` del final de línea por un acento grave `` ` `` o escribe todo en una línea.

---

## Comandos

| Comando | Qué hace |
|---|---|
| `check` | Verifica Radare2 y la conexión con Ollama |
| `extract BIN [--ref BIN_CON_SIMBOLOS] -o out.json` | Extrae funciones (dirección, tamaño, Assembly) |
| `build-dataset` | Empareja cada `X.stripped` con `X` y guarda `data/dataset/dataset.json` |
| `prompt JSON --estrategia few-shot --indice N --pool dataset.json` | Muestra el prompt exacto (no usa GPU) |
| `infer ENTRADA [--ref] --modelo M --estrategia E -o report.json` | Corre la inferencia y genera `report.json` |
| `evaluate report.json` | Tabla de EM / F1 / BLEU-4 por modelo y estrategia |
| `bench --entorno E [--inferencia N]` | Mide tiempos de extracción e inferencia (comparativa entre SO) |
| `bench-report` | Tabla comparativa de todos los entornos medidos |

`--modelo` y `--estrategia` se pueden repetir para correr varias combinaciones.

### Analizar un binario desconocido (sin ground truth)

```bash
docker compose run --rm elfinfer infer data/binaries/mi_programa --estrategia few-shot -o results/report.json
```

---

## Formato de `report.json`

Es la interfaz con la capa de reconstrucción. Cada función:

```json
{
  "direccion": "0x401236",
  "tamano_bytes": 51,
  "nombre_inferido": "string_length",
  "confianza": "alta",
  "estrategia": "few-shot",
  "modelo": "qwen2.5-coder:7b",
  "segundos": 1.84,
  "binario": "strutils_O0.stripped",
  "nombre_original": "string_length",
  "em": 1.0,
  "f1": 1.0,
  "bleu4": 1.0
}
```

- `nombre_original`, `em`, `f1`, `bleu4` solo aparecen cuando hay ground truth.
- **Confianza:** con ground truth usa los umbrales de F1 del anteproyecto
  (alta > 0.75, media 0.40–0.75, baja < 0.40). Sin ground truth usa una
  heurística (nombre válido y descriptivo → media; si no → baja).

---

## Agregar proyectos reales al dataset

1. Copia los `.c` del proyecto (p. ej. cJSON, tinyexpr) a una carpeta, por ejemplo `fuentes/cjson/`.
2. Compílalos:
   ```bash
   docker compose run --rm --entrypoint bash elfinfer scripts/build_samples.sh fuentes/cjson
   ```
   Para proyectos con varios archivos o `Makefile`, compílalos con `-g -O0/-O1/-O2`,
   copia el ejecutable a `data/binaries/<proyecto>_O<n>` y su versión stripped a
   `data/binaries/<proyecto>_O<n>.stripped`.
3. Vuelve a correr `build-dataset`.

En few-shot **nunca** se usan ejemplos del mismo proyecto que la función evaluada, para no "regalarle" la respuesta al modelo.

---

## Comparar Windows vs Linux vs Docker

```bash
docker compose run --rm elfinfer bench --entorno docker-windows --repeticiones 5 --inferencia 10
elfinfer bench --entorno windows --repeticiones 5 --inferencia 10    # nativo, con el venv activo
elfinfer bench-report                                               # tabla comparativa
```

Mide por separado la **extracción** (Radare2) y la **inferencia** (LLM) y guarda todo en
`benchmarks/benchmarks.csv`, que sí se sube a Git. El protocolo completo está en
[`docs/comparativa_so.md`](docs/comparativa_so.md) y el registro de pruebas en
[`docs/bitacora.md`](docs/bitacora.md).

---

## Desarrollo sin Docker (opcional)

```bash
python -m venv .venv
# Windows: .venv\Scripts\Activate.ps1    Linux: source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

---

## Problemas comunes

| Síntoma | Solución |
|---|---|
| `No pude conectar con Ollama` (Windows/Mac) | Abre Ollama; verifica `curl http://localhost:11434` en tu máquina |
| `No pude conectar con Ollama` (Linux) | Ollama escucha solo en 127.0.0.1. Arráncalo con `OLLAMA_HOST=0.0.0.0 ollama serve` o en su servicio systemd |
| `El modelo ... no está descargado` | `ollama pull <modelo>` en tu máquina |
| `bash\r: No such file` al correr el script | El `.sh` se guardó con saltos de Windows; `.gitattributes` lo evita en clones nuevos |
| El 7B va lento (4 GB de VRAM) | Prueba `--modelo qwen2.5-coder:3b` (`ollama pull qwen2.5-coder:3b`) |

---

## Estructura

```
elf-inference/
├── src/elfinfer/
│   ├── extractor.py       # Fase 2: Radare2 -> funciones en JSON
│   ├── prompt_builder.py  # Fase 3: zero-shot, few-shot dinámico, CoT
│   ├── inference.py       # Fase 4: Ollama -> report.json
│   ├── metrics.py         # EM, F1 por tokens, BLEU-4
│   └── cli.py             # comandos
├── samples/               # programas C de ejemplo
├── scripts/build_samples.sh
├── tests/                 # pytest
├── data/                  # binarios y dataset (generados, no se suben a Git)
├── results/               # reportes de inferencia (generados)
├── benchmarks/            # mediciones de tiempo (sí se suben)
├── docs/                  # bitácora, comparativa y capturas
├── Dockerfile
└── docker-compose.yml
```
