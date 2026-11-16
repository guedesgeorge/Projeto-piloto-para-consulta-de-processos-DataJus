"""Leitura de PDFs anexados: extrai o texto e os números de processo válidos."""
import io
import re

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from .numero_cnj import NumeroInvalido, parse_numero

# Aceita o formato com pontuação (com ou sem espaços) ou 20 dígitos seguidos
PADRAO_NUMERO = re.compile(
    r"\b\d{7}\s*-\s*\d{2}\s*\.\s*\d{4}\s*\.\s*\d\s*\.\s*\d{2}\s*\.\s*\d{4}\b|\b\d{20}\b"
)

LIMITE_TEXTO = 6000  # caracteres enviados ao modelo
LIMITE_PAGINAS = 30


class AnexoInvalido(ValueError):
    """O arquivo não é um PDF legível."""


def numeros_no_texto(texto: str) -> list[str]:
    """Retorna os números de processo válidos (dígito verificador correto), sem repetição."""
    encontrados = []
    for trecho in PADRAO_NUMERO.findall(texto):
        try:
            formatado = parse_numero(trecho).formatado
        except NumeroInvalido:
            continue
        if formatado not in encontrados:
            encontrados.append(formatado)
    return encontrados


def ler_pdf(conteudo: bytes) -> dict:
    try:
        leitor = PdfReader(io.BytesIO(conteudo))
        paginas = [p.extract_text() or "" for p in leitor.pages[:LIMITE_PAGINAS]]
    except (PdfReadError, ValueError, OSError) as e:
        raise AnexoInvalido(f"Não foi possível ler o PDF ({e}).")

    texto = re.sub(r"[ \t]+", " ", "\n".join(paginas)).strip()
    return {
        "paginas": len(leitor.pages),
        "numeros": numeros_no_texto(texto),
        "texto": texto[:LIMITE_TEXTO],
        "texto_truncado": len(texto) > LIMITE_TEXTO,
        "tem_texto": bool(texto),
    }
