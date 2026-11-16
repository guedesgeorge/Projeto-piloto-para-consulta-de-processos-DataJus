"""Testa o agente sem chamar o LLM de verdade nem o DataJud."""
import json

import pytest
from langchain_core.messages import AIMessage

import agente.agente as ag
from tests.conftest import NUMERO, ModeloRoteirizado, chamada, numero_valido


def test_agente_chama_ferramenta_e_responde(servico_falso):
    modelo = ModeloRoteirizado(respostas=[chamada(NUMERO), AIMessage(content="É um Procedimento do Juizado Especial Cível, no TRF1.")])
    r = ag.perguntar(ag.criar_agente(modelo), f"Qual a classe do processo {NUMERO}?")

    assert servico_falso == [NUMERO]
    assert r.texto == "É um Procedimento do Juizado Especial Cível, no TRF1."
    assert r.consultas[0]["numero"] == NUMERO
    assert r.consultas[0]["ok"] is True
    assert json.loads(r.consultas[0]["resultado"])["tribunal"] == "TRF1"


def test_eventos_saem_na_ordem_certa(servico_falso):
    modelo = ModeloRoteirizado(respostas=[chamada(NUMERO), AIMessage(content="Resposta.")])
    mensagens = ag.montar_mensagens([{"papel": "user", "texto": f"Processo {NUMERO}?"}])
    tipos = [e["tipo"] for e in ag.transmitir(ag.criar_agente(modelo), mensagens)]
    assert tipos == ["consulta_inicio", "consulta", "texto"]


def test_consulta_com_erro_fica_marcada(servico_falso):
    outro = numero_valido()  # válido, mas inexistente no DataJud simulado
    modelo = ModeloRoteirizado(respostas=[chamada(outro), AIMessage(content="Não encontrei esse processo.")])
    r = ag.perguntar(ag.criar_agente(modelo), f"E o processo {outro}?")
    assert r.consultas[0]["ok"] is False
    assert r.consultas[0]["resultado"].startswith("Erro: Processo")


def test_numero_invalido_vira_erro_para_o_modelo():
    assert ag.consultar_processo.invoke({"numero": "123"}).startswith("Erro: Número de processo deve ter 20 dígitos")


def test_historico_e_anexos_chegam_ao_modelo(servico_falso):
    modelo = ModeloRoteirizado(respostas=[AIMessage(content="Segunda resposta.")])
    historico = [
        {"papel": "user", "texto": "Primeira pergunta"},
        {"papel": "assistant", "texto": "Primeira resposta"},
        {"papel": "user", "texto": "O que diz este documento?",
         "anexos": [{"nome": "intimacao.pdf", "numeros": [NUMERO], "texto": "Fica intimada a parte..."}]},
    ]
    list(ag.transmitir(ag.criar_agente(modelo), ag.montar_mensagens(historico)))

    recebidas = modelo.recebidas[0]
    conteudos = [m.content for m in recebidas]
    assert "Primeira pergunta" in conteudos and "Primeira resposta" in conteudos
    ultima = conteudos[-1]
    assert "[Documento anexado: intimacao.pdf]" in ultima
    assert NUMERO in ultima and "Fica intimada a parte..." in ultima


def test_pergunta_sem_numero_nao_consulta(servico_falso):
    modelo = ModeloRoteirizado(respostas=[AIMessage(content="Qual é o número do processo?")])
    r = ag.perguntar(ag.criar_agente(modelo), "Como está meu processo?")
    assert r.consultas == []
    assert servico_falso == []


def test_modelos_disponiveis(monkeypatch):
    monkeypatch.delenv("LLM_MODELOS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    assert ag.modelos_disponiveis() == ["deepseek-flash", "deepseek-v4-pro"]
    monkeypatch.setenv("LLM_MODELOS", "a, b")
    assert ag.modelos_disponiveis() == ["a", "b"]
    monkeypatch.setenv("LLM_MODEL", "b")  # escolhe o padrão sem esconder os outros
    assert ag.modelos_disponiveis() == ["b", "a"]
    monkeypatch.delenv("LLM_MODELOS")
    monkeypatch.setenv("LLM_MODEL", "deepseek-flash")  # .env antigo continua funcionando
    assert ag.modelos_disponiveis() == ["deepseek-flash", "deepseek-v4-pro"]


def test_modelo_deepseek_desliga_modo_de_raciocinio(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "teste")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODELOS", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    m = ag.criar_modelo()
    assert m.model_name == "deepseek-flash"
    assert m.extra_body == {"thinking": {"type": "disabled"}}
    assert ag.criar_modelo("deepseek-v4-pro").model_name == "deepseek-v4-pro"


def test_outro_provedor_nao_recebe_parametro_do_deepseek(monkeypatch):
    monkeypatch.setenv("LLM_API_KEY", "teste")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.openai.com/v1")
    assert ag.criar_modelo("gpt-4o-mini").extra_body is None


def test_sem_chave_da_erro_claro(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        ag.criar_modelo()
