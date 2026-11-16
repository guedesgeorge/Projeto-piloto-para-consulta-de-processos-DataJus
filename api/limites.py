"""Limite de uso do chat, para proteger a chave do LLM quando o app fica público.

Três tetos, configuráveis pelo ambiente (0 desliga o teto):

    LIMITE_IP_HORA     mensagens por visitante por hora     (padrão 20)
    LIMITE_IP_DIA      mensagens por visitante por dia      (padrão 60)
    LIMITE_GLOBAL_DIA  mensagens de todos somados por dia   (padrão 150)

Os contadores ficam em memória: zeram quando o servidor reinicia e não são
compartilhados entre réplicas. Para um app de uma instância só (Docker local ou
um serviço de hospedagem com uma instância) isso basta.
"""
import math
import os
import threading
import time
from collections import deque
from dataclasses import dataclass

HORA = 3600
DIA = 86_400


def _ler_int(nome: str, padrao: int) -> int:
    valor = os.getenv(nome, "").strip()
    try:
        return max(0, int(valor)) if valor else padrao
    except ValueError:
        return padrao


@dataclass
class Bloqueio:
    mensagem: str
    tentar_em: int  # segundos até liberar


class Limitador:
    def __init__(self, por_ip_hora: int, por_ip_dia: int, global_dia: int, relogio=time.monotonic):
        self.tetos_ip = [(por_ip_hora, HORA, "por hora"), (por_ip_dia, DIA, "por dia")]
        self.global_dia = global_dia
        self.relogio = relogio
        self._por_ip: dict[str, deque] = {}
        self._global: deque = deque()
        self._trava = threading.Lock()

    @classmethod
    def do_ambiente(cls) -> "Limitador":
        return cls(
            por_ip_hora=_ler_int("LIMITE_IP_HORA", 20),
            por_ip_dia=_ler_int("LIMITE_IP_DIA", 60),
            global_dia=_ler_int("LIMITE_GLOBAL_DIA", 150),
        )

    @staticmethod
    def _limpar(fila: deque, agora: float, janela: int) -> None:
        while fila and agora - fila[0] >= janela:
            fila.popleft()

    @staticmethod
    def _contar(fila: deque, agora: float, janela: int) -> int:
        return sum(1 for t in fila if agora - t < janela)

    def registrar(self, ip: str) -> Bloqueio | None:
        """Conta uma mensagem do visitante. Devolve um Bloqueio se algum teto estourou."""
        with self._trava:
            agora = self.relogio()
            fila = self._por_ip.setdefault(ip, deque())
            self._limpar(fila, agora, DIA)
            self._limpar(self._global, agora, DIA)

            for teto, janela, rotulo in self.tetos_ip:
                if teto and self._contar(fila, agora, janela) >= teto:
                    recentes = [t for t in fila if agora - t < janela]
                    espera = math.ceil(janela - (agora - recentes[-teto]))
                    return Bloqueio(
                        f"Você atingiu o limite de {teto} mensagens {rotulo} desta demonstração. "
                        f"Tente de novo em {_formatar(espera)}.",
                        espera,
                    )

            if self.global_dia and len(self._global) >= self.global_dia:
                espera = math.ceil(DIA - (agora - self._global[0]))
                return Bloqueio(
                    "A demonstração atingiu o limite diário de uso. Tente de novo amanhã, "
                    "ou rode o projeto na sua máquina (instruções no GitHub).",
                    espera,
                )

            fila.append(agora)
            self._global.append(agora)
            # descarta visitantes sem mensagens no último dia, para a memória não crescer
            if len(self._por_ip) > 10_000:
                self._por_ip = {k: v for k, v in self._por_ip.items() if v}
            return None


def _formatar(segundos: int) -> str:
    if segundos < 90:
        return f"{max(1, segundos)} segundos"
    minutos = math.ceil(segundos / 60)
    if minutos < 90:
        return f"{minutos} minutos"
    return f"{math.ceil(minutos / 60)} horas"


def ip_do_visitante(cabecalho_forwarded: str | None, ip_conexao: str | None) -> str:
    """Identifica o visitante.

    Atrás de um proxy (como o de um serviço de hospedagem), a conexão vem sempre do proxy e o IP
    real chega no X-Forwarded-For. Com CONFIAR_PROXY=1, usamos o último endereço da
    lista, que é o que o proxy viu. Os anteriores podem ter sido escritos pelo próprio
    visitante para burlar o limite.
    """
    if os.getenv("CONFIAR_PROXY", "").strip() in {"1", "true", "sim"} and cabecalho_forwarded:
        ultimo = cabecalho_forwarded.split(",")[-1].strip()
        if ultimo:
            return ultimo
    return ip_conexao or "desconhecido"
