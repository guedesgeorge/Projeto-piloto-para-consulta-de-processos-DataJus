"""Cliente da API pública do DataJud (CNJ).

Documentação oficial: https://datajud-wiki.cnj.jus.br/api-publica/
A API devolve apenas metadados de processos públicos: não traz nomes das
partes nem o conteúdo das decisões.
"""
import os
import time
from datetime import datetime

import requests

from .numero_cnj import NumeroCNJ, alias_tribunal

BASE_URL = "https://api-publica.datajud.cnj.jus.br"

GRAUS = {
    "G1": "1º grau",
    "G2": "2º grau",
    "JE": "Juizado Especial",
    "TR": "Turma Recursal",
    "SUP": "Tribunal Superior",
    "TRU": "Turma Regional de Uniformização",
    "TNU": "Turma Nacional de Uniformização",
}


class DataJudIndisponivel(RuntimeError):
    """A API do DataJud não respondeu ou retornou erro."""


def _data(valor: str | None) -> str | None:
    """Converte '20181029000000' ou '2018-10-29T00:00:00Z' para '2018-10-29'."""
    if not valor:
        return None
    if valor[:8].isdigit() and len(valor) >= 8:
        return f"{valor[0:4]}-{valor[4:6]}-{valor[6:8]}"
    try:
        return datetime.fromisoformat(valor.replace("Z", "+00:00")).date().isoformat()
    except ValueError:
        return valor


def resumir_instancia(fonte: dict, max_movimentos: int = 5) -> dict:
    """Transforma um documento bruto do DataJud num resumo enxuto."""
    movimentos = sorted(fonte.get("movimentos") or [], key=lambda m: m.get("dataHora", ""), reverse=True)
    return {
        "tribunal": fonte.get("tribunal"),
        "grau": GRAUS.get(fonte.get("grau"), fonte.get("grau")),
        "classe": (fonte.get("classe") or {}).get("nome"),
        "assuntos": [a.get("nome") for a in fonte.get("assuntos") or [] if a.get("nome")],
        "orgao_julgador": (fonte.get("orgaoJulgador") or {}).get("nome"),
        "data_ajuizamento": _data(fonte.get("dataAjuizamento")),
        "sistema": (fonte.get("sistema") or {}).get("nome"),
        "formato": (fonte.get("formato") or {}).get("nome"),
        "ultima_atualizacao": _data(fonte.get("dataHoraUltimaAtualizacao")),
        "total_movimentos": len(movimentos),
        "ultimos_movimentos": [
            {
                "data": _data(m.get("dataHora")),
                "nome": m.get("nome"),
                "complementos": [c.get("nome") for c in m.get("complementosTabelados") or [] if c.get("nome")],
            }
            for m in movimentos[:max_movimentos]
        ],
    }


class DataJudClient:
    def __init__(self, api_key: str | None = None, base_url: str | None = None,
                 timeout: float = 90, tentativas: int = 2, session: requests.Session | None = None):
        self.api_key = api_key or os.getenv("DATAJUD_API_KEY", "")
        if not self.api_key:
            raise ValueError("Defina DATAJUD_API_KEY (chave pública em https://datajud-wiki.cnj.jus.br/api-publica/acesso)")
        self.base_url = (base_url or os.getenv("DATAJUD_URL") or BASE_URL).rstrip("/")
        self.timeout = timeout
        self.tentativas = tentativas
        self.session = session or requests.Session()

    def buscar(self, numero: NumeroCNJ) -> list[dict]:
        """Retorna os documentos brutos do processo (um por grau/instância)."""
        url = f"{self.base_url}/api_publica_{alias_tribunal(numero)}/_search"
        corpo = {"query": {"match": {"numeroProcesso": numero.digitos}}}
        cabecalhos = {"Authorization": f"APIKey {self.api_key}", "Content-Type": "application/json"}

        ultimo_erro = "sem resposta"
        for tentativa in range(self.tentativas):
            try:
                r = self.session.post(url, json=corpo, headers=cabecalhos, timeout=self.timeout)
            except requests.RequestException as e:
                ultimo_erro = str(e)
            else:
                if r.status_code == 200:
                    return [h["_source"] for h in r.json().get("hits", {}).get("hits", [])]
                if r.status_code in (401, 403):
                    raise DataJudIndisponivel(
                        "DataJud recusou a chave de acesso. A chave pública pode ter mudado: "
                        "atualize DATAJUD_API_KEY com a da wiki do CNJ."
                    )
                ultimo_erro = f"HTTP {r.status_code}"
                if r.status_code < 500:
                    break
            if tentativa + 1 < self.tentativas:
                time.sleep(2)
        raise DataJudIndisponivel(f"Falha ao consultar o DataJud ({ultimo_erro}).")

    def consultar(self, numero: NumeroCNJ) -> list[dict]:
        """Retorna o resumo de cada instância do processo (lista vazia se não encontrado)."""
        return [resumir_instancia(fonte) for fonte in self.buscar(numero)]
