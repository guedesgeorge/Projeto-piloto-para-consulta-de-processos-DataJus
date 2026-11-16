"""Servidor do projeto: API REST, chat com streaming e a interface web."""
import json
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request, UploadFile
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from agente import agente as ag
from consulta import servico
from consulta.anexos import AnexoInvalido, ler_pdf

from .limites import Limitador, ip_do_visitante

load_dotenv()

app = FastAPI(
    title="Agente de Consulta Processual",
    description="Consulta metadados de processos públicos na API pública do DataJud (CNJ) e conversa sobre eles com um agente de IA.",
    version="3.0.0",
)

MAX_MENSAGENS = 20          # histórico enviado ao modelo
MAX_CARACTERES = 20_000     # por mensagem (texto + anexos)
MAX_PDF_BYTES = 10 * 1024 * 1024

limitador = Limitador.do_ambiente()   # protege a chave do LLM quando o app é público


# ------------------------------------------------------------------ modelos de dados

class Movimento(BaseModel):
    data: str | None
    nome: str | None
    complementos: list[str]


class Instancia(BaseModel):
    tribunal: str | None
    grau: str | None
    classe: str | None
    assuntos: list[str]
    orgao_julgador: str | None
    data_ajuizamento: str | None
    sistema: str | None
    formato: str | None
    ultima_atualizacao: str | None
    total_movimentos: int
    ultimos_movimentos: list[Movimento]


class ProcessoResponse(BaseModel):
    numero: str
    tribunal: str
    instancias: list[Instancia]


class Anexo(BaseModel):
    nome: str
    numeros: list[str] = []
    texto: str = ""
    texto_truncado: bool = False


class Mensagem(BaseModel):
    papel: Literal["user", "assistant"]
    texto: str = Field("", max_length=MAX_CARACTERES)
    anexos: list[Anexo] = Field(default_factory=list, max_length=3)


class ChatRequest(BaseModel):
    mensagens: list[Mensagem] = Field(min_length=1)
    modelo: str | None = None


# ------------------------------------------------------------------ rotas

@app.get("/api/health", tags=["infra"])
def health():
    return {"status": "ok"}


@app.get("/api/config", tags=["infra"])
def config():
    """Modelos disponíveis para o seletor da interface."""
    return {"modelos": ag.modelos_disponiveis()}


# Rotas síncronas de propósito: o FastAPI as executa numa thread separada,
# então uma consulta lenta ao DataJud não trava o servidor.
@app.get("/api/processos/{numero}", response_model=ProcessoResponse, tags=["processos"])
def consultar_processo(numero: str):
    """Consulta um processo pelo número único CNJ (com ou sem pontuação)."""
    try:
        return servico.consultar_processo(numero)
    except servico.NumeroInvalido as e:
        raise HTTPException(status_code=422, detail=str(e))
    except servico.TribunalNaoSuportado as e:
        raise HTTPException(status_code=400, detail=str(e))
    except servico.ProcessoNaoEncontrado as e:
        raise HTTPException(status_code=404, detail=str(e))
    except servico.DataJudIndisponivel as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/api/anexos", tags=["chat"])
def ler_anexo(arquivo: UploadFile):
    """Lê um PDF e devolve o texto e os números de processo válidos encontrados nele."""
    nome = arquivo.filename or "documento.pdf"
    if not nome.lower().endswith(".pdf") and arquivo.content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="Envie um arquivo PDF.")
    conteudo = arquivo.file.read(MAX_PDF_BYTES + 1)
    if len(conteudo) > MAX_PDF_BYTES:
        raise HTTPException(status_code=413, detail="O PDF deve ter no máximo 10 MB.")
    try:
        return {"nome": nome, **ler_pdf(conteudo)}
    except AnexoInvalido as e:
        raise HTTPException(status_code=422, detail=str(e))


_agentes: dict[str, object] = {}


def obter_agente(nome_modelo: str):
    if nome_modelo not in _agentes:
        _agentes[nome_modelo] = ag.criar_agente(nome_modelo=nome_modelo)
    return _agentes[nome_modelo]


def _sse(evento: dict) -> str:
    return f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"


@app.post("/api/chat", tags=["chat"])
def chat(req: ChatRequest, request: Request):
    """Conversa com o agente. A resposta chega aos poucos (Server-Sent Events).

    Eventos: consulta_inicio, consulta, texto, erro e fim.
    """
    modelos = ag.modelos_disponiveis()
    nome_modelo = req.modelo or modelos[0]
    if nome_modelo not in modelos:
        raise HTTPException(status_code=422, detail=f"Modelo não disponível. Opções: {', '.join(modelos)}")
    if req.mensagens[-1].papel != "user":
        raise HTTPException(status_code=422, detail="A última mensagem deve ser do usuário.")

    ip = ip_do_visitante(request.headers.get("x-forwarded-for"), request.client.host if request.client else None)
    bloqueio = limitador.registrar(ip)
    if bloqueio:
        raise HTTPException(status_code=429, detail=bloqueio.mensagem,
                            headers={"Retry-After": str(bloqueio.tentar_em)})

    try:
        agente = obter_agente(nome_modelo)
    except RuntimeError as e:  # chave do LLM ausente
        raise HTTPException(status_code=503, detail=str(e))

    historico = [m.model_dump() for m in req.mensagens[-MAX_MENSAGENS:]]
    mensagens = ag.montar_mensagens(historico)

    def eventos():
        try:
            for evento in ag.transmitir(agente, mensagens):
                yield _sse(evento)
        except Exception as e:  # falha do provedor do LLM (chave, crédito, rede)
            yield _sse({"tipo": "erro", "mensagem": f"Falha ao falar com o modelo de linguagem: {e}"})
        yield _sse({"tipo": "fim"})

    return StreamingResponse(eventos(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# ------------------------------------------------------------------ interface web

PASTA_WEB = Path(__file__).resolve().parent.parent / "web" / "dist"
if PASTA_WEB.is_dir():
    app.mount("/", StaticFiles(directory=PASTA_WEB, html=True), name="web")
