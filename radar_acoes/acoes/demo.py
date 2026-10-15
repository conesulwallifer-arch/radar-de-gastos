"""Dados FICTÍCIOS para testar o sistema sem internet (python apurar.py --demo). Não use para investir."""
from __future__ import annotations

import zlib
from datetime import date

import numpy as np
import pandas as pd


def gerar(ticker: str, hoje: date | None = None) -> dict:
    hoje = pd.Timestamp(hoje or date.today())
    rng = np.random.default_rng(zlib.crc32(ticker.encode()))
    dias = pd.bdate_range(hoje - pd.DateOffset(years=10), hoje)
    mu, vol = rng.uniform(-0.02, 0.12), rng.uniform(0.18, 0.45)
    ret = rng.normal(mu / 252, vol / np.sqrt(252), len(dias))
    precos = pd.Series(rng.uniform(8, 60) * np.exp(np.cumsum(ret)), index=dias).round(2)
    dy_alvo = rng.uniform(0.0, 0.11)
    meses = sorted(rng.choice(range(1, 13), size=int(rng.choice([1, 2, 4, 12])), replace=False))
    datas = [pd.Timestamp(a, m, 15) for a in range(hoje.year - 10, hoje.year + 1) for m in meses
             if pd.Timestamp(a, m, 15) <= hoje and rng.random() > 0.08]
    datas = [d if d.weekday() < 5 else d - pd.offsets.BDay(1) for d in datas]
    prov = pd.Series([float(precos.asof(d)) * dy_alvo / len(meses) * rng.uniform(0.6, 1.4) for d in datas],
                     index=pd.DatetimeIndex(datas)).round(4)
    preco = float(precos.iloc[-1])
    lpa = preco / rng.uniform(4, 25) * (1 if rng.random() > 0.08 else -1)
    vpa = preco / rng.uniform(0.6, 3.5)
    ex = hoje + pd.Timedelta(days=int(rng.integers(-60, 40)))
    info = {
        "longName": f"{ticker} Empresa Fictícia S.A. (DEMO)", "sector": None, "currentPrice": preco,
        "trailingEps": lpa, "bookValue": vpa, "returnOnEquity": lpa / vpa, "profitMargins": rng.uniform(-0.05, 0.35),
        "debtToEquity": rng.uniform(10, 250), "earningsGrowth": rng.uniform(-0.3, 0.3),
        "exDividendDate": int(ex.timestamp()), "targetMeanPrice": preco * rng.uniform(0.85, 1.4),
        "recommendationKey": rng.choice(["buy", "hold", "strong_buy", "underperform"]),
        "longBusinessSummary": "Empresa fictícia gerada para demonstração do Radar de Ações.",
    }
    return {"ticker": ticker, "info": info, "precos": precos, "proventos": prov}


def noticias(ticker: str) -> list[dict]:
    from .noticias import classificar
    rng = np.random.default_rng(zlib.crc32(ticker.encode()) + 7)
    modelos = [f"{ticker} anuncia dividendos e JCP para o trimestre", f"Lucro da {ticker} sobe no 3T e supera expectativas",
               f"{ticker} recua após rebaixamento de recomendação", f"Conselho da {ticker} aprova recompra de ações",
               f"{ticker}: investigação da CVM preocupa investidores", f"Analistas elevam preço-alvo de {ticker}"]
    agora = pd.Timestamp.now()
    return [{"ticker": ticker, "titulo": f"[DEMO] {m}", "fonte": "Notícia fictícia", "quando": agora - pd.Timedelta(hours=int(h)),
             "link": "", **classificar(m)} for m, h in zip(rng.choice(modelos, 3, replace=False), rng.integers(1, 200, 3))]
