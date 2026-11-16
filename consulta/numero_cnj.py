"""Validação do número único de processo (Resolução CNJ nº 65/2008) e
identificação do tribunal correspondente na API pública do DataJud.

Formato: NNNNNNN-DD.AAAA.J.TR.OOOO
  N = número sequencial   D = dígito verificador   A = ano
  J = segmento da Justiça TR = tribunal             O = origem
"""
import re
from dataclasses import dataclass

# Ordem oficial das UFs usada nos códigos TR da Justiça Estadual e Eleitoral
UFS = [
    "ac", "al", "ap", "am", "ba", "ce", "df", "es", "go", "ma", "mt", "ms", "mg", "pa",
    "pb", "pr", "pe", "pi", "rj", "rn", "rs", "ro", "rr", "sc", "se", "sp", "to",
]

# Justiça Militar Estadual: só MG, RS e SP têm tribunal próprio
TJM = {"13": "tjmmg", "21": "tjmrs", "26": "tjmsp"}


class NumeroInvalido(ValueError):
    """O texto não é um número de processo CNJ válido."""


class TribunalNaoSuportado(ValueError):
    """O tribunal do processo não está disponível na API pública do DataJud."""


@dataclass(frozen=True)
class NumeroCNJ:
    digitos: str  # 20 dígitos, sem pontuação

    @property
    def formatado(self) -> str:
        d = self.digitos
        return f"{d[0:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:20]}"

    @property
    def segmento(self) -> str:
        return self.digitos[13]

    @property
    def tribunal(self) -> str:
        return self.digitos[14:16]


def _digito_verificador(d: str) -> int:
    base = d[0:7] + d[9:13] + d[13] + d[14:16] + d[16:20] + "00"
    return 98 - int(base) % 97


def parse_numero(texto: str) -> NumeroCNJ:
    """Normaliza e valida um número de processo, com ou sem pontuação."""
    digitos = re.sub(r"\D", "", texto or "")
    if len(digitos) != 20:
        raise NumeroInvalido(
            f"Número de processo deve ter 20 dígitos (formato NNNNNNN-DD.AAAA.J.TR.OOOO); recebido: {texto!r}"
        )
    if int(digitos[7:9]) != _digito_verificador(digitos):
        raise NumeroInvalido(f"Dígito verificador inválido no número {texto!r}")
    return NumeroCNJ(digitos)


def alias_tribunal(numero: NumeroCNJ) -> str:
    """Retorna o alias do tribunal na API do DataJud (ex.: 'tjms', 'trf1', 'tre-sp')."""
    j, tr = numero.segmento, numero.tribunal
    n = int(tr)

    if j == "3" and tr == "00":
        return "stj"
    if j == "4" and 1 <= n <= 6:
        return f"trf{n}"
    if j == "5":
        if tr == "00":
            return "tst"
        if 1 <= n <= 24:
            return f"trt{n}"
    if j == "6":
        if tr == "00":
            return "tse"
        if 1 <= n <= 27:
            uf = UFS[n - 1]
            return "tre-dft" if uf == "df" else f"tre-{uf}"
    if j == "7" and tr == "00":
        return "stm"
    if j == "8" and 1 <= n <= 27:
        uf = UFS[n - 1]
        return "tjdft" if uf == "df" else f"tj{uf}"
    if j == "9" and tr in TJM:
        return TJM[tr]

    if j in ("1", "2"):
        raise TribunalNaoSuportado("Processos do STF e do CNJ não estão na API pública do DataJud.")
    raise TribunalNaoSuportado(f"Segmento {j} / tribunal {tr} não reconhecido no número {numero.formatado}.")
