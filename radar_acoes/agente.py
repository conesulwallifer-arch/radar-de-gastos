"""Agente AURUM: a equipe trabalhando sozinha, todos os dias, com ou sem o painel aberto.

    python agente.py            # liga a equipe (deixe rodando; "Ligar AURUM 24h.bat" faz isso escondido ao iniciar o Windows)
    python agente.py --agora    # apuração completa + relatório agora
    python agente.py --checar   # confere os preços do pregão uma vez agora
    python agente.py --semanal  # reunião semanal agora

Rotina da equipe (horário de Brasília):
- ao ligar: se perdeu alguma apuração (computador desligado), faz na hora para não começar o dia com dado velho;
- dias úteis, 10h–18h: a cada 1 hora, apuração completa com preços novos (ranking, previsões, mesa, alertas no painel);
  entre uma e outra, Rex e Téo conferem os preços das melhores ações e da sua carteira a cada 30 min;
- dias úteis, 18h30: reunião completa — coleta, notas, 10 especialistas, verificação cruzada, Atlas, relatório;
- sábado, 10h: reunião semanal com o placar da equipe e o que mudou na semana.
Tudo o que fazem fica no diário da equipe (aba 🧠 Sala dos Agentes) e o importante chega no seu Telegram.
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acoes import DADOS, alertas, aporte, escritorio, plano, semanal, trading, universo, vigia  # noqa: E402
from apurar import ULTIMO, apurar  # noqa: E402

alertas.carregar_config()  # config.env antes de ler os intervalos abaixo
FUSO = ZoneInfo("America/Sao_Paulo")
INTERVALO_MIN = int(os.getenv("AURUM_INTERVALO_MIN") or os.getenv("JARVIS_INTERVALO_MIN") or "30")
HORA_APURACAO = (18, 30)
# apuração completa durante o pregão a cada N minutos (0 = só a das 18h30). Configurável no config.env.
APURAR_A_CADA_MIN = int(os.getenv("AURUM_APURAR_A_CADA_MIN") or "60")
HORA_SEMANAL = (10, 0)
VIVO = DADOS / "agente_vivo.txt"
TRAVA = DADOS / "agente.lock"
LOG = DADOS / "agente.log"
SEMANAL_FEITA = DADOS / "semanal_ultima.txt"
PID = DADOS / "agente.pid"
FECHAMENTO = DADOS / "fechamento_ultimo.txt"  # pregão coberto pela última reunião completa (a das 18h30)


def agora() -> datetime:
    return datetime.now(FUSO)


def pregao_aberto(t: datetime) -> bool:
    return t.weekday() < 5 and (10, 0) <= (t.hour, t.minute) < (18, 0)


def ultimo_pregao_fechado(t: datetime) -> date:
    """Data da última apuração que já deveria existir (dia útil após as 18h30)."""
    d = t.date() if t.weekday() < 5 and (t.hour, t.minute) >= HORA_APURACAO else t.date() - timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def data_ultima_apuracao() -> date | None:
    """Pregão coberto pela última reunião completa de fechamento. As apurações da hora não contam: elas não
    trazem a análise com IA nem o relatório do dia, então não podem 'pular' a reunião das 18h30."""
    try:
        return date.fromisoformat(FECHAMENTO.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return None


def sinal_de_vida() -> None:
    VIVO.parent.mkdir(parents=True, exist_ok=True)
    VIVO.write_text(datetime.now().isoformat(timespec="seconds"), encoding="utf-8")


def enviar(texto: str, assunto: str) -> None:
    alertas.carregar_config()
    ok = alertas.enviar_telegram(texto) | alertas.enviar_email(assunto, texto)
    if not ok:
        print("  (Telegram/e-mail não configurados: o aviso ficou no painel e no diário.)")


def avisar_operacoes(precos: dict[str, float]) -> None:
    """Suas operações de trading: avisa no Telegram quando bater o alvo, o stop ou for hora de proteger o ganho."""
    try:
        msgs = trading.alertas_operacoes(precos)
    except Exception as e:  # noqa: BLE001
        print(f"  [aviso] operações de trading: {e}")
        return
    if msgs:
        escritorio.registrar("trading", f"avisou sobre {len(msgs)} operação(ões) sua(s): " + "; ".join(m.split(':')[0] for m in msgs))
        enviar("⚡ AURUM — suas operações de trading\n\n" + "\n\n".join(msgs) + "\n\nNão é recomendação de investimento.",
               f"AURUM: {len(msgs)} aviso(s) de trading")


def _precos_do(R: dict) -> dict[str, float]:
    rk = R["ranking"]
    return {t: float(p) for t, p in zip(rk["ticker"], rk["preco"]) if p == p}


def apuracao_completa() -> None:
    print(f"[{agora():%d/%m %H:%M}] 🪙 Reunião completa da equipe começando...")
    escritorio.registrar("aurum", "convocou a equipe para a apuração completa")
    coberto = ultimo_pregao_fechado(agora())
    R = apurar(universo.tickers(), plano.ler()["aporte_mensal"], forcar=True)  # já envia o relatório do AURUM
    avisar_operacoes(_precos_do(R))
    FECHAMENTO.write_text(coberto.isoformat(), encoding="utf-8")


_INICIO_ULTIMA: list[float] = []  # quando começou a última apuração (conta do início: "de hora em hora" certinho)


def minutos_desde_ultima_apuracao() -> float:
    try:
        ref = _INICIO_ULTIMA[-1] if _INICIO_ULTIMA else ULTIMO.stat().st_mtime
        return (time.time() - ref) / 60
    except OSError:
        return float("inf")


def apuracao_horaria() -> None:
    """Durante o pregão: tudo de novo com preços frescos. Sem relatório no Telegram (só o das 18h30 e os alertas
    do vigia) e sem IA paga (as regras dos 10 especialistas rodam; a IA entra na reunião das 18h30)."""
    _INICIO_ULTIMA.append(time.time())
    print(f"[{agora():%d/%m %H:%M}] 🪙 Apuração da hora (preços novos)...")
    escritorio.registrar("aurum", "convocou a equipe para a apuração da hora, com preços novos do pregão")
    R = apurar(universo.tickers(), plano.ler()["aporte_mensal"], enviar=False, forcar=True, usar_ia=False)
    avisar_operacoes(_precos_do(R))
    escritorio.status("aurum", "pausa", f"próxima apuração por volta das {agora() + timedelta(minutes=APURAR_A_CADA_MIN):%H:%M}")


def checagem() -> None:
    if not ULTIMO.exists():
        print("Ainda não há apuração; fazendo a primeira agora.")
        apuracao_completa()
        return
    with open(ULTIMO, "rb") as f:
        R = pickle.load(f)
    escritorio.status(["risco", "tendencia"], "vigiando", "conferindo os preços do pregão")
    novos = vigia.checar(R, aporte.ler_carteira()["ticker"].tolist())
    ops = trading.ler_operacoes()
    abertas = ops[ops["status"].str.lower() == "aberta"]["ticker"].tolist()
    if abertas:
        try:
            avisar_operacoes(vigia.precos_agora(abertas))
        except Exception as e:  # noqa: BLE001
            print(f"  [aviso] preços das operações: {e}")
    print(f"[{agora():%d/%m %H:%M}] Vigia: {len(novos)} alerta(s) novo(s).")
    escritorio.registrar("risco", f"conferiu os preços do pregão: {len(novos)} alerta(s) novo(s)" if novos
                         else "conferiu os preços do pregão: nada fora do normal")
    if novos:
        txt = "🪙 AURUM — alerta do pregão\n\n" + "\n\n".join(novos) + "\n\nNão é recomendação de investimento."
        print(txt)
        enviar(txt, f"AURUM: {len(novos)} alerta(s) agora")
    prox = agora() + timedelta(minutes=INTERVALO_MIN)
    escritorio.status(["risco", "tendencia"], "pausa", f"próxima conferência às {prox:%H:%M}")


def reuniao_semanal() -> None:
    if not ULTIMO.exists():
        return
    with open(ULTIMO, "rb") as f:
        R = pickle.load(f)
    escritorio.status("aurum", "trabalhando", "conduzindo a reunião semanal")
    txt = semanal.relatorio(R)
    print(txt)
    escritorio.registrar("aurum", "conduziu a reunião semanal e enviou o resumo")
    enviar(txt, "AURUM: reunião semanal")
    SEMANAL_FEITA.write_text(date.today().isoformat(), encoding="utf-8")
    escritorio.status("aurum", "pausa", "reunião semanal entregue")


def semanal_pendente(t: datetime) -> bool:
    if t.weekday() != 5 or (t.hour, t.minute) < HORA_SEMANAL:
        return False
    try:
        return SEMANAL_FEITA.read_text(encoding="utf-8").strip() != t.date().isoformat()
    except FileNotFoundError:
        return True


def descricao_proxima(t: datetime) -> str:
    if pregao_aberto(t):
        return (f"apuração completa a cada {APURAR_A_CADA_MIN} min e vigia a cada {INTERVALO_MIN} min" if APURAR_A_CADA_MIN
                else f"vigiando o pregão a cada {INTERVALO_MIN} min")
    if t.weekday() < 5 and (t.hour, t.minute) < (10, 0):
        return "volta às 10h, na abertura do pregão"
    if t.weekday() < 5 and (t.hour, t.minute) < HORA_APURACAO:
        return "reunião completa às 18h30"
    semanal_vem = t.weekday() == 4 or (t.weekday() == 5 and (t.hour, t.minute) < HORA_SEMANAL)
    return "volta no próximo pregão (10h)" + (" · reunião semanal sábado às 10h" if semanal_vem else "")


def trava_unica():
    """Impede duas cópias do agente ao mesmo tempo (devolve o arquivo travado, ou None se já houver outra)."""
    TRAVA.parent.mkdir(parents=True, exist_ok=True)
    f = open(TRAVA, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def vigiar() -> None:
    trava = trava_unica()
    if trava is None:
        print("O AURUM já está ligado em outra janela (ou em segundo plano). Nada a fazer aqui.")
        return
    PID.write_text(str(os.getpid()), encoding="utf-8")
    print("🪙 AURUM online. A equipe está trabalhando (Ctrl+C para parar).")
    escritorio.registrar("aurum", "ligou a equipe")
    while True:
        t = agora()
        sinal_de_vida()
        try:
            ultima = data_ultima_apuracao()
            if ultima is None or ultima < ultimo_pregao_fechado(t):
                if ultima is not None:
                    escritorio.registrar("aurum", f"percebeu que a última apuração era de {ultima:%d/%m} e está colocando o trabalho em dia")
                apuracao_completa()
            elif semanal_pendente(t):
                reuniao_semanal()
            elif pregao_aberto(t) and APURAR_A_CADA_MIN and minutos_desde_ultima_apuracao() >= APURAR_A_CADA_MIN - 2:
                apuracao_horaria()
            elif pregao_aberto(t):
                checagem()
            else:
                escritorio.todos_em_pausa(descricao_proxima(t))
        except Exception as e:  # noqa: BLE001  (a equipe não para por causa de um erro: tenta de novo no próximo ciclo)
            print(f"  [erro] {e} — tento de novo no próximo ciclo.")
            escritorio.registrar("aurum", f"encontrou um problema e vai tentar de novo: {e}")
            escritorio.status("aurum", "erro", f"tentando de novo: {str(e)[:80]}")
        # dorme em blocos de 5 min mandando sinal de vida (o painel mostra 'equipe ligada')
        alvo = agora() + timedelta(minutes=INTERVALO_MIN)
        if APURAR_A_CADA_MIN and pregao_aberto(agora()):
            alvo = min(alvo, agora() + timedelta(minutes=max(1.0, APURAR_A_CADA_MIN - minutos_desde_ultima_apuracao())))
        if not pregao_aberto(alvo) and t.weekday() < 5 and (t.hour, t.minute) < HORA_APURACAO <= (alvo.hour, alvo.minute):
            alvo = alvo.replace(hour=HORA_APURACAO[0], minute=HORA_APURACAO[1], second=5)
        while agora() < alvo:
            time.sleep(min(300, max(1, (alvo - agora()).total_seconds())))
            sinal_de_vida()


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agora", action="store_true", help="apuração completa + relatório agora")
    ap.add_argument("--checar", action="store_true", help="confere os preços do pregão uma vez agora")
    ap.add_argument("--semanal", action="store_true", help="reunião semanal agora")
    ap.add_argument("--hora", action="store_true", help="apuração da hora (preços novos, sem envio) agora")
    a = ap.parse_args()
    if sys.stdout is None or os.getenv("AURUM_OCULTO"):  # rodando escondido (pythonw): tudo vai para o arquivo de log
        LOG.parent.mkdir(parents=True, exist_ok=True)
        if LOG.exists() and LOG.stat().st_size > 5_000_000:  # não deixa o log crescer para sempre
            LOG.replace(LOG.with_suffix(".log.antigo"))
        sys.stdout = sys.stderr = open(LOG, "a", encoding="utf-8", buffering=1)
    alertas.carregar_config()
    if a.agora:
        apuracao_completa()
    elif a.checar:
        checagem()
    elif a.semanal:
        reuniao_semanal()
    elif a.hora:
        apuracao_horaria()
    else:
        vigiar()


if __name__ == "__main__":
    main()
