"""Coleta de preços, proventos (dividendos + JCP) e indicadores via Yahoo Finance (yfinance), com cache diário."""
from __future__ import annotations

import pickle
import time
from datetime import date

import pandas as pd

from . import DADOS

CACHE = DADOS / "cache"
CACHE.mkdir(parents=True, exist_ok=True)

CAMPOS_INFO = [
    "longName", "shortName", "sector", "industry", "website", "longBusinessSummary", "marketCap",
    "currentPrice", "regularMarketPrice", "previousClose", "fiftyTwoWeekHigh", "fiftyTwoWeekLow",
    "trailingPE", "forwardPE", "priceToBook", "trailingEps", "forwardEps", "bookValue",
    "returnOnEquity", "returnOnAssets", "profitMargins", "operatingMargins", "debtToEquity",
    "totalDebt", "totalCash", "ebitda", "payoutRatio", "earningsGrowth", "revenueGrowth",
    "exDividendDate", "dividendRate", "beta", "recommendationKey", "targetMeanPrice", "numberOfAnalystOpinions",
]


def _arquivo(ticker: str) -> object:
    return CACHE / f"{ticker}_{date.today():%Y%m%d}.pkl"


def coletar(ticker: str, forcar: bool = False, tentativas: int = 3) -> dict | None:
    """Retorna {'ticker','info','precos'(Series fechamento),'proventos'(Series por data-ex)} ou None."""
    arq = _arquivo(ticker)
    if arq.exists() and not forcar:
        with open(arq, "rb") as f:
            return pickle.load(f)
    import yfinance as yf  # import tardio: os testes não precisam da biblioteca

    for i in range(tentativas):
        try:
            tk = yf.Ticker(f"{ticker}.SA")
            hist = tk.history(period="10y", auto_adjust=False, actions=True)
            if hist is None or hist.empty:
                return None
            hist.index = pd.to_datetime(hist.index).tz_localize(None)
            precos = hist["Close"].dropna()
            proventos = hist.get("Dividends", pd.Series(dtype=float))
            proventos = proventos[proventos > 0]
            try:
                info_bruto = tk.get_info() or {}
            except Exception:  # noqa: BLE001
                info_bruto = {}
            info = {k: info_bruto.get(k) for k in CAMPOS_INFO}
            demos = {}
            for nome, metodo in (("dre", "get_income_stmt"), ("balanco", "get_balance_sheet"), ("fluxo", "get_cashflow")):
                try:
                    demos[nome] = getattr(tk, metodo)(pretty=True, freq="yearly")
                except Exception:  # noqa: BLE001  (demonstrações são opcionais: sem elas, só pulamos os testes)
                    demos[nome] = None
            d = {"ticker": ticker, "info": info, "precos": precos, "proventos": proventos, "demos": demos}
            for velho in CACHE.glob(f"{ticker}_*.pkl"):
                velho.unlink(missing_ok=True)
            with open(arq, "wb") as f:
                pickle.dump(d, f)
            return d
        except Exception as e:  # noqa: BLE001
            if i == tentativas - 1:
                print(f"  [erro] {ticker}: {e}")
                return None
            time.sleep(2 * (i + 1))
    return None


def coletar_varios(tickers: list[str], forcar: bool = False, pausa: float = 0.4) -> dict[str, dict]:
    saida = {}
    for n, t in enumerate(tickers, 1):
        print(f"  [{n}/{len(tickers)}] {t}", end="\r")
        em_cache = _arquivo(t).exists() and not forcar
        d = coletar(t, forcar=forcar)
        if d is not None:
            saida[t] = d
        if not em_cache:
            time.sleep(pausa)
    print()
    return saida
