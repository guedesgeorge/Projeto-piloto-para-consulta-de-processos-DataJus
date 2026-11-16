import json
from pathlib import Path

import pytest
import requests
from fastapi.testclient import TestClient

import api.main as main
from consulta import servico
from consulta.datajud import DataJudClient

FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "datajud_trf1.json").read_text(encoding="utf-8"))
NUMERO = "0000832-35.2018.4.01.3202"


class RespostaFalsa:
    def __init__(self, status_code, dados=None):
        self.status_code = status_code
        self._dados = dados or {}

    def json(self):
        return self._dados


class SessaoFalsa:
    """Substitui requests.Session e devolve respostas pré-definidas, em ordem."""

    def __init__(self, *respostas):
        self.respostas = list(respostas)
        self.chamadas = []

    def post(self, url, **kwargs):
        self.chamadas.append((url, kwargs))
        r = self.respostas.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


@pytest.fixture
def usar_sessao(monkeypatch):
    def _usar(*respostas):
        sessao = SessaoFalsa(*respostas)
        monkeypatch.setattr(servico, "_cliente", DataJudClient(api_key="teste", session=sessao, tentativas=2))
        monkeypatch.setattr("consulta.datajud.time.sleep", lambda s: None)
        return sessao
    return _usar


client = TestClient(main.app)


def test_health():
    assert client.get("/api/health").json() == {"status": "ok"}


def test_consulta_processo(usar_sessao):
    sessao = usar_sessao(RespostaFalsa(200, FIXTURE))
    r = client.get(f"/api/processos/{NUMERO}")
    assert r.status_code == 200
    dados = r.json()
    assert dados["numero"] == NUMERO
    assert dados["tribunal"] == "TRF1"
    inst = dados["instancias"][0]
    assert inst["grau"] == "Juizado Especial"
    assert inst["classe"] == "Procedimento do Juizado Especial Cível"
    assert inst["assuntos"] == ["Concessão"]
    assert inst["data_ajuizamento"] == "2018-10-29"
    assert inst["total_movimentos"] == 3
    # movimentos em ordem do mais recente para o mais antigo
    assert [m["nome"] for m in inst["ultimos_movimentos"]] == ["Ato ordinatório", "Definitivo", "Documento"]
    assert inst["ultimos_movimentos"][2]["complementos"] == ["Outros documentos"]

    url, kwargs = sessao.chamadas[0]
    assert url.endswith("/api_publica_trf1/_search")
    assert kwargs["headers"]["Authorization"] == "APIKey teste"
    assert kwargs["json"] == {"query": {"match": {"numeroProcesso": "00008323520184013202"}}}


def test_processo_nao_encontrado(usar_sessao):
    usar_sessao(RespostaFalsa(200, {"hits": {"hits": []}}))
    r = client.get(f"/api/processos/{NUMERO}")
    assert r.status_code == 404


def test_numero_invalido_nao_chama_datajud(usar_sessao):
    sessao = usar_sessao()
    r = client.get("/api/processos/0000832-99.2018.4.01.3202")
    assert r.status_code == 422
    assert sessao.chamadas == []


def test_tentativa_extra_quando_datajud_da_timeout(usar_sessao):
    sessao = usar_sessao(requests.Timeout("lento"), RespostaFalsa(200, FIXTURE))
    assert client.get(f"/api/processos/{NUMERO}").status_code == 200
    assert len(sessao.chamadas) == 2


def test_datajud_fora_do_ar(usar_sessao):
    usar_sessao(RespostaFalsa(504), RespostaFalsa(504))
    r = client.get(f"/api/processos/{NUMERO}")
    assert r.status_code == 503


def test_chave_recusada(usar_sessao):
    usar_sessao(RespostaFalsa(401))
    r = client.get(f"/api/processos/{NUMERO}")
    assert r.status_code == 503
    assert "DATAJUD_API_KEY" in r.json()["detail"]
