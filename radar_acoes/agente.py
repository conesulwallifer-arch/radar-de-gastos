"""Agente JARVIS: fica ligado e trabalha sozinho.

    python agente.py            # modo vigia: roda sem parar (deixe a janela aberta)
    python agente.py --agora    # faz a apuração completa + relatório do JARVIS agora e envia
    python agente.py --checar   # confere os preços do pregão uma vez agora

No modo vigia, em dias úteis (horário de Brasília):
- durante o pregão (10h–18h), a cada 30 minutos confere os preços das 15 melhores ações e da sua carteira
  e avisa no Telegram/e-mail se surgir oportunidade (preço abaixo do teto) ou queda forte;
- às 18h30, faz a apuração completa do dia: coleta tudo de novo, recalcula notas, previsões, meta,
  teste no passado, busca notícias e o JARVIS escreve e envia o relatório (com pesquisa na web, se houver chave da IA).
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acoes import alertas, aporte, plano, universo, vigia  # noqa: E402
from apurar import ULTIMO, apurar  # noqa: E402

FUSO = ZoneInfo("America/Sao_Paulo")
INTERVALO_MIN = int(os.getenv("JARVIS_INTERVALO_MIN", "30"))
HORA_APURACAO = (18, 30)


def agora() -> datetime:
    return datetime.now(FUSO)


def pregao_aberto(t: datetime) -> bool:
    return t.weekday() < 5 and (10, 0) <= (t.hour, t.minute) < (18, 0)


def enviar(texto: str, assunto: str) -> None:
    alertas.carregar_config()
    ok = alertas.enviar_telegram(texto) | alertas.enviar_email(assunto, texto)
    if not ok:
        print("  (Telegram/e-mail não configurados: o aviso ficou só aqui na tela e no painel.)")


def apuracao_completa() -> None:
    print(f"[{agora():%d/%m %H:%M}] 🤖 Iniciando apuração completa...")
    apurar(universo.tickers(), plano.ler()["aporte_mensal"])  # já envia o relatório do JARVIS


def checagem() -> None:
    if not ULTIMO.exists():
        print("Ainda não há apuração; fazendo a primeira agora.")
        apuracao_completa()
        return
    with open(ULTIMO, "rb") as f:
        R = pickle.load(f)
    novos = vigia.checar(R, aporte.ler_carteira()["ticker"].tolist())
    print(f"[{agora():%d/%m %H:%M}] Vigia: {len(novos)} alerta(s) novo(s).")
    if novos:
        txt = "🤖 J.A.R.V.I.S. — alerta do pregão\n\n" + "\n\n".join(novos) + "\n\nNão é recomendação de investimento."
        print(txt)
        enviar(txt, f"JARVIS: {len(novos)} alerta(s) agora")


def vigiar() -> None:
    print("🤖 J.A.R.V.I.S. online. Vigiando o mercado (Ctrl+C para parar).")
    ultima_apuracao = None
    if ULTIMO.exists():
        with open(ULTIMO, "rb") as f:
            ultima_apuracao = pickle.load(f)["data"]
    while True:
        t = agora()
        if t.weekday() < 5 and (t.hour, t.minute) >= HORA_APURACAO and ultima_apuracao != t.date():
            try:
                apuracao_completa()
                ultima_apuracao = t.date()
            except Exception as e:  # noqa: BLE001
                print(f"  [erro na apuração] {e} — tento de novo no próximo ciclo.")
        elif pregao_aberto(t):
            try:
                checagem()
            except Exception as e:  # noqa: BLE001
                print(f"  [erro na vigia] {e}")
        prox = t + timedelta(minutes=INTERVALO_MIN)
        if not pregao_aberto(prox) and not (prox.weekday() < 5 and (prox.hour, prox.minute) >= HORA_APURACAO):
            print(f"[{t:%d/%m %H:%M}] Mercado fechado. Próxima verificação às {prox:%H:%M}.")
        time.sleep(max(60, (prox - agora()).total_seconds()))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agora", action="store_true", help="apuração completa + relatório agora")
    ap.add_argument("--checar", action="store_true", help="confere os preços do pregão uma vez agora")
    a = ap.parse_args()
    alertas.carregar_config()
    if a.agora:
        apuracao_completa()
    elif a.checar:
        checagem()
    else:
        vigiar()


if __name__ == "__main__":
    main()
