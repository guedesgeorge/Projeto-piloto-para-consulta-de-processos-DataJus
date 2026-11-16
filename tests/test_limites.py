"""Testa o limite de uso do chat (api/limites.py e a rota /api/chat)."""
import pytest
from fastapi.testclient import TestClient

import api.main as main
from api.limites import DIA, HORA, Limitador, ip_do_visitante

client = TestClient(main.app)


class Relogio:
    def __init__(self):
        self.agora = 1_000.0

    def __call__(self):
        return self.agora


def test_bloqueia_depois_do_teto_por_hora_e_libera_depois():
    relogio = Relogio()
    lim = Limitador(por_ip_hora=2, por_ip_dia=0, global_dia=0, relogio=relogio)
    assert lim.registrar("1.1.1.1") is None
    relogio.agora += 10
    assert lim.registrar("1.1.1.1") is None

    bloqueio = lim.registrar("1.1.1.1")
    assert bloqueio is not None
    assert "2 mensagens por hora" in bloqueio.mensagem
    assert bloqueio.tentar_em == HORA - 10  # a mensagem mais antiga sai da janela primeiro

    relogio.agora += HORA - 10
    assert lim.registrar("1.1.1.1") is None


def test_visitantes_tem_contadores_separados():
    lim = Limitador(por_ip_hora=1, por_ip_dia=0, global_dia=0, relogio=Relogio())
    assert lim.registrar("1.1.1.1") is None
    assert lim.registrar("2.2.2.2") is None
    assert lim.registrar("1.1.1.1") is not None


def test_teto_por_dia():
    relogio = Relogio()
    lim = Limitador(por_ip_hora=0, por_ip_dia=2, global_dia=0, relogio=relogio)
    lim.registrar("1.1.1.1")
    relogio.agora += 2 * HORA
    lim.registrar("1.1.1.1")
    relogio.agora += 2 * HORA
    bloqueio = lim.registrar("1.1.1.1")
    assert bloqueio and "por dia" in bloqueio.mensagem
    relogio.agora += DIA
    assert lim.registrar("1.1.1.1") is None


def test_teto_global_vale_para_todos():
    lim = Limitador(por_ip_hora=0, por_ip_dia=0, global_dia=2, relogio=Relogio())
    assert lim.registrar("1.1.1.1") is None
    assert lim.registrar("2.2.2.2") is None
    bloqueio = lim.registrar("3.3.3.3")
    assert bloqueio and "limite diário" in bloqueio.mensagem


def test_mensagem_bloqueada_nao_conta():
    relogio = Relogio()
    lim = Limitador(por_ip_hora=1, por_ip_dia=0, global_dia=2, relogio=relogio)
    lim.registrar("1.1.1.1")
    for _ in range(5):
        assert lim.registrar("1.1.1.1") is not None
    assert lim.registrar("2.2.2.2") is None  # as tentativas bloqueadas não gastaram o teto global


def test_zero_desliga_os_tetos():
    lim = Limitador(por_ip_hora=0, por_ip_dia=0, global_dia=0, relogio=Relogio())
    assert all(lim.registrar("1.1.1.1") is None for _ in range(1000))


def test_limites_vem_do_ambiente(monkeypatch):
    monkeypatch.setenv("LIMITE_IP_HORA", "3")
    monkeypatch.setenv("LIMITE_IP_DIA", "abc")  # valor inválido cai no padrão
    monkeypatch.setenv("LIMITE_GLOBAL_DIA", "0")
    lim = Limitador.do_ambiente()
    assert lim.tetos_ip[0][0] == 3
    assert lim.tetos_ip[1][0] == 60
    assert lim.global_dia == 0


@pytest.mark.parametrize("confiar, cabecalho, esperado", [
    ("", "9.9.9.9", "10.0.0.1"),                  # sem CONFIAR_PROXY, ignora o cabeçalho
    ("1", "9.9.9.9", "9.9.9.9"),
    ("1", "6.6.6.6, 9.9.9.9", "9.9.9.9"),          # usa o último: o primeiro pode ser forjado
    ("1", None, "10.0.0.1"),
])
def test_ip_do_visitante(monkeypatch, confiar, cabecalho, esperado):
    monkeypatch.setenv("CONFIAR_PROXY", confiar)
    assert ip_do_visitante(cabecalho, "10.0.0.1") == esperado


def test_chat_responde_429_quando_estoura(monkeypatch):
    monkeypatch.setattr(main, "limitador", Limitador(por_ip_hora=1, por_ip_dia=0, global_dia=0))
    monkeypatch.delenv("LLM_MODELOS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setattr(main, "obter_agente", lambda nome: object())
    monkeypatch.setattr(main.ag, "transmitir", lambda agente, mensagens: iter([{"tipo": "texto", "delta": "oi"}]))

    corpo = {"mensagens": [{"papel": "user", "texto": "Olá"}]}
    assert client.post("/api/chat", json=corpo).status_code == 200

    r = client.post("/api/chat", json=corpo)
    assert r.status_code == 429
    assert "limite" in r.json()["detail"]
    assert int(r.headers["Retry-After"]) > 0


def test_requisicao_invalida_nao_gasta_o_limite(monkeypatch):
    monkeypatch.setattr(main, "limitador", Limitador(por_ip_hora=1, por_ip_dia=0, global_dia=0))
    r = client.post("/api/chat", json={"mensagens": [{"papel": "assistant", "texto": "x"}]})
    assert r.status_code == 422
    assert main.limitador.registrar("testclient") is None
