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
