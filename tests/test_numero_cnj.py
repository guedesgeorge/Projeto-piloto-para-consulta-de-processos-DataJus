import pytest

from consulta.numero_cnj import NumeroInvalido, TribunalNaoSuportado, alias_tribunal, parse_numero

EXEMPLO = "0000832-35.2018.4.01.3202"  # exemplo da documentação do DataJud


def _gerar(segmento: str, tribunal: str) -> str:
    """Gera um número válido (com dígito verificador correto) para o segmento/tribunal."""
    n, a, o = "0000001", "2024", "0001"
    dv = 98 - int(n + a + segmento + tribunal + o + "00") % 97
    return f"{n}-{dv:02d}.{a}.{segmento}.{tribunal}.{o}"


def test_aceita_numero_formatado_e_so_digitos():
    assert parse_numero(EXEMPLO).digitos == "00008323520184013202"
    assert parse_numero("00008323520184013202").formatado == EXEMPLO


def test_rejeita_tamanho_errado():
    with pytest.raises(NumeroInvalido):
        parse_numero("123")


def test_rejeita_digito_verificador_errado():
    with pytest.raises(NumeroInvalido):
        parse_numero("0000832-36.2018.4.01.3202")


@pytest.mark.parametrize("segmento,tribunal,alias", [
    ("4", "01", "trf1"),
    ("4", "06", "trf6"),
    ("8", "12", "tjms"),
    ("8", "26", "tjsp"),
    ("8", "07", "tjdft"),
    ("5", "00", "tst"),
    ("5", "24", "trt24"),
    ("6", "00", "tse"),
    ("6", "12", "tre-ms"),
    ("6", "07", "tre-dft"),
    ("3", "00", "stj"),
    ("7", "00", "stm"),
    ("9", "26", "tjmsp"),
])
def test_alias_tribunal(segmento, tribunal, alias):
    assert alias_tribunal(parse_numero(_gerar(segmento, tribunal))) == alias


@pytest.mark.parametrize("segmento,tribunal", [("1", "00"), ("2", "00"), ("9", "12"), ("4", "07")])
def test_tribunal_nao_suportado(segmento, tribunal):
    with pytest.raises(TribunalNaoSuportado):
        alias_tribunal(parse_numero(_gerar(segmento, tribunal)))
