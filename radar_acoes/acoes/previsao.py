"""Previsões: proventos dos próximos 12 meses, faixa de preço (1, 3 e 5 anos) e simulação de aportes mensais.

Método (transparente de propósito):
- Proventos: média dos últimos 3 anos completos, corrigida pelo crescimento histórico (limitado a -10%..+10% a.a.).
- Preço: modelo log-normal. A tendência mistura o histórico da ação (50%) com uma expectativa de longo prazo
  para a bolsa (50%), descontando o que sai como provento; a incerteza vem da volatilidade histórica.
  Mostramos uma faixa (pessimista 10%, mediana, otimista 90%), não um número mágico.
"""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

RETORNO_LONGO_PRAZO = 0.12  # retorno total nominal esperado de longo prazo para ações no Brasil (a.a.)
Z90 = 1.2815515655446004


def proventos_12m(i: dict, hoje: pd.Timestamp | None = None) -> dict:
    hoje = hoje or pd.Timestamp(date.today())
    base = i.get("proventos_media_3a") or i.get("proventos_12m") or 0.0
    g = i.get("cresc_proventos_5a")
    g = 0.0 if g is None or g != g else max(-0.10, min(0.10, g))
    previsto = base * (1 + g)
    preco = i.get("preco") or np.nan
    meses = i.get("meses_pagamento") if isinstance(i.get("meses_pagamento"), list) else []
    nomes = "jan fev mar abr mai jun jul ago set out nov dez".split()
    return {
        "proventos_previstos_12m": previsto,
        "dy_previsto": previsto / preco if preco else np.nan,
        "renda_mensal_por_100_acoes": previsto * 100 / 12,
        "meses_provaveis": ", ".join(nomes[m - 1] for m in meses) or "sem histórico",
        "proximos_meses": [nomes[m - 1] for m in meses if m > hoje.month] + [nomes[m - 1] for m in meses if m <= hoje.month],
    }


def tendencia(precos: pd.Series, dy: float) -> tuple[float, float]:
    """(tendência anual de preço, volatilidade anual)."""
    p = precos.dropna()
    p = p[p.index > p.index.max() - pd.DateOffset(years=5)]
    if len(p) < 60:
        return 0.0, 0.30
    anos = (p.index[-1] - p.index[0]).days / 365.25
    hist = (p.iloc[-1] / p.iloc[0]) ** (1 / anos) - 1 if anos > 0.5 and p.iloc[0] > 0 else 0.0
    vol = float(np.log(p).diff().dropna().std() * math.sqrt(252))
    dy = 0.0 if dy != dy else min(dy, 0.15)
    esperado_preco = RETORNO_LONGO_PRAZO - dy
    mu = 0.5 * hist + 0.5 * esperado_preco
    return float(max(-0.10, min(0.20, mu))), float(min(max(vol, 0.10), 0.80))


def faixa_preco(preco: float, mu: float, vol: float, anos: float) -> dict:
    """Quantis 10/50/90% do preço daqui a `anos` (log-normal, mediana = preço × (1+mu)^anos)."""
    m = math.log(1 + mu) * anos
    s = vol * math.sqrt(anos)
    return {"pessimista": preco * math.exp(m - Z90 * s), "mediana": preco * math.exp(m),
            "otimista": preco * math.exp(m + Z90 * s)}


def prever(i: dict, precos: pd.Series) -> dict:
    prov = proventos_12m(i)
    mu, vol = tendencia(precos, i.get("dy_medio_5a") or i.get("dy_12m") or 0.0)
    preco = i["preco"]
    saida = {"tendencia_preco_aa": mu, "volatilidade_aa": vol, **prov}
    for anos in (1, 3, 5):
        f = faixa_preco(preco, mu, vol, anos)
        for k, v in f.items():
            saida[f"preco_{anos}a_{k}"] = v
    dyp = prov["dy_previsto"] if prov["dy_previsto"] == prov["dy_previsto"] else 0.0
    saida["retorno_total_esperado_aa"] = mu + dyp
    return saida


def simular_aportes(aporte_mensal: float, anos: int, dy: float, valorizacao: float,
                    inicial: float = 0.0, reinvestir: bool = True, aumento_aporte_aa: float = 0.0) -> pd.DataFrame:
    """Evolução mês a mês de uma carteira com aportes mensais e proventos reinvestidos.
    dy e valorizacao em fração ao ano (ex.: 0.07 e 0.04)."""
    r_preco = (1 + valorizacao) ** (1 / 12) - 1
    r_div = dy / 12
    patrimonio, investido, proventos_acum = inicial, inicial, 0.0
    aporte = aporte_mensal
    linhas = []
    for mes in range(1, anos * 12 + 1):
        if mes > 1 and (mes - 1) % 12 == 0:
            aporte *= 1 + aumento_aporte_aa
        patrimonio *= 1 + r_preco
        prov = patrimonio * r_div
        proventos_acum += prov
        patrimonio += aporte + (prov if reinvestir else 0.0)
        investido += aporte
        linhas.append({"mes": mes, "ano": (mes - 1) // 12 + 1, "aporte": aporte, "investido": investido,
                       "patrimonio": patrimonio, "proventos_mes": prov, "proventos_acumulados": proventos_acum,
                       "renda_mensal_estimada": patrimonio * r_div})
    return pd.DataFrame(linhas)


def cenarios(aporte_mensal: float, anos: int, dy: float, valorizacao: float, **kw) -> dict[str, pd.DataFrame]:
    return {
        "Pessimista": simular_aportes(aporte_mensal, anos, dy * 0.75, valorizacao - 0.03, **kw),
        "Base": simular_aportes(aporte_mensal, anos, dy, valorizacao, **kw),
        "Otimista": simular_aportes(aporte_mensal, anos, dy * 1.15, valorizacao + 0.02, **kw),
    }


def meta_renda(renda_mensal_desejada: float, dy: float, valorizacao: float, aporte_mensal: float,
               inicial: float = 0.0, limite_anos: int = 60) -> int | None:
    """Em quantos meses a renda passiva mensal estimada atinge a meta (None se não atingir no limite)."""
    df = simular_aportes(aporte_mensal, limite_anos, dy, valorizacao, inicial=inicial)
    ok = df[df["renda_mensal_estimada"] >= renda_mensal_desejada]
    return int(ok["mes"].iloc[0]) if len(ok) else None
