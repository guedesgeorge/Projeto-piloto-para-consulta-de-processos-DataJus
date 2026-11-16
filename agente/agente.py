"""Agente de IA que responde perguntas sobre processos judiciais públicos.

O agente usa um LLM (por padrão, DeepSeek) e uma única ferramenta,
`consultar_processo`. O próprio modelo decide quando a ferramenta é necessária.
"""
import json
import os
from collections.abc import Iterator
from dataclasses import dataclass, field

from dotenv import load_dotenv
from langchain.agents import create_agent
from langchain_core.messages import AIMessage, AIMessageChunk, HumanMessage, ToolMessage
from langchain_core.tools import tool

from consulta import servico

load_dotenv()

SYSTEM_PROMPT = """Você é um assistente que consulta processos judiciais públicos brasileiros.

Regras:
- Para qualquer pergunta sobre um processo específico, use a ferramenta consultar_processo com o número informado.
- Responda somente com base no que a ferramenta retornar. Nunca invente andamentos, datas, classes ou decisões.
- Se o usuário não informar o número do processo, peça o número no formato NNNNNNN-DD.AAAA.J.TR.OOOO.
- Os dados são metadados públicos do DataJud (CNJ): não incluem nomes das partes nem o conteúdo das decisões. Se perguntarem isso, explique a limitação.
- Quando a mensagem trouxer o texto de um documento anexado, você pode usá-lo para responder sobre o documento, deixando claro o que veio do documento e o que veio do DataJud.
- Se a ferramenta retornar erro, explique o problema ao usuário em linguagem simples.
- Se a pergunta não for sobre processos judiciais ou documentos jurídicos anexados, diga que não consegue ajudar com esse assunto.
- Responda em português, de forma objetiva. Escreva datas no formato DD/MM/AAAA."""


@tool
def consultar_processo(numero: str) -> str:
    """Consulta um processo judicial público pelo número único CNJ (formato NNNNNNN-DD.AAAA.J.TR.OOOO).

    Retorna tribunal, grau, classe, assuntos, órgão julgador, data de ajuizamento
    e os movimentos mais recentes de cada instância do processo.
    """
    try:
        return json.dumps(servico.consultar_processo(numero), ensure_ascii=False)
    except (servico.NumeroInvalido, servico.TribunalNaoSuportado,
            servico.ProcessoNaoEncontrado, servico.DataJudIndisponivel) as e:
        return f"Erro: {e}"


# ---------------------------------------------------------------- modelos

def modelos_disponiveis() -> list[str]:
    """Modelos que o usuário pode escolher (o primeiro é o padrão).

    LLM_MODELOS define a lista; LLM_MODEL (opcional) escolhe qual vem primeiro.
    """
    lista = os.getenv("LLM_MODELOS") or "deepseek-flash,deepseek-v4-pro"
    modelos = [m.strip() for m in lista.split(",") if m.strip()]
    padrao = (os.getenv("LLM_MODEL") or "").strip()
    if padrao:
        modelos = [padrao] + [m for m in modelos if m != padrao]
    return modelos


def criar_modelo(nome: str | None = None):
    """Cria o LLM a partir do .env. Funciona com qualquer API compatível com a da OpenAI."""
    from langchain_openai import ChatOpenAI

    chave = os.getenv("LLM_API_KEY")
    if not chave:
        raise RuntimeError("Defina LLM_API_KEY no arquivo .env (chave da API do DeepSeek ou de outro provedor).")

    base_url = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    extra = {}
    if "deepseek" in base_url:
        # Modo sem raciocínio: mais rápido e barato, e suficiente para consultar e resumir.
        extra["extra_body"] = {"thinking": {"type": "disabled"}}

    return ChatOpenAI(
        model=nome or modelos_disponiveis()[0],
        api_key=chave,
        base_url=base_url,
        temperature=0,
        timeout=120,
        **extra,
    )


def criar_agente(modelo=None, nome_modelo: str | None = None):
    """Cria o agente. `modelo` permite injetar outro chat model (usado nos testes)."""
    return create_agent(modelo or criar_modelo(nome_modelo), tools=[consultar_processo], system_prompt=SYSTEM_PROMPT)


# ---------------------------------------------------------------- conversa

def descrever_anexo(anexo: dict) -> str:
    """Texto que acompanha a mensagem do usuário quando ele anexa um PDF."""
    numeros = ", ".join(anexo.get("numeros") or []) or "nenhum número válido encontrado"
    partes = [
        f"[Documento anexado: {anexo.get('nome', 'documento.pdf')}]",
        f"Números de processo encontrados no documento (já validados): {numeros}",
    ]
    if anexo.get("texto"):
        aviso = " (trecho inicial; o documento é maior)" if anexo.get("texto_truncado") else ""
        partes.append(f"Texto extraído do documento{aviso}:\n\"\"\"\n{anexo['texto']}\n\"\"\"")
    else:
        partes.append("O PDF não tem texto extraível (provavelmente é uma imagem digitalizada).")
    return "\n".join(partes)


def montar_mensagens(historico: list[dict]) -> list:
    """Converte [{'papel': 'user'|'assistant', 'texto': ..., 'anexos': [...]}] em mensagens do LangChain."""
    mensagens = []
    for m in historico:
        if m["papel"] == "user":
            texto = m.get("texto", "")
            for anexo in m.get("anexos") or []:
                texto += "\n\n" + descrever_anexo(anexo)
            mensagens.append(HumanMessage(texto.strip()))
        elif m["papel"] == "assistant" and m.get("texto"):
            mensagens.append(AIMessage(m["texto"]))
    return mensagens


def transmitir(agente, mensagens: list) -> Iterator[dict]:
    """Executa o agente e devolve eventos à medida que acontecem:

    {"tipo": "consulta_inicio", "id", "numero"}   o agente decidiu consultar um processo
    {"tipo": "consulta", "id", "ok", "resultado"}  a consulta terminou
    {"tipo": "texto", "delta"}                     pedaço da resposta final
    """
    for modo, dado in agente.stream({"messages": mensagens}, stream_mode=["messages", "updates"]):
        if modo == "messages":
            msg, meta = dado
            if meta.get("langgraph_node") == "model" and isinstance(msg, (AIMessage, AIMessageChunk)):
                if isinstance(msg.content, str) and msg.content:
                    yield {"tipo": "texto", "delta": msg.content}
        else:
            for no, atualizacao in dado.items():
                for msg in (atualizacao or {}).get("messages", []):
                    if no == "model" and isinstance(msg, AIMessage):
                        for c in msg.tool_calls:
                            yield {"tipo": "consulta_inicio", "id": c["id"], "numero": c["args"].get("numero", "")}
                    elif no == "tools" and isinstance(msg, ToolMessage):
                        yield {"tipo": "consulta", "id": msg.tool_call_id,
                               "ok": not msg.content.startswith("Erro"), "resultado": msg.content}


@dataclass
class Resposta:
    texto: str
    consultas: list[dict] = field(default_factory=list)


def perguntar(agente, pergunta: str, historico: list[dict] | None = None) -> Resposta:
    """Versão sem streaming: envia uma pergunta e devolve a resposta completa."""
    mensagens = montar_mensagens((historico or []) + [{"papel": "user", "texto": pergunta}])
    texto, consultas = "", {}
    for ev in transmitir(agente, mensagens):
        if ev["tipo"] == "texto":
            texto += ev["delta"]
        elif ev["tipo"] == "consulta_inicio":
            consultas[ev["id"]] = {"numero": ev["numero"]}
        elif ev["tipo"] == "consulta":
            consultas.setdefault(ev["id"], {}).update(ok=ev["ok"], resultado=ev["resultado"])
    return Resposta(texto=texto, consultas=list(consultas.values()))
