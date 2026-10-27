"""Vigilância durante o pregão: confere preços das melhores ações e da sua carteira e avisa na hora.

Não refaz a análise inteira (isso é a apuração diária). Só compara o preço do momento com o da última
apuração e com o preço-teto, e avisa:
- ação boa que acabou de cruzar para baixo do preço-teto (oportunidade nova);
- queda forte no dia (≥ 4%) numa ação boa ou da sua carteira.
Cada alerta é enviado no máximo uma vez por dia.
"""
from __future__ import annotations

import json
from datetime import date
from typing import Callable

import pandas as pd

from . import DADOS, hoje_brt
from .alertas import _fmt_r as brl

ESTADO = DADOS / "vigia_estado.json"
QUEDA_FORTE = -0.04


def precos_agora(tickers: list[str]) -> dict[str, float]:
    """Último preço negociado (atraso de ~15 min no Yahoo)."""
    import yfinance as yf

    saida = {}
    try:
        df = yf.download([f"{t}.SA" for t in tickers], period="1d", interval="5m", progress=False,
                         auto_adjust=False, group_by="ticker", threads=True)
    except Exception as e:  # noqa: BLE001
        print(f"  [vigia] falha ao buscar preços: {e}")
        return saida
    for t in tickers:
        try:
            s = df[f"{t}.SA"]["Close"].dropna() if isinstance(df.columns, pd.MultiIndex) else df["Close"].dropna()
            if len(s):
                saida[t] = float(s.iloc[-1])
        except KeyError:
            continue
    return saida


def _ler_estado() -> dict:
    try:
        e = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        e = {}
    if e.get("dia") != hoje_brt().isoformat():
        e = {"dia": hoje_brt().isoformat(), "enviados": []}
    return e


def _fechamento_anterior(R: dict, t: str, padrao: float) -> float:
    """Fechamento do pregão ANTERIOR: a queda do dia é medida contra ele (não contra a última apuração da hora)."""
    s = (R.get("precos") or {}).get(t)
    if s is None or len(s) < 2:
        return padrao
    hoje = pd.Timestamp(hoje_brt())
    anteriores = s[s.index.normalize() < hoje]
    return float(anteriores.iloc[-1]) if len(anteriores) else padrao


def checar(R: dict, carteira: list[str], buscar: Callable[[list[str]], dict[str, float]] = precos_agora,
           n_top: int = 15) -> list[str]:
    """Retorna os alertas NOVOS de agora (já registrados para não repetir hoje)."""
    rk: pd.DataFrame = R["ranking"]
    alvo = list(dict.fromkeys(rk.head(n_top)["ticker"].tolist() + [t for t in carteira if t in set(rk["ticker"])]))
    agora = buscar(alvo)
    est = _ler_estado()
    novos = []
    info = rk.set_index("ticker")
    for t, p in agora.items():
        r = info.loc[t]
        ref, teto = _fechamento_anterior(R, t, float(r["preco"])), r["preco_teto_bazin"]
        var = p / ref - 1 if ref else 0.0
        boa = r["nota"] >= 60 and r.get("confianca", "Alta") != "Baixa"
        if boa and teto == teto and ref > teto >= p:
            chave = f"{t}:teto"
            if chave not in est["enviados"]:
                novos.append(f"🟢 {t} acabou de cair para {brl(p)}, abaixo do preço-teto de {brl(teto)} "
                             f"(nota {r['nota']:.0f}). Oportunidade de compra para renda.")
                est["enviados"].append(chave)
        if var <= QUEDA_FORTE and (boa or t in carteira):
            chave = f"{t}:queda"
            if chave not in est["enviados"]:
                novos.append(f"📉 {t} cai {f'{abs(var) * 100:.1f}'.replace('.', ',')}% agora ({brl(p)}). "
                             + ("Está na sua carteira: veja as notícias antes de qualquer decisão." if t in carteira
                                else "Boa empresa em queda: pode ser oportunidade — confira o motivo."))
                est["enviados"].append(chave)
    ESTADO.parent.mkdir(parents=True, exist_ok=True)
    ESTADO.write_text(json.dumps(est, ensure_ascii=False), encoding="utf-8")
    return novos
