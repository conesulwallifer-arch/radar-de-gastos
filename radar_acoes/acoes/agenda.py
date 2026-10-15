"""Agenda de proventos: quanto você deve receber em cada um dos próximos 12 meses e as próximas datas-com.

Para cada ação, usa o padrão dos últimos 3 anos: em quais meses ela paga e quanto (média por ação naquele mês),
corrigido pela previsão de proventos dos próximos 12 meses. É estimativa: a empresa pode mudar datas e valores.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

MESES = "jan fev mar abr mai jun jul ago set out nov dez".split()


def padrao_mensal(proventos: pd.Series, previsto_12m: float | None, hoje: pd.Timestamp) -> dict[int, float]:
    """{mês: R$ por ação esperado naquele mês nos próximos 12 meses}."""
    p = proventos[proventos.index > hoje - pd.DateOffset(years=3)]
    if p.empty:
        return {}
    por_mes = p.groupby(p.index.month).sum() / 3.0
    total = float(por_mes.sum())
    if previsto_12m and previsto_12m == previsto_12m and total > 0:
        por_mes = por_mes * (previsto_12m / total)
    return {int(m): float(v) for m, v in por_mes.items() if v > 0}


def projetar(posicoes: dict[str, float], proventos: dict[str, pd.Series], ranking: pd.DataFrame,
             hoje: date | None = None) -> pd.DataFrame:
    """Linhas (mes_ord, mes, ano, ticker, valor) para os próximos 12 meses. posicoes = {ticker: quantidade}."""
    hoje = pd.Timestamp(hoje or date.today())
    prev = dict(zip(ranking["ticker"], ranking.get("proventos_previstos_12m", pd.Series(dtype=float))))
    linhas = []
    for t, q in posicoes.items():
        if not q or t not in proventos:
            continue
        pad = padrao_mensal(proventos[t], prev.get(t), hoje)
        for k in range(1, 13):
            d = hoje + pd.DateOffset(months=k)
            v = pad.get(d.month, 0.0) * q
            if v > 0:
                linhas.append({"ordem": k, "mes": f"{MESES[d.month - 1]}/{d.year % 100:02d}", "ticker": t, "valor": v})
    return pd.DataFrame(linhas, columns=["ordem", "mes", "ticker", "valor"])


def proximas_datas_com(ranking: pd.DataFrame, dias: int = 45, hoje: date | None = None) -> pd.DataFrame:
    hoje = hoje or date.today()
    if "ex_dividendo" not in ranking:
        return pd.DataFrame()
    r = ranking.dropna(subset=["ex_dividendo"]).copy()
    r["data_ex"] = pd.to_datetime(r["ex_dividendo"], errors="coerce")
    r = r[(r["data_ex"] >= pd.Timestamp(hoje)) & (r["data_ex"] <= pd.Timestamp(hoje) + pd.Timedelta(days=dias))]
    r["comprar_ate"] = r["data_ex"] - pd.offsets.BDay(1)
    return r.sort_values("data_ex")[["ticker", "nome", "sinal", "data_ex", "comprar_ate", "ultimo_provento_valor", "dy_medio_5a"]]
