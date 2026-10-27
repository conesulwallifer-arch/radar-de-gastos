"""O escritório da equipe: o que cada agente está fazendo agora e o diário de trabalho de todos os dias.

- status_agentes.json: estado atual de cada agente (trabalhando / vigiando / em pausa) e a tarefa.
- diario_equipe.jsonl: uma linha por ação, com data e hora — acumula para sempre (o painel mostra as últimas).

Quem escreve aqui: a apuração diária, a mesa de agentes, o Atlas, a vigilância do pregão e a reunião semanal.
O painel só lê — por isso dá para ver a equipe trabalhando mesmo que o painel tenha ficado fechado.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from datetime import datetime

from . import DADOS

STATUS = DADOS / "status_agentes.json"
SILENCIOSO = False  # em testes com dados fictícios o diário não é escrito (só o status)
DIARIO = DADOS / "diario_equipe.jsonl"

EQUIPE = {  # id: (nome, ícone, cargo)
    "aurum": ("AURUM", "🪙", "Estrategista-chefe"),
    "renda": ("Dora", "💰", "Analista de Dividendos"),
    "fundamentos": ("Fausto", "🏛️", "Analista Fundamentalista"),
    "valuation": ("Vitória", "🏷️", "Analista de Valuation"),
    "tendencia": ("Téo", "📈", "Analista de Tendência"),
    "noticias": ("Nina", "📰", "Analista de Notícias"),
    "previsor": ("Íris", "🔮", "Previsora do próximo mês"),
    "risco": ("Rex", "🛡️", "Gestor de Risco"),
    "proventos": ("Otto", "💵", "Previsor de Proventos"),
    "entrada": ("Bento", "🎯", "Estrategista de Entrada"),
    "conjunto": ("Sofia", "🧮", "Cientista de Dados"),
    "trading": ("Leo", "⚡", "Trader de Médio Prazo"),
    "atlas": ("Atlas", "🧭", "Explorador autônomo"),
}


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def ler_status() -> dict:
    try:
        return json.loads(STATUS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


_TRAVA = threading.Lock()


def status(agentes: str | list[str], estado: str, tarefa: str) -> None:
    """estado: 'trabalhando' | 'vigiando' | 'pausa' | 'erro'.

    O status é só para mostrar a equipe no painel: se não der para gravar (outro processo escrevendo ao mesmo
    tempo, antivírus segurando o arquivo no Windows...), tenta de novo e, em último caso, desiste em silêncio —
    nunca derruba a apuração."""
    with _TRAVA:
        for tentativa in range(5):
            tmp = STATUS.with_name(f"{STATUS.stem}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")  # nome único por escrita
            try:
                atual = ler_status()
                for a in [agentes] if isinstance(agentes, str) else agentes:
                    atual[a] = {"estado": estado, "tarefa": tarefa, "desde": _agora()}
                STATUS.parent.mkdir(parents=True, exist_ok=True)
                tmp.write_text(json.dumps(atual, ensure_ascii=False, indent=1), encoding="utf-8")
                os.replace(tmp, STATUS)  # troca atômica: o painel nunca lê o arquivo pela metade
                return
            except OSError:
                try:
                    tmp.unlink(missing_ok=True)
                except OSError:
                    pass
                time.sleep(0.05 * (tentativa + 1))


def todos_em_pausa(proxima: str) -> None:
    status(list(EQUIPE), "pausa", proxima)


def registrar(agente: str, texto: str) -> None:
    if SILENCIOSO:
        return
    try:
        DIARIO.parent.mkdir(parents=True, exist_ok=True)
        with _TRAVA, open(DIARIO, "a", encoding="utf-8") as f:
            f.write(json.dumps({"quando": _agora(), "agente": agente, "texto": texto[:400]}, ensure_ascii=False) + "\n")
    except OSError:
        pass  # o diário é registro; falhar aqui não pode parar o trabalho


def ler_diario(n: int = 80) -> list[dict]:
    try:
        linhas = DIARIO.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    saida = []
    for l in linhas[-n:]:
        try:
            saida.append(json.loads(l))
        except json.JSONDecodeError:
            continue
    return saida[::-1]  # mais recente primeiro


def dias_trabalhados() -> int:
    try:
        return len({json.loads(l)["quando"][:10] for l in DIARIO.read_text(encoding="utf-8").splitlines() if l.strip()})
    except (OSError, ValueError, KeyError):
        return 0
