from elfinfer import metrics


def test_tokenizar():
    assert metrics.tokenizar("calculate_checksum") == ["calculate", "checksum"]
    assert metrics.tokenizar("calcCheckSum") == ["calc", "check", "sum"]
    assert metrics.tokenizar(None) == []


def test_exact_match():
    assert metrics.exact_match("List_Sum", "list_sum") == 1.0
    assert metrics.exact_match("list_total", "list_sum") == 0.0


def test_f1_parcial():
    # el ejemplo del anteproyecto: calc_checksum vs calculate_checksum
    assert metrics.f1_tokens("calc_checksum", "calculate_checksum") == 0.5
    assert metrics.f1_tokens("list_sum", "list_sum") == 1.0
    assert metrics.f1_tokens("foo", "bar") == 0.0


def test_bleu4_rango():
    assert metrics.bleu4("list_sum", "list_sum") > 0.5
    assert metrics.bleu4("foo", "bar") == 0.0
    assert 0 < metrics.bleu4("list_find_node", "list_find") < 1


def test_confianza():
    assert metrics.nivel_confianza(0.9) == "alta"
    assert metrics.nivel_confianza(0.5) == "media"
    assert metrics.nivel_confianza(0.1) == "baja"
