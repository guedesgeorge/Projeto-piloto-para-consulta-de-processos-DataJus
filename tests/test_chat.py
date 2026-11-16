"""Testa as rotas /api/chat (streaming) e /api/anexos (PDF)."""
import io
import json

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage
from reportlab.pdfgen import canvas

import agente.agente as ag
import api.main as main
from tests.conftest import NUMERO, ModeloRoteirizado, chamada

client = TestClient(main.app)


def eventos(resposta) -> list[dict]:
    return [json.loads(linha[6:]) for linha in resposta.text.splitlines() if linha.startswith("data: ")]


@pytest.fixture
def agente_roteirizado(monkeypatch):
    def usar(*respostas):
        modelo = ModeloRoteirizado(respostas=list(respostas))
        monkeypatch.setattr(main, "_agentes", {"deepseek-flash": ag.criar_agente(modelo)})
        return modelo
    monkeypatch.delenv("LLM_MODELOS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    return usar


def test_config_lista_modelos(monkeypatch):
    monkeypatch.setenv("LLM_MODELOS", "deepseek-flash,deepseek-v4-pro")
    assert client.get("/api/config").json() == {"modelos": ["deepseek-flash", "deepseek-v4-pro"]}


def test_chat_transmite_consulta_e_resposta(agente_roteirizado, servico_falso):
    agente_roteirizado(chamada(NUMERO), AIMessage(content="Tramita no TRF1."))
    r = client.post("/api/chat", json={"mensagens": [{"papel": "user", "texto": f"Processo {NUMERO}?"}]})

    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")
    evs = eventos(r)
    assert [e["tipo"] for e in evs] == ["consulta_inicio", "consulta", "texto", "fim"]
    assert evs[0]["numero"] == NUMERO
    assert evs[1]["ok"] is True
    assert evs[2]["delta"] == "Tramita no TRF1."


def test_chat_rejeita_modelo_desconhecido(agente_roteirizado):
    r = client.post("/api/chat", json={"modelo": "gpt-qualquer", "mensagens": [{"papel": "user", "texto": "oi"}]})
    assert r.status_code == 422


def test_chat_exige_que_a_ultima_mensagem_seja_do_usuario(agente_roteirizado):
    r = client.post("/api/chat", json={"mensagens": [{"papel": "assistant", "texto": "oi"}]})
    assert r.status_code == 422


def test_chat_sem_chave_do_llm(monkeypatch):
    monkeypatch.setattr(main, "_agentes", {})
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODELOS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    r = client.post("/api/chat", json={"mensagens": [{"papel": "user", "texto": "oi"}]})
    assert r.status_code == 503
    assert "LLM_API_KEY" in r.json()["detail"]


def test_falha_do_llm_vira_evento_de_erro(monkeypatch):
    class Quebrado:
        def stream(self, *a, **k):
            raise RuntimeError("401 saldo insuficiente")
            yield
    monkeypatch.setattr(main, "_agentes", {"deepseek-flash": Quebrado()})
    monkeypatch.delenv("LLM_MODELOS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    evs = eventos(client.post("/api/chat", json={"mensagens": [{"papel": "user", "texto": "oi"}]}))
    assert evs[0]["tipo"] == "erro" and "saldo insuficiente" in evs[0]["mensagem"]
    assert evs[-1]["tipo"] == "fim"


# ------------------------------------------------------------------ anexos

def pdf_com_texto(*linhas: str) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf)
    for i, linha in enumerate(linhas):
        c.drawString(50, 800 - 20 * i, linha)
    c.save()
    return buf.getvalue()


def test_anexo_extrai_numeros_validos():
    pdf = pdf_com_texto(
        "INTIMACAO",
        f"Processo n. {NUMERO}",
        "Referente tambem ao 00008323520184013202 (repetido, sem pontuacao)",
        "Numero com digito errado: 0000832-99.2018.4.01.3202",
    )
    r = client.post("/api/anexos", files={"arquivo": ("intimacao.pdf", pdf, "application/pdf")})
    assert r.status_code == 200
    dados = r.json()
    assert dados["nome"] == "intimacao.pdf"
    assert dados["numeros"] == [NUMERO]
    assert "INTIMACAO" in dados["texto"]
    assert dados["paginas"] == 1


def test_anexo_que_nao_e_pdf():
    r = client.post("/api/anexos", files={"arquivo": ("nota.txt", b"texto", "text/plain")})
    assert r.status_code == 415


def test_anexo_pdf_corrompido():
    r = client.post("/api/anexos", files={"arquivo": ("ruim.pdf", b"%PDF-1.4 lixo", "application/pdf")})
    assert r.status_code == 422
