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

### Re-medición en Windows nativo tras la corrección de red

| Etapa | Docker en Windows | Windows nativo (antes) | Windows nativo (después) |
|---|---|---|---|
| Extracción (s/pasada) | 1.66 ± 0.21 | 1.13 ± 0.06 | **1.04 ± 0.01** |
| Inferencia few-shot (s/función) | **0.90 ± 0.31** | 3.15 ± 0.23 | 1.57 ± 0.46 |

- La inferencia nativa bajó a la mitad (3.15 → 1.57 s): **confirma que la mayor parte de la
  diferencia era el retraso de red**, no el sistema operativo.
- La extracción nativa es consistente (desviación de 0.01 s) y sigue siendo ~37% más rápida que Docker.
- Queda una brecha en inferencia (1.57 contra 0.90 s). Posible causa: el código abría una conexión nueva
  a Ollama en cada función. **Corregido:** ahora se reutiliza un solo cliente. Hay que volver a medir.
- **Ojo:** `bench-report` promedia la medición nativa vieja (con el error) y la nueva, así que su `2.361`
  no es válido. La fila del 2026-10-01 00:14 de `windows` en `benchmarks.csv` se eliminó del reporte
  (queda registrada en esta bitácora y en sus capturas).
- A partir de esta versión, la columna `fecha` del CSV se guarda siempre en UTC (Docker ya lo hacía;
  Windows guardaba hora local).

Capturas: `capturas/2026-10-01_bench_windows_tras_correccion.png`, `capturas/2026-10-01_bench_report.png`.

### Comparativa final del día: 3 corridas por entorno, cliente reutilizado

`elfinfer bench-report --desde "2026-10-01 06:24"` (solo mediciones con el código corregido):

| Etapa | Windows nativo | Docker en Windows | Diferencia |
|---|---|---|---|
| Extracción, s/pasada (9 binarios, 95 funciones) | **1.12 ± 0.04** (1.09–1.16) | 1.66 ± 0.04 (1.63–1.71) | Docker ~48% más lento |
| Inferencia few-shot, s/función (10 funciones) | 0.66 ± 0.00 | 0.67 ± 0.02 | ≈ igual (~2%) |

**Conclusiones**
1. **La extracción sí depende del entorno.** Radare2 nativo en Windows es ~33% más rápido que dentro
   de Docker. La causa es la capa de virtualización de Docker en Windows (WSL2) y el acceso a la carpeta
   compartida. Se espera que en Linux nativo Docker no tenga ese costo.
2. **La inferencia no depende del sistema operativo.** Con la conexión corregida, Windows y Docker
   tardan lo mismo: el tiempo lo define la GPU (RTX 3050, 4 GB) y Ollama, no el entorno del cliente.
3. **Los dos errores de medición encontrados eran del cliente, no del SO:** resolver `localhost`
   por IPv6 (~2 s por llamada) y abrir una conexión nueva por función (~0.9 s). Corregirlos bajó la
   inferencia nativa de 3.15 s a 0.66 s por función (4.8× más rápido) y también mejoró Docker
   (0.90 → 0.67 s).
4. Para los experimentos grandes, la extracción representa una parte mínima del tiempo total
   (~0.012 s por función contra ~0.66 s de inferencia few-shot y ~24 s de CoT), así que **elegir
   Docker por portabilidad casi no cuesta tiempo** en el pipeline completo.

Capturas: `capturas/2026-10-01_bench_windows_3corridas_a.png`, `..._b.png`,
`capturas/2026-10-01_bench_docker_3corridas_a.png`, `..._b.png`, `capturas/2026-10-01_bench_report_final.png`.

### Siguiente
- Medir en Linux (misma laptop, USB booteable o arranque dual) con `--entorno ubuntu` y `docker-ubuntu`.
- Probar `qwen2.5-coder:3b` y `deepseek-coder:6.7b` con las mismas 20 funciones.
- Ampliar el dataset con proyectos reales (cJSON, tinyexpr, miniz) para acercarse a 500 funciones.
- Evaluar una métrica semántica adicional, porque F1 por tokens subestima respuestas correctas.

---

## 2026-10-01 (mañana) — Integración con la capa de reconstrucción

Se revisó el contexto y la guía del trabajo de Fernanda (servidor `techmaleon`, `reconstructor.py`,
oráculo y validación con 7 proyectos reales).

### Problema encontrado: el `report.json` no era compatible
| Contrato de `reconstructor.py` | Lo que generaba `elfinfer infer` |
|---|---|
| objeto `{"binary", "functions": [...]}` | lista directa `[...]` |
| `address`, `size`, `inferred_name` | `direccion`, `tamano_bytes`, `nombre_inferido` |
| `confidence`, `prompt_strategy` | `confianza`, `estrategia` |

Los datos estaban, pero con otros nombres; además el reporte mezcla varias estrategias.
**Solución:** nuevo comando `elfinfer export`, que genera un archivo por binario y estrategia con el
formato exacto del contrato. El reporte de evaluación no cambia.

### Prueba de punta a punta
Binario `checksum_O0` compilado como PIE (igual que los del servidor) → `infer` (modelo simulado) →
`export` → `reconstructor.py` de la guía (md5 `b8a20db9c2f0334c34f72de4e182ac78`):
- Símbolos reinyectados: **7 de 7**.
- Salida del programa idéntica antes y después (mismo SHA-256).
- `readelf` y Radare2 muestran los nombres reinyectados.
- Archivo exportado: `resultados/2026-10-01_prueba_contrato_checksum_O0.json`.

### Otros cambios por hallazgos de la capa de reconstrucción
1. **Código de arranque:** se mandaban al modelo `entry0` (`_start`), `entry.init0` y `entry.fini0`.
   Ahora se descartan, igual que en el oráculo.
2. **`main`:** Radare2 la reconoce en el binario stripped. Ya no se le pregunta al modelo; se reporta con
   ese nombre y confianza `alta` (y no cuenta en las métricas).
3. **Convención de nombres del servidor:** `build-dataset` acepta `<proyecto>_<nivel>_stripped` /
   `_nonstripped`, así que se pueden reutilizar los binarios de los 7 proyectos reales del servidor.
4. **Sufijos de GCC** (`.constprop.0`, `.isra.0`, `.part.1`, `.cold`): se quitan antes de evaluar.
5. **Tokens por respuesta:** cada inferencia guarda `tokens_prompt` y `tokens_respuesta`, para explicar
   los tiempos con evidencia.

### Sobre los 0.66 s por función
La observación de que podría ser "efecto de caché" es válida y se revisará con los nuevos campos.
Lo esperado: cada función tiene un prompt distinto, así que la caché de Ollama solo reutiliza la parte
común (instrucciones del sistema y, en few-shot, a veces ejemplos repetidos). La causa principal del
tiempo bajo es que en zero-shot y few-shot el modelo genera muy pocos tokens (solo `NAME: x`), mientras
que CoT genera cientos (por eso tarda ~24 s). Con `tokens_respuesta` se podrá confirmar.

### Siguiente
- Copiar los binarios del servidor y generar el dataset real (`build-dataset --bin-dir`).
- Primera prueba de punta a punta con el modelo real sobre `aes_O0_stripped` y el reconstructor del servidor.
- Medición en Linux (Parrot, dual boot desde disco externo): anotar que el disco es USB.
