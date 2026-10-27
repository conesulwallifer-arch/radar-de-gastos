"""Reunião semanal da equipe (sábado de manhã): o que mudou na semana, como a equipe se saiu e o que vigiar.

Compara o ranking de hoje com o de ~7 dias atrás (histórico das apurações reais), mostra o placar real da
equipe (decisões do consenso conferidas 3 meses depois contra o mercado), as anotações do Atlas na semana,
o progresso da meta e quantas ações a equipe registrou no diário.
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from . import DADOS, escritorio, memoria, mesa
from .alertas import _fmt_pct as pct_sinal
from .alertas import _fmt_r as brl
from .atlas import ler_notas

HIST = DADOS / "historico"


def _ranking_de(dia: date) -> pd.DataFrame | None:
    arqs = sorted(p for p in HIST.glob("ranking_*.csv") if p.stem <= f"ranking_{dia:%Y-%m-%d}")
    return pd.read_csv(arqs[-1]) if arqs else None


def relatorio(R: dict, hoje: date | None = None) -> str:
    hoje = hoje or date.today()
    rk: pd.DataFrame = R["ranking"]
    l = [f"🪙 AURUM — Reunião semanal ({hoje - timedelta(days=6):%d/%m} a {hoje:%d/%m})", ""]

    antes = _ranking_de(hoje - timedelta(days=7))
    if antes is not None and len(antes):
        a = antes.set_index("ticker")
        entraram = [t for t in rk.head(10)["ticker"] if t not in set(antes.head(10)["ticker"])]
        sairam = [t for t in antes.head(10)["ticker"] if t not in set(rk.head(10)["ticker"])]
        delta = (rk.set_index("ticker")["nota"] - a["nota"]).dropna().sort_values()
        l.append("📊 Ranking na semana")
        l.append(f"• Entraram no top 10: {', '.join(entraram) or 'ninguém'} · saíram: {', '.join(sairam) or 'ninguém'}")
        if len(delta):
            l.append(f"• Mais melhorou: {delta.index[-1]} ({delta.iloc[-1]:+.0f} pts) · mais piorou: {delta.index[0]} ({delta.iloc[0]:+.0f} pts)")
        if "consenso" in a.columns and "consenso" in rk:
            novos = [t for t in rk[rk["consenso"] == "Compra forte"]["ticker"] if a["consenso"].get(t) != "Compra forte"]
            if novos:
                l.append(f"• Novos consensos de COMPRA FORTE: {', '.join(novos)}")
        l.append("")
    else:
        l += ["📊 Ainda não há uma semana de histórico para comparar.", ""]

    cer = memoria.avaliar(R.get("precos", {}), R.get("proventos", {}))
    pa = cer.get("por_agente")
    l.append("🧠 Placar real da equipe (votos conferidos 3 meses depois, contra a média do mercado)")
    if pa is not None and len(pa):
        eq = pa[pa["agente"] == "equipe"]
        if len(eq):
            e = eq.iloc[0]
            l.append(f"• Equipe: acertou {pct_sinal(e['acerto']).lstrip('+')} de {int(e['conferidos'])} decisões; ações que ela apoiou "
                     f"renderam {pct_sinal(e['ganho_a_favor'])} vs mercado")
        top = pa[pa["agente"].isin(mesa.POR_ID)].sort_values("acerto", ascending=False)
        if len(top):
            m = top.iloc[0]
            l.append(f"• Destaque: {mesa.POR_ID[m['agente']].apelido} ({pct_sinal(m['acerto']).lstrip('+')} de acerto)")
    else:
        l.append(f"• Ainda acumulando: {cer.get('votos_guardados', 0)} votos guardados, conferência começa 3 meses após o 1º voto.")
    l.append("")

    notas = [n for n in ler_notas(60) if n["data"] >= (hoje - timedelta(days=7)).isoformat()]
    if notas:
        l.append("🧭 Anotações do Atlas na semana")
        l += [f"• {n.get('ticker') or ''} {n['texto']}".strip() for n in notas[-5:]]
        l.append("")

    dias = {d["quando"][:10] for d in escritorio.ler_diario(5000) if d["quando"][:10] >= (hoje - timedelta(days=7)).isoformat()}
    acoes_ = sum(1 for d in escritorio.ler_diario(5000) if d["quando"][:10] >= (hoje - timedelta(days=7)).isoformat())
    l.append(f"🏢 A equipe trabalhou em {len(dias)} dia(s) nesta semana e registrou {acoes_} ação(ões) no diário.")
    if R.get("compras") is not None and len(R["compras"]):
        l.append(f"🛒 Plano do mês continua: {', '.join(R['compras']['ticker'].head(6))} (total {brl(R['compras']['valor'].sum())}).")
    l += ["", "Não é recomendação de investimento."]
    return "\n".join(l)
