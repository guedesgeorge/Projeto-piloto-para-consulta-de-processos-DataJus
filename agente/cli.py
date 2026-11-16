"""Conversa com o agente pelo terminal.

Uso:
    python -m agente.cli                          # modo conversa
    python -m agente.cli "Em que pé está o processo NNNNNNN-DD.AAAA.J.TR.OOOO?"
"""
import sys

from .agente import criar_agente, montar_mensagens, transmitir


def responder(agente, historico: list[dict]) -> str:
    texto = ""
    for ev in transmitir(agente, montar_mensagens(historico)):
        if ev["tipo"] == "consulta_inicio":
            print(f"  → consultando o processo {ev['numero']} no DataJud…", flush=True)
        elif ev["tipo"] == "consulta":
            print(f"  ← consulta {'concluída' if ev['ok'] else 'com erro'}", flush=True)
        elif ev["tipo"] == "texto":
            if not texto:
                print("\nAgente: ", end="", flush=True)
            print(ev["delta"], end="", flush=True)
            texto += ev["delta"]
    print()
    return texto


def main():
    agente = criar_agente()

    if len(sys.argv) > 1:
        responder(agente, [{"papel": "user", "texto": " ".join(sys.argv[1:])}])
        return

    print("Agente de consulta processual. Digite sua pergunta ('sair' para encerrar).")
    historico = []
    while True:
        try:
            pergunta = input("\nVocê: ").strip()
        except (EOFError, KeyboardInterrupt):
            break
        if pergunta.lower() in ("sair", "exit", "quit"):
            break
        if not pergunta:
            continue
        historico.append({"papel": "user", "texto": pergunta})
        historico.append({"papel": "assistant", "texto": responder(agente, historico)})


if __name__ == "__main__":
    main()
