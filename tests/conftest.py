import json
from pathlib import Path

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

NUMERO = "0000832-35.2018.4.01.3202"
FIXTURE = json.loads((Path(__file__).parent / "fixtures" / "datajud_trf1.json").read_text(encoding="utf-8"))


class ModeloRoteirizado(BaseChatModel):
    """Chat model falso: devolve as respostas na ordem dada e guarda o que recebeu."""

    respostas: list
    recebidas: list = []
    posicao: int = 0

    @property
    def _llm_type(self) -> str:
        return "roteirizado"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.recebidas.append(list(messages))
        resposta = self.respostas[self.posicao]
        self.posicao += 1
        return ChatResult(generations=[ChatGeneration(message=resposta)])


def numero_valido(sequencial: str = "0000001", ano: str = "2024", segmento: str = "8", tribunal: str = "12", origem: str = "0001") -> str:
    """Gera um número CNJ com dígito verificador correto."""
    dv = 98 - int(sequencial + ano + segmento + tribunal + origem + "00") % 97
    return f"{sequencial}-{dv:02d}.{ano}.{segmento}.{tribunal}.{origem}"


def chamada(numero: str, id_: str = "c1") -> AIMessage:
    return AIMessage(content="", tool_calls=[{"name": "consultar_processo", "args": {"numero": numero}, "id": id_}])


@pytest.fixture
def servico_falso(monkeypatch):
    """Substitui a consulta ao DataJud: o processo de exemplo existe, os demais não."""
    from consulta import servico
    from consulta.datajud import resumir_instancia

    chamados = []

    def consultar(numero):
        chamados.append(numero)
        n = servico.parse_numero(numero)
        if n.digitos != "00008323520184013202":
            raise servico.ProcessoNaoEncontrado(f"Processo {n.formatado} não encontrado no DataJud.")
        fonte = FIXTURE["hits"]["hits"][0]["_source"]
        return {"numero": n.formatado, "tribunal": "TRF1", "instancias": [resumir_instancia(fonte)]}

    monkeypatch.setattr(servico, "consultar_processo", consultar)
    return chamados


@pytest.fixture(autouse=True)
def limitador_zerado(monkeypatch):
    """Cada teste começa com os contadores de uso do chat zerados."""
    import api.main as main
    from api.limites import Limitador

    monkeypatch.setattr(main, "limitador", Limitador.do_ambiente())


@pytest.fixture(autouse=True)
def chave_do_servidor(monkeypatch):
    """Por padrão, o servidor tem chave própria do LLM. Os testes do modo "traga sua chave" a removem."""
    monkeypatch.setenv("LLM_API_KEY", "chave-do-servidor-de-teste")
