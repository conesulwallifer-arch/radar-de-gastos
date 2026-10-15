"""Indicadores de renda, qualidade e preço; preço-teto (Bazin) e preço justo (Graham); nota de 0 a 100."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from . import universo

DY_MINIMO_BAZIN = 0.06  # Bazin: só compra se o dividendo médio render pelo menos 6% ao ano


def _escala(x, ruim, bom) -> float:
    """Converte x para 0..1 (linear entre 'ruim' e 'bom'; funciona também quando menor é melhor)."""
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return np.nan
    v = (x - ruim) / (bom - ruim)
    return float(min(1.0, max(0.0, v)))


def _media(pares: list[tuple[float, float]]) -> float:
    """Média ponderada ignorando os itens sem dado (NaN)."""
    ok = [(v, p) for v, p in pares if v == v and v is not None]
    return sum(v * p for v, p in ok) / sum(p for _, p in ok) if ok else np.nan


def _num(v):
    try:
        v = float(v)
        return v if math.isfinite(v) else np.nan
    except (TypeError, ValueError):
        return np.nan


def proventos_por_ano(proventos: pd.Series, hoje: pd.Timestamp | None = None) -> pd.Series:
    """Soma por ano civil dos anos completos (exclui o ano corrente)."""
    hoje = hoje or pd.Timestamp(date.today())
    if proventos.empty:
        return pd.Series(dtype=float)
    anual = proventos.groupby(proventos.index.year).sum()
    return anual[anual.index < hoje.year]


def indicadores(d: dict, hoje: pd.Timestamp | None = None) -> dict:
    hoje = hoje or pd.Timestamp(date.today())
    info, precos, prov = d["info"], d["precos"], d["proventos"]
    t = d["ticker"]
    preco = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
    if np.isnan(preco) and not precos.empty:
        preco = float(precos.iloc[-1])

    # ---- Proventos (dividendos + JCP, pela data-ex) ----
    ult12 = float(prov[prov.index > hoje - pd.DateOffset(years=1)].sum()) if not prov.empty else 0.0
    anual = proventos_por_ano(prov, hoje)
    anos10 = anual[anual.index >= hoje.year - 10]
    anos_pagou = int((anos10 > 0).sum())
    anos_hist = max(1, min(10, hoje.year - int(precos.index.min().year))) if not precos.empty else 1
    media5 = float(anual[anual.index >= hoje.year - 5].mean()) if len(anual) else 0.0
    media3 = float(anual[anual.index >= hoje.year - 3].mean()) if len(anual) else 0.0
    ult5 = anual[anual.index >= hoje.year - 5]
    if len(ult5) >= 3 and ult5.iloc[0] > 0 and ult5.iloc[-1] > 0:
        cagr_div = (ult5.iloc[-1] / ult5.iloc[0]) ** (1 / (len(ult5) - 1)) - 1
    else:
        cagr_div = np.nan
    cv_div = float(ult5.std() / ult5.mean()) if len(ult5) >= 3 and ult5.mean() > 0 else np.nan
    meses_pag = sorted(set(prov[prov.index > hoje - pd.DateOffset(years=3)].index.month)) if not prov.empty else []

    # ---- Preço e risco ----
    p5 = precos[precos.index > hoje - pd.DateOffset(years=5)]
    ret = np.log(p5).diff().dropna()
    vol = float(ret.std() * np.sqrt(252)) if len(ret) > 20 else np.nan
    queda_max = float((p5 / p5.cummax() - 1).min()) if len(p5) else np.nan
    var12 = float(precos.iloc[-1] / precos[precos.index <= hoje - pd.DateOffset(years=1)].iloc[-1] - 1) \
        if len(precos[precos.index <= hoje - pd.DateOffset(years=1)]) else np.nan
    var_dia = float(precos.iloc[-1] / precos.iloc[-2] - 1) if len(precos) > 1 else np.nan

    # ---- Fundamentos ----
    lpa, vpa = _num(info.get("trailingEps")), _num(info.get("bookValue"))
    pl = preco / lpa if lpa and lpa > 0 else _num(info.get("trailingPE"))
    pvp = preco / vpa if vpa and vpa > 0 else _num(info.get("priceToBook"))
    roe = _num(info.get("returnOnEquity"))
    if np.isnan(roe) and lpa and vpa and vpa > 0:
        roe = lpa / vpa
    margem = _num(info.get("profitMargins"))
    div_pl = _num(info.get("debtToEquity"))
    div_pl = div_pl / 100 if not np.isnan(div_pl) else np.nan  # Yahoo informa em %
    payout = (ult12 / lpa) if lpa and lpa > 0 else _num(info.get("payoutRatio"))
    cresc_lucro = _num(info.get("earningsGrowth"))

    # ---- Preço-teto e preço justo ----
    base_div = media5 if media5 > 0 else ult12
    teto_bazin = base_div / DY_MINIMO_BAZIN if base_div > 0 else np.nan
    graham = math.sqrt(22.5 * lpa * vpa) if lpa and vpa and lpa > 0 and vpa > 0 else np.nan
    margem_bazin = teto_bazin / preco - 1 if teto_bazin == teto_bazin and preco else np.nan
    margem_graham = graham / preco - 1 if graham == graham and preco else np.nan

    alvo = _num(info.get("targetMeanPrice"))
    return {
        "ticker": t, "nome": info.get("longName") or info.get("shortName") or t,
        "setor": universo.setor(t, info.get("sector")), "preco": preco, "var_dia": var_dia, "var_12m": var12,
        "dy_12m": ult12 / preco if preco else np.nan, "dy_medio_5a": media5 / preco if preco else np.nan,
        "proventos_12m": ult12, "proventos_media_5a": media5, "proventos_media_3a": media3,
        "anos_pagou_10": anos_pagou, "anos_historico": anos_hist, "cresc_proventos_5a": cagr_div,
        "estabilidade_proventos": cv_div, "meses_pagamento": meses_pag,
        "pl": pl, "pvp": pvp, "roe": roe, "margem_liquida": margem, "divida_pl": div_pl, "payout": payout,
        "cresc_lucro": cresc_lucro, "lpa": lpa, "vpa": vpa, "volatilidade": vol, "queda_max_5a": queda_max,
        "preco_teto_bazin": teto_bazin, "margem_bazin": margem_bazin, "preco_justo_graham": graham,
        "margem_graham": margem_graham, "alvo_analistas": alvo,
        "potencial_analistas": alvo / preco - 1 if alvo == alvo and preco else np.nan,
        "recomendacao_analistas": info.get("recommendationKey"),
        "ex_dividendo": _data_ex(info.get("exDividendDate")),
        "ultimo_provento_data": prov.index[-1].date().isoformat() if not prov.empty else None,
        "ultimo_provento_valor": float(prov.iloc[-1]) if not prov.empty else np.nan,
    }


def _data_ex(v):
    try:
        return pd.Timestamp(int(v), unit="s").date().isoformat() if v else None
    except (TypeError, ValueError):
        return None


PESOS = {"renda": 0.40, "qualidade": 0.30, "preco": 0.20, "risco": 0.10}


def nota(i: dict, saldo_noticias: float = 0.0) -> dict:
    """Nota 0–100 pensada para longo prazo com foco em renda passiva."""
    financeira = i["setor"] in ("Bancos", "Seguros", "Holdings", "Bolsa e serviços financeiros")
    dy = i["dy_medio_5a"] if i["dy_medio_5a"] == i["dy_medio_5a"] and i["dy_medio_5a"] > 0 else i["dy_12m"]
    # DY muito alto costuma ser pagamento extraordinário (não se repete): limita a nota acima de 14%
    s_dy = _escala(dy, 0.02, 0.09) if dy != dy or dy <= 0.14 else max(0.5, 1 - (dy - 0.14) * 5)
    renda = _media([
        (s_dy, 1.5),
        (_escala(i["anos_pagou_10"] / max(1, min(10, i["anos_historico"])), 0.5, 1.0), 1),
        (_escala(i["cresc_proventos_5a"], -0.05, 0.10), 1),
        (_escala(i["estabilidade_proventos"], 0.8, 0.15), 1),
    ])
    payout = i["payout"]
    s_payout = np.nan if payout != payout else (
        1.0 if 0.25 <= payout <= 0.90 else 0.6 if payout < 0.25 else max(0.0, 1 - (payout - 0.90) * 2))
    qualidade = _media([
        (_escala(i["roe"], 0.05, 0.22), 1.5),
        (_escala(i["margem_liquida"], 0.0, 0.20), 1),
        (np.nan if financeira else _escala(i["divida_pl"], 2.0, 0.3), 1),
        (s_payout, 1),
        (1.0 if i["lpa"] == i["lpa"] and i["lpa"] > 0 else 0.0, 1),
    ])
    preco = _media([
        (_escala(i["margem_bazin"], -0.40, 0.20), 1.5),
        (_escala(i["margem_graham"], -0.40, 0.30), 1),
        (_escala(i["pl"], 20, 5) if i["pl"] == i["pl"] and i["pl"] > 0 else 0.0, 1),
        (_escala(i["pvp"], 3.0, 0.8), 0.5),
    ])
    risco = _media([
        (_escala(i["volatilidade"], 0.50, 0.18), 1),
        (_escala(i["queda_max_5a"], -0.60, -0.20), 1),
    ])
    partes = {"renda": renda, "qualidade": qualidade, "preco": preco, "risco": risco}
    total = sum(PESOS[k] * (0.0 if v != v else v) for k, v in partes.items())
    total += 0.03 * saldo_noticias  # notícias mexem pouco: no máximo ±3 pontos
    total = max(0.0, min(1.0, total))
    return {**{f"nota_{k}": round(100 * (0 if v != v else v), 1) for k, v in partes.items()},
            "nota": round(100 * total, 1)}


DY_MINIMO_RENDA = 0.04  # abaixo disso a ação não serve ao objetivo de renda, mesmo sendo boa


def sinal(i: dict) -> str:
    """Comprar / Acumular / Aguardar (boa, mas cara ou paga pouco) / Evitar."""
    n, mb = i["nota"], i["margem_bazin"]
    barata = mb == mb and mb >= 0
    if i.get("lpa") != i.get("lpa") or (i.get("lpa") or 0) <= 0:
        return "Evitar"
    dy = i.get("dy_medio_5a")
    if dy != dy or dy is None or dy < DY_MINIMO_RENDA:
        return "Aguardar" if n >= 55 else "Evitar"
    if n >= 65 and barata:
        return "Comprar"
    if n >= 55 and (barata or (mb == mb and mb >= -0.10)):
        return "Acumular"
    if n >= 55:
        return "Aguardar"
    return "Evitar"


def ranking(dados: dict[str, dict], noticias_saldo: dict[str, float] | None = None,
            hoje: pd.Timestamp | None = None) -> pd.DataFrame:
    noticias_saldo = noticias_saldo or {}
    linhas = []
    for t, d in dados.items():
        try:
            i = indicadores(d, hoje)
        except Exception as e:  # noqa: BLE001
            print(f"  [aviso] {t}: não deu para calcular ({e})")
            continue
        i.update(nota(i, noticias_saldo.get(t, 0.0)))
        i["sinal"] = sinal(i)
        linhas.append(i)
    if not linhas:
        return pd.DataFrame()
    df = pd.DataFrame(linhas).sort_values("nota", ascending=False).reset_index(drop=True)
    df.insert(0, "posicao", range(1, len(df) + 1))
    return df
