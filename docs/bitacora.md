# Bitácora del motor de inferencia

Registro de avances, pruebas y hallazgos. Las capturas van en `docs/capturas/`
con el nombre `AAAA-MM-DD_descripcion.png`.

---

## 2026-09-30 — Entorno y primera corrida real (Windows + Docker)

**Equipo:** laptop con Windows 11, 16 GB RAM, NVIDIA RTX 3050 (4 GB VRAM).

### Entorno
- Docker Desktop: imagen `elfinfer` construida (Python 3.11 + Radare2 6.2.2 + GCC).
- Ollama en Windows con `qwen2.5-coder:7b` y `deepseek-coder:6.7b`.
- El contenedor se conecta a Ollama por `host.docker.internal:11434`.
- Repositorio: https://github.com/Mich0023/elf-inference

### Problemas resueltos
| Problema | Causa | Solución |
|---|---|---|
| `check` no conectaba con Ollama | Ollama estaba cerrado | Abrirlo (`ollama serve`) |
| `git status` marcaba `build_samples.sh` modificado | Windows no conserva el permiso de ejecución | `git config core.fileMode false` |
| El 7B corre 55% CPU / 45% GPU | Solo 4 GB de VRAM | Pendiente: probar `qwen2.5-coder:3b` |

### Primera inferencia (5 funciones × 3 estrategias, qwen2.5-coder:7b)

| Estrategia | EM | F1 | BLEU-4 | s/función |
|---|---|---|---|---|
| zero-shot | 0.000 | 0.167 | 0.205 | 4.42* |
| few-shot | 0.000 | 0.067 | 0.064 | 1.79 |
| chain-of-thought | 0.000 | 0.067 | 0.064 | 0.79 |

\* Incluye la carga inicial del modelo en memoria.

Ejemplos de respuestas:

| Nombre real | Predicción |
|---|---|
| `duplicate_string` | `allocate_and_copy_string` |
| `list_length` | `count_elements` / `count_elements_until_null` |
| `crc32_compute` | `process_data` / `xor_bytes` |

### Hallazgos
1. **El modelo entiende la función, pero usa otras palabras.** `duplicate_string → allocate_and_copy_string`
   es semánticamente correcto, pero F1 por tokens lo castiga casi a cero. Las métricas léxicas
   subestiman la calidad: vale la pena discutirlo en el reporte (posible métrica semántica extra).
2. **Chain-of-thought no razonaba.** El prompt pedía "una sola línea final" y el modelo respondió
   solo `NAME: ...`. Por eso era la estrategia más rápida. **Corregido:** el prompt ahora exige una
   sección `Reasoning:` antes del nombre.
3. **`main` contaminaba la evaluación.** Radare2 lo detecta aunque el binario esté stripped, así que
   no mide al modelo. **Corregido:** se excluye del ground truth (el dataset pasó de 59 a 50 funciones).
4. Con 5 funciones los promedios no son concluyentes; siguiente prueba con más funciones.

### Capturas
- `capturas/2026-09-30_netstat_ollama.png`: Ollama escuchando en el puerto 11434
- `capturas/2026-09-30_build_samples_dataset.png`: compilación de ejemplos y dataset
- `capturas/2026-09-30_primera_inferencia.png`: tabla de métricas de la primera corrida
- `capturas/2026-09-30_predicciones_vs_reales.png`: nombres reales vs. predichos

### Siguiente
- Repetir la inferencia con las correcciones y ~20 funciones.
- Primera medición de la comparativa (`bench`) en Windows nativo y Docker.

---

## 2026-10-01 — Corrida con correcciones (20 funciones) y primera comparativa

### Inferencia: 20 funciones × 3 estrategias, qwen2.5-coder:7b (Docker en Windows)

Dataset de 50 funciones (sin `main`); muestra aleatoria con semilla 42.
Reporte completo: `resultados/2026-10-01_report_20fn.json`.

| Estrategia | EM | F1 | BLEU-4 | s/función | Aciertos parciales (F1 > 0) |
|---|---|---|---|---|---|
| zero-shot | 0.050 | 0.178 | 0.180 | 1.16 | 7 / 20 |
| few-shot | 0.000 | 0.143 | 0.175 | 1.56 | 7 / 20 |
| chain-of-thought | 0.050 | **0.187** | **0.232** | 24.27 | 7 / 20 |

F1 promedio por nivel de optimización:

| Estrategia | O0 | O1 | O2 |
|---|---|---|---|
| zero-shot | 0.357 | 0.092 | 0.067 |
| few-shot | 0.176 | 0.092 | 0.180 |
| chain-of-thought | 0.286 | 0.175 | 0.067 |

Aciertos exactos: `reverse_string` (zero-shot) y `duplicate_string` (CoT).

### Hallazgos
1. **CoT ya razona** (corrección del 30-sep funcionó): ahora es la más lenta (~24 s por
   función contra ~1 s de las otras) y la de mejor F1/BLEU, aunque la ventaja es pequeña
   con 20 funciones. El costo en tiempo es ~20× mayor.
2. **Zero-shot cae en un nombre genérico:** respondió `process_data` en 8 de 20 funciones.
3. **Few-shot copia el dominio de los ejemplos:** a todas las funciones de checksum les puso
   `calculate_checksum` (dominio correcto, pero no distingue CRC32, Adler-32 o Fletcher).
4. **La optimización del compilador afecta claramente:** en zero-shot y CoT el F1 cae de O0 a O2.
   Es justo la variable que el anteproyecto plantea medir.
5. **El modelo entiende más de lo que miden las métricas:** `list_length → count_nodes`,
   `list_sum → sum_array`, `is_palindrome → compare_strings`. Describen bien el comportamiento,
   pero F1 por tokens los califica con 0 o casi 0.
6. **Error del parser (corregido):** en 3 respuestas CoT el modelo escribió `### NAME:` seguido de
   `NAME: x`, y se leía la palabra "name" como nombre. Recuperados: `check_and_jump`,
   `update_pointer`, `encode_bytes` (siguen sin coincidir con el nombre real, el F1 no cambia).

### Comparativa de entornos (primera medición, 1 corrida por entorno)

| Etapa | Docker en Windows | Windows nativo |
|---|---|---|
| Extracción (9 binarios, 95 funciones, media de 5 pasadas) | 1.66 s ± 0.21 | **1.13 s ± 0.06** |
| Inferencia few-shot (10 funciones, s/función) | **0.90 s ± 0.31** | 3.15 s ± 0.23 |

- **Extracción:** Windows nativo fue ~32% más rápido que Docker. Concuerda con la hipótesis:
  Docker en Windows corre sobre WSL2 y lee los archivos a través de la carpeta compartida.
- **Inferencia:** el resultado al revés (nativo 3.5× más lento) **no es atribuible al sistema operativo**:
  ambos entornos llaman al mismo Ollama y la misma GPU. La diferencia es casi constante (~2.2 s
  por llamada), típica de un retraso de red: en Windows, `localhost` intenta primero IPv6 y la
  variable `OLLAMA_HOST=0.0.0.0` también la lee el cliente. **Corregido:** el cliente ahora usa
  siempre `127.0.0.1`. Hay que repetir la medición nativa para confirmarlo.

### Capturas
- `capturas/2026-10-01_dataset_sin_main.png`: dataset de 50 funciones
- `capturas/2026-10-01_inferencia_20_funciones.png`: tabla de métricas con 20 funciones
- `capturas/2026-10-01_bench_docker_windows.png`: benchmark en Docker
- `capturas/2026-10-01_bench_windows_nativo.png`: benchmark nativo y `bench-report`

### Siguiente
- Repetir `bench --entorno windows` con la corrección de red (3 corridas por entorno).
- Medir en Linux (misma laptop, USB booteable o arranque dual).
- Probar `qwen2.5-coder:3b` y `deepseek-coder:6.7b` con las mismas 20 funciones.
- Ampliar el dataset con proyectos reales (cJSON, tinyexpr, miniz) para acercarse a 500 funciones.
- Evaluar una métrica semántica adicional, porque F1 por tokens subestima respuestas correctas.
