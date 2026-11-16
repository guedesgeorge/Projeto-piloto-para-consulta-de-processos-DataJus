"""Ponto único de consulta de processos, usado pela API e pela ferramenta do agente."""
from .datajud import DataJudClient, DataJudIndisponivel
from .numero_cnj import NumeroInvalido, TribunalNaoSuportado, alias_tribunal, parse_numero

__all__ = [
    "consultar_processo", "ProcessoNaoEncontrado",
    "NumeroInvalido", "TribunalNaoSuportado", "DataJudIndisponivel",
]


class ProcessoNaoEncontrado(LookupError):
    """O processo não existe no DataJud ou está sob sigilo."""


_cliente: DataJudClient | None = None


def cliente() -> DataJudClient:
    global _cliente
    if _cliente is None:
        _cliente = DataJudClient()
    return _cliente


def consultar_processo(numero: str) -> dict:
    """Valida o número, consulta o DataJud e devolve o resumo do processo.

    Exceções: NumeroInvalido, TribunalNaoSuportado, DataJudIndisponivel, ProcessoNaoEncontrado.
    """
    n = parse_numero(numero)
    alias = alias_tribunal(n)
    instancias = cliente().consultar(n)
    if not instancias:
        raise ProcessoNaoEncontrado(
            f"Processo {n.formatado} não encontrado no DataJud ({alias.upper()}). "
            "Processos sob sigilo não aparecem na API pública."
        )
    return {"numero": n.formatado, "tribunal": alias.upper(), "instancias": instancias}
