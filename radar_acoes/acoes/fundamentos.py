"""Análise profunda dos balanços: Piotroski F-score, fluxo de caixa livre, segurança dos dividendos e
preço justo pelo modelo de dividendos descontados (Gordon).

Fontes: demonstrações anuais do Yahoo Finance (DRE, balanço e fluxo de caixa dos últimos anos).
Quando um dado não existe (comum em bancos), o teste é pulado e a nota considera só os testes disponíveis.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FINANCEIRAS = ("Bancos", "Seguros", "Holdings", "Bolsa e serviços financeiros")


def _chave(s: str) -> str:
    return "".join(ch for ch in str(s).lower() if ch.isalnum())


def _linha(df: pd.DataFrame | None, nomes: list[str]) -> list[float]:
    """Valores anuais (mais recente primeiro) da primeira linha encontrada entre `nomes`."""
    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return []
    idx = {_chave(i): i for i in df.index}
    for n in nomes:
        k = idx.get(_chave(n))
        if k is not None:
            s = pd.to_numeric(df.loc[k], errors="coerce")
            s = s[sorted(s.index, reverse=True)] if all(isinstance(c, pd.Timestamp) for c in s.index) else s
            return [float(v) if v == v else float("nan") for v in s.values]
    return []


def _v(lst: list[float], i: int) -> float:
    return lst[i] if len(lst) > i and lst[i] == lst[i] else float("nan")


def extrair(demos: dict | None) -> dict:
    demos = demos or {}
    dre, bal, flx = demos.get("dre"), demos.get("balanco"), demos.get("fluxo")
    return {
        "lucro": _linha(dre, ["Net Income", "Net Income Common Stockholders", "Net Income Continuous Operations"]),
        "receita": _linha(dre, ["Total Revenue", "Operating Revenue"]),
        "lucro_bruto": _linha(dre, ["Gross Profit"]),
        "ativos": _linha(bal, ["Total Assets"]),
        "ativo_circ": _linha(bal, ["Current Assets"]),
        "passivo_circ": _linha(bal, ["Current Liabilities"]),
        "divida_lp": _linha(bal, ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"]),
        "acoes": _linha(bal, ["Ordinary Shares Number", "Share Issued"]),
        "fco": _linha(flx, ["Operating Cash Flow", "Cash Flow From Continuing Operating Activities"]),
        "capex": _linha(flx, ["Capital Expenditure"]),
        "fcl": _linha(flx, ["Free Cash Flow"]),
        "dividendos_pagos": _linha(flx, ["Cash Dividends Paid", "Common Stock Dividend Paid"]),
    }


def piotroski(f: dict) -> dict:
    """F-score de Piotroski (0–9). Retorna pontos, testes disponíveis, nota equivalente em 9 e o detalhe."""
    testes: list[tuple[str, bool]] = []

    def teste(nome, a, b=None, cond=None):
        if any(x != x for x in ([a] if b is None else [a, b])):
            return
        testes.append((nome, bool(cond(a) if b is None else cond(a, b))))

    ni0, ni1 = _v(f["lucro"], 0), _v(f["lucro"], 1)
    ta0, ta1, ta2 = _v(f["ativos"], 0), _v(f["ativos"], 1), _v(f["ativos"], 2)
    roa0 = ni0 / ta1 if ta1 == ta1 and ta1 else (ni0 / ta0 if ta0 else float("nan"))
    roa1 = ni1 / ta2 if ta2 == ta2 and ta2 else (ni1 / ta1 if ta1 else float("nan"))
    cfo0 = _v(f["fco"], 0)
    teste("Lucro sobre ativos positivo", roa0, cond=lambda a: a > 0)
    teste("Geração de caixa operacional positiva", cfo0, cond=lambda a: a > 0)
    teste("Rentabilidade (ROA) melhorou", roa0, roa1, lambda a, b: a > b)
    teste("Caixa operacional maior que o lucro (lucro de qualidade)", cfo0, ni0, lambda a, b: a > b)
    lev0 = _v(f["divida_lp"], 0) / ta0 if ta0 else float("nan")
    lev1 = _v(f["divida_lp"], 1) / ta1 if ta1 else float("nan")
    teste("Endividamento de longo prazo caiu", lev0, lev1, lambda a, b: a <= b)
    lc0 = _v(f["ativo_circ"], 0) / _v(f["passivo_circ"], 0) if _v(f["passivo_circ"], 0) else float("nan")
    lc1 = _v(f["ativo_circ"], 1) / _v(f["passivo_circ"], 1) if _v(f["passivo_circ"], 1) else float("nan")
    teste("Liquidez corrente melhorou", lc0, lc1, lambda a, b: a > b)
    teste("Não emitiu novas ações", _v(f["acoes"], 0), _v(f["acoes"], 1), lambda a, b: a <= b * 1.005)
    mb0 = _v(f["lucro_bruto"], 0) / _v(f["receita"], 0) if _v(f["receita"], 0) else float("nan")
    mb1 = _v(f["lucro_bruto"], 1) / _v(f["receita"], 1) if _v(f["receita"], 1) else float("nan")
    teste("Margem bruta melhorou", mb0, mb1, lambda a, b: a > b)
    gi0 = _v(f["receita"], 0) / ta1 if ta1 == ta1 and ta1 else float("nan")
    gi1 = _v(f["receita"], 1) / ta2 if ta2 == ta2 and ta2 else float("nan")
    teste("Giro dos ativos melhorou", gi0, gi1, lambda a, b: a > b)
    n = len(testes)
    pontos = sum(ok for _, ok in testes)
    return {"f_score": pontos, "f_testes": n, "f_score_9": round(pontos / n * 9, 1) if n >= 5 else float("nan"),
            "f_detalhe": [("✅ " if ok else "❌ ") + nome for nome, ok in testes]}


def caixa(f: dict, preco: float, proventos_12m: float) -> dict:
    """Fluxo de caixa livre e quanto dele os dividendos consomem."""
    fcl = _v(f["fcl"], 0)
    if fcl != fcl:
        fco, capex = _v(f["fco"], 0), _v(f["capex"], 0)
        fcl = fco + capex if fco == fco and capex == capex else float("nan")  # capex vem negativo
    acoes = _v(f["acoes"], 0)
    div = abs(_v(f["dividendos_pagos"], 0))
    fcl_acao = fcl / acoes if acoes and acoes == acoes and fcl == fcl else float("nan")
    payout_fcl = div / fcl if fcl == fcl and fcl > 0 and div == div else (float("inf") if fcl == fcl and fcl <= 0 and div > 0 else float("nan"))
    return {"fcl": fcl, "fcl_por_acao": fcl_acao,
            "fcl_yield": fcl_acao / preco if preco and fcl_acao == fcl_acao else float("nan"),
            "payout_fcl": payout_fcl}


def seguranca_dividendos(i: dict) -> dict:
    """Seis checagens objetivas (no espírito do 'Snowflake'): nota 0–100 = checagens aprovadas ÷ disponíveis."""
    fin = i.get("setor") in FINANCEIRAS
    checks: list[tuple[str, bool]] = []

    def chk(nome, valor, ok):
        if valor is None or (isinstance(valor, float) and valor != valor):
            return
        checks.append((nome, bool(ok(valor))))

    chk("Paga até 90% do lucro (sobra para crescer)", i.get("payout"), lambda v: 0 < v <= 0.90)
    chk("Dividendos cobertos pelo caixa livre", i.get("payout_fcl"), lambda v: v <= 1.0)
    chk("Saúde financeira (Piotroski ≥ 6 de 9)", i.get("f_score_9"), lambda v: v >= 6)
    chk("Pagou em 8+ dos últimos 10 anos", i.get("anos_pagou_10"), lambda v: v >= 8)
    chk("Proventos sem tendência de queda", i.get("cresc_proventos_5a"), lambda v: v >= -0.05)
    if fin:
        chk("Rentabilidade sólida (ROE ≥ 12%)", i.get("roe"), lambda v: v >= 0.12)
    else:
        chk("Dívida controlada (≤ 1,5× patrimônio)", i.get("divida_pl"), lambda v: v <= 1.5)
    n = len(checks)
    return {"seguranca_div": round(100 * sum(ok for _, ok in checks) / n) if n >= 3 else float("nan"),
            "seguranca_checks": [("✅ " if ok else "❌ ") + nome for nome, ok in checks]}


def taxa_desconto(selic: float | None) -> float:
    """Retorno exigido de uma ação de renda: parte fixa de longo prazo + parte que acompanha a Selic de hoje."""
    s = 0.12 if selic is None or selic != selic else selic
    return float(np.clip(0.12 + 0.25 * (s - 0.10), 0.10, 0.16))


def preco_justo_ddm(proventos_media: float, crescimento: float | None, selic: float | None) -> float:
    """Modelo de Gordon: P = D1 / (k − g), com g limitado a 0–5% ao ano e k pela taxa_desconto."""
    if not proventos_media or proventos_media <= 0:
        return float("nan")
    g = 0.0 if crescimento is None or crescimento != crescimento else float(np.clip(crescimento, 0.0, 0.05))
    k = taxa_desconto(selic)
    return proventos_media * (1 + g) / (k - g) if k - g > 0.02 else float("nan")


def analisar(i: dict, demos: dict | None, selic: float | None = None) -> dict:
    f = extrair(demos)
    out = {}
    out.update(piotroski(f))
    out.update(caixa(f, i.get("preco"), i.get("proventos_12m") or 0.0))
    ddm = preco_justo_ddm(i.get("proventos_media_5a") or 0.0, i.get("cresc_proventos_5a"), selic)
    out["preco_justo_ddm"] = ddm
    out["margem_ddm"] = ddm / i["preco"] - 1 if ddm == ddm and i.get("preco") else float("nan")
    out["taxa_desconto"] = taxa_desconto(selic)
    out.update(seguranca_dividendos({**i, **out}))
    return out

