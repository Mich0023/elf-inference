"""Prueba el flujo de inferencia sin Ollama real (cliente simulado)."""
from types import SimpleNamespace

from elfinfer import inference
from elfinfer.extractor import Funcion
from elfinfer.prompt_builder import construir_prompt, seleccionar_ejemplos


class ClienteFalso:
    def __init__(self, *a, **k):
        pass

    def chat(self, model, messages, options):
        texto = "1. Loops over a linked list adding values.\nNAME: list_sum"
        return SimpleNamespace(message=SimpleNamespace(content=texto))


def _fn(nombre, n=10, asm=None, binario="x_O0.stripped"):
    asm = asm or ["push rbp", "mov rbp, rsp", "add eax, edx", "pop rbp", "ret"]
    return Funcion("0x401000", 40, n, asm, nombre, binario)


def test_parsear_nombre():
    assert inference.parsear_nombre("blah\nNAME: crc32_compute") == "crc32_compute"
    assert inference.parsear_nombre("NAME: `List_Sum`") == "list_sum"
    assert inference.parsear_nombre("I think it is count_words.") == "count_words"
    assert inference.parsear_nombre("no se") is None


def test_reporte_con_ground_truth(monkeypatch):
    monkeypatch.setattr(inference.ollama, "Client", ClienteFalso)
    monkeypatch.setattr(inference, "_CLIENTE", None)
    fila = inference.inferir_funcion(_fn("list_sum"), "qwen2.5-coder:7b", "cot")
    # campos que necesita la capa de reconstrucción
    for k in ("direccion", "tamano_bytes", "nombre_inferido", "confianza", "estrategia", "modelo"):
        assert k in fila
    assert fila["nombre_inferido"] == "list_sum"
    assert fila["em"] == 1.0 and fila["confianza"] == "alta"


def test_reporte_sin_ground_truth(monkeypatch):
    monkeypatch.setattr(inference.ollama, "Client", ClienteFalso)
    monkeypatch.setattr(inference, "_CLIENTE", None)
    fila = inference.inferir_funcion(_fn(None), "qwen2.5-coder:7b", "zero-shot")
    assert "f1" not in fila
    assert fila["confianza"] == "media"


def test_few_shot_no_filtra_la_respuesta():
    objetivo = _fn("list_sum")
    pool = [_fn("list_sum"), _fn("list_length"), _fn("list_free"), _fn("count_words")]
    ejemplos = seleccionar_ejemplos(objetivo, pool)
    assert len(ejemplos) == 3
    assert all(e.nombre_original != "list_sum" for e in ejemplos)
    texto = construir_prompt(objetivo, "few-shot", pool)[1]["content"]
    assert "NAME: list_sum" not in texto


def test_cot_exige_razonamiento():
    texto = construir_prompt(_fn(None), "cot")[1]["content"]
    assert "Reasoning:" in texto
    assert "Do NOT skip the reasoning" in texto


def test_main_no_se_evalua():
    from elfinfer.extractor import emparejar_con_ground_truth
    stripped = [Funcion("0x10", 9, 9, [], None), Funcion("0x20", 9, 9, [], None)]
    ref = [Funcion("0x10", 9, 9, [], "main"), Funcion("0x20", 9, 9, [], "list_sum")]
    res = emparejar_con_ground_truth(stripped, ref)
    assert res[0].nombre_original is None
    assert res[1].nombre_original == "list_sum"


def test_parser_respuestas_reales_cot():
    # casos que fallaron en la corrida del 2026-10-01
    assert inference.parsear_nombre("...\n### NAME:\nNAME: check_and_jump") == "check_and_jump"
    assert inference.parsear_nombre("### NAME:\nNAME: `update_pointer`") == "update_pointer"
    assert inference.parsear_nombre("**NAME:** count_nodes") == "count_nodes"
    assert inference.parsear_nombre("### NAME:\ntransform_range") == "transform_range"
    assert inference.parsear_nombre("**NAME: count_whitespace**") == "count_whitespace"
