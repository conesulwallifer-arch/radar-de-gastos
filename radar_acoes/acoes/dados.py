"""Coleta de preços, proventos (dividendos + JCP) e indicadores via Yahoo Finance (yfinance), com cache diário."""
from __future__ import annotations

import os
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
    "exDividendDate", "dividendRate", "beta", "earningsTimestamp", "earningsTimestampStart", "earningsTimestampEnd", "recommendationKey", "targetMeanPrice", "numberOfAnalystOpinions", "financialCurrency", "currency",
]


def _arquivo(ticker: str) -> object:
    return CACHE / f"{ticker}_{date.today():%Y%m%d}.pkl"


def _ler(arq) -> dict | None:
    """Lê um cache; se estiver corrompido (PC desligou no meio da gravação), apaga e devolve None."""
    try:
        with open(arq, "rb") as f:
            return pickle.load(f)
    except Exception:  # noqa: BLE001
        try:
            arq.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _ultimo_bom(ticker: str) -> dict | None:
    """O cache mais recente que exista (de qualquer dia) — rede de segurança quando o Yahoo falha."""
    for arq in sorted(CACHE.glob(f"{ticker}_*.pkl"), reverse=True):
        d = _ler(arq)
        if d:
            return d
    return None


def _gravar(ticker: str, arq, d: dict) -> None:
    """Gravação atômica (arquivo temporário + troca): nunca deixa um cache pela metade."""
    tmp = arq.with_name(f"{arq.stem}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        pickle.dump(d, f)
    os.replace(tmp, arq)
    for velho in CACHE.glob(f"{ticker}_*.pkl"):
        if velho != arq:
            try:
                velho.unlink(missing_ok=True)
            except OSError:  # Windows/antivírus segurando o arquivo: fica para a próxima
                pass


def _info_vazia(info: dict | None) -> bool:
    return not info or all(v is None for k, v in info.items() if k not in ("longName", "shortName"))


def coletar(ticker: str, forcar: bool = False, tentativas: int = 3) -> dict | None:
    """Retorna {'ticker','info','precos'(Series fechamento),'proventos'(Series por data-ex),'demos','info_antiga'} ou None.

    - forcar=True no mesmo dia (apuração da hora): baixa só preços e proventos; indicadores e balanços do dia são reaproveitados
      (menos chamadas ao Yahoo = menos bloqueio).
    - Se o Yahoo falhar ou devolver indicadores vazios, usa o último cache bom em vez de "zerar" a ação
      (indicadores vazios faziam toda ação virar "Evitar" e disparar alertas falsos)."""
    arq = _arquivo(ticker)
    hoje = _ler(arq) if arq.exists() else None
    if hoje is not None and not forcar:
        return hoje
    anterior = hoje or _ultimo_bom(ticker)
    import yfinance as yf  # import tardio: os testes não precisam da biblioteca

    for i in range(tentativas):
        try:
            tk = yf.Ticker(f"{ticker}.SA")
            hist = tk.history(period="10y", auto_adjust=False, actions=True)
            if hist is None or hist.empty:
                raise ValueError("histórico vazio (bloqueio temporário ou código fora da B3)")
            hist.index = pd.to_datetime(hist.index).tz_localize(None)
            precos = hist["Close"].dropna()
            proventos = hist.get("Dividends", pd.Series(dtype=float))
            proventos = proventos[proventos > 0]
            info, demos, info_antiga = None, None, False
            if hoje is not None and not _info_vazia(hoje.get("info")):
                info, demos = hoje["info"], hoje.get("demos")  # já baixados hoje
            else:
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
                if _info_vazia(info) and anterior and not _info_vazia(anterior.get("info")):
                    info, info_antiga = anterior["info"], True
                if all(v is None for v in demos.values()) and anterior and anterior.get("demos"):
                    demos = anterior["demos"]
            d = {"ticker": ticker, "info": info, "precos": precos, "proventos": proventos, "demos": demos, "info_antiga": info_antiga}
            if not _info_vazia(info):  # sem indicadores não grava: a próxima rodada tenta de novo
                try:
                    _gravar(ticker, arq, d)
                except OSError as e:
                    print(f"  [aviso] cache de {ticker} não gravado: {e}")
            return d
        except Exception as e:  # noqa: BLE001
            if i == tentativas - 1:
                print(f"  [erro] {ticker}: {e}" + (" — usando os últimos dados bons" if anterior else ""))
                return anterior
            time.sleep(2 * (i + 1))
    return anterior


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
