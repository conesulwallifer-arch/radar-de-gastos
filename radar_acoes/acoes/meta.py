"""Rumo à meta (ex.: R$ 1 milhão): em quanto tempo, com que chance, e o que acelera.

Simula milhares de futuros possíveis para a carteira (retorno mensal aleatório com a média e a oscilação
esperadas), com aportes todo mês e proventos reinvestidos. Em vez de prometer uma data, diz a CHANCE de chegar
até cada ano — é assim que se planeja com honestidade num mercado que oscila.
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd

CORRELACAO_MEDIA = 0.45  # ações brasileiras andam bastante juntas; diversificar reduz o risco, mas não zera


def carteira_esperada(escolhidas: pd.DataFrame) -> dict:
    """Retorno total esperado (proventos + valorização) e oscilação de uma carteira com pesos iguais."""
    if escolhidas is None or escolhidas.empty:
        return {"retorno": 0.11, "dy": 0.07, "volatilidade": 0.22, "n": 0}
    n = len(escolhidas)
    ret = escolhidas["retorno_total_esperado_aa"].clip(0.0, 0.25).median()
    dy = escolhidas["dy_previsto"].clip(0.0, 0.15).median()
    s = escolhidas["volatilidade_aa"].fillna(0.30)
    var_media = float((s ** 2).mean())
    vol = math.sqrt(var_media * (CORRELACAO_MEDIA + (1 - CORRELACAO_MEDIA) / n))
    return {"retorno": float(ret), "dy": float(dy), "volatilidade": vol, "n": n}


def meses_ate(meta: float, inicial: float, aporte: float, retorno_aa: float, aumento_aa: float = 0.0,
              inflacao_aa: float = 0.0, limite_meses: int = 720) -> int | None:
    """Caminho médio (sem oscilação). Meta corrigida pela inflação se inflacao_aa > 0."""
    r = (1 + retorno_aa) ** (1 / 12) - 1
    pat, ap = inicial, aporte
    for m in range(1, limite_meses + 1):
        if m > 1 and (m - 1) % 12 == 0:
            ap *= 1 + aumento_aa
        pat = pat * (1 + r) + ap
        if pat >= meta * (1 + inflacao_aa) ** (m / 12):
            return m
    return None


def aporte_necessario(meta: float, inicial: float, retorno_aa: float, meses: int, aumento_aa: float = 0.0,
                      inflacao_aa: float = 0.0) -> float:
    """Aporte mensal (no 1º ano) para chegar à meta em `meses`, no caminho médio."""
    lo, hi = 0.0, meta
    for _ in range(60):
        mid = (lo + hi) / 2
        m = meses_ate(meta, inicial, mid, retorno_aa, aumento_aa, inflacao_aa, meses)
        if m is not None and m <= meses:
            hi = mid
        else:
            lo = mid
    return hi


def simular(meta: float, inicial: float, aporte: float, retorno_aa: float, volatilidade_aa: float,
            aumento_aa: float = 0.0, inflacao_aa: float = 0.0, anos: int = 40, n: int = 5000, semente: int = 42) -> dict:
    """Monte Carlo. Retorna faixas do patrimônio por ano e a chance de ter atingido a meta até cada ano."""
    rng = np.random.default_rng(semente)
    meses = anos * 12
    sig = volatilidade_aa / math.sqrt(12)
    mu = math.log(1 + retorno_aa) / 12 - sig ** 2 / 2  # conservador: o retorno informado é a MÉDIA, a mediana fica abaixo
    sig = volatilidade_aa / math.sqrt(12)
    fatores = np.exp(rng.normal(mu, sig, size=(n, meses)))
    aportes = aporte * (1 + aumento_aa) ** (np.arange(meses) // 12)
    metas = meta * (1 + inflacao_aa) ** (np.arange(1, meses + 1) / 12)
    pat = np.full(n, float(inicial))
    caminho = np.empty((n, meses))
    for m in range(meses):
        pat = pat * fatores[:, m] + aportes[m]
        caminho[:, m] = pat
    atingiu = caminho >= metas
    primeiro = np.where(atingiu.any(axis=1), atingiu.argmax(axis=1) + 1, np.nan)
    anos_idx = np.arange(12, meses + 1, 12) - 1
    faixas = pd.DataFrame({
        "ano": np.arange(1, anos + 1),
        "investido": inicial + np.cumsum(aportes)[anos_idx],
        "pessimista": np.percentile(caminho[:, anos_idx], 10, axis=0),
        "mediana": np.percentile(caminho[:, anos_idx], 50, axis=0),
        "otimista": np.percentile(caminho[:, anos_idx], 90, axis=0),
        "meta": metas[anos_idx],
        "chance_ate_ano": [(primeiro <= (a * 12)).mean() for a in range(1, anos + 1)],
    })

    def quantil(q):
        v = np.nanpercentile(primeiro, q) if np.isfinite(primeiro).mean() * 100 >= q else np.nan
        return None if v != v else int(math.ceil(v))

    return {"faixas": faixas, "meses_10": quantil(10), "meses_50": quantil(50), "meses_90": quantil(90),
            "chance_total": float(np.isfinite(primeiro).mean())}


def alavancas(meta: float, inicial: float, aporte: float, retorno_aa: float, aumento_aa: float,
              inflacao_aa: float = 0.0) -> pd.DataFrame:
    """O que mais encurta o caminho (no caminho médio)."""
    base = meses_ate(meta, inicial, aporte, retorno_aa, aumento_aa, inflacao_aa)
    linhas = [("Seu plano atual", aporte, retorno_aa, aumento_aa)]
    for extra in (250, 500, 1000, 2000):
        linhas.append((f"Aportar R$ {extra:,.0f} a mais por mês".replace(",", "."), aporte + extra, retorno_aa, aumento_aa))
    linhas += [("Aumentar o aporte 10% ao ano (em vez do atual)", aporte, retorno_aa, 0.10),
               ("Rentabilidade 2 pontos maior", aporte, retorno_aa + 0.02, aumento_aa),
               ("Rentabilidade 2 pontos menor", aporte, retorno_aa - 0.02, aumento_aa)]
    saida = []
    for nome, ap, ret, aum in linhas:
        m = meses_ate(meta, inicial, ap, ret, aum, inflacao_aa)
        saida.append({"cenario": nome, "aporte": ap, "retorno": ret, "meses": m,
                      "diferenca_meses": (m - base) if m is not None and base is not None else None})
    return pd.DataFrame(saida)


def fmt_tempo(meses: int | None) -> str:
    if meses is None:
        return "não chega em 60 anos"
    a, m = divmod(meses, 12)
    if a == 0:
        return f"{m} meses"
    return f"{a} ano{'s' if a > 1 else ''}" + (f" e {m} {'meses' if m > 1 else 'mês'}" if m else "")
