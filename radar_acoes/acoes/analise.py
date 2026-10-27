"""Indicadores de renda, qualidade e preço; preço-teto (Bazin) e preço justo (Graham); nota de 0 a 100."""
from __future__ import annotations

import math
from datetime import date

import numpy as np
import pandas as pd

from . import fundamentos, universo

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


def proventos_por_ano(proventos: pd.Series, hoje: pd.Timestamp | None = None, primeiro_ano: int | None = None) -> pd.Series:
    """Soma por ano civil dos anos completos (exclui o ano corrente), COM ZERO nos anos em que não pagou.

    `primeiro_ano`: primeiro ano inteiro com cotação. Sem os zeros, quem pagou em 2 de 5 anos parecia pagar todo ano
    (a média, o preço-teto e o crescimento saíam inflados)."""
    hoje = hoje or pd.Timestamp(date.today())
    if proventos.empty and primeiro_ano is None:
        return pd.Series(dtype=float)
    anual = proventos.groupby(proventos.index.year).sum() if not proventos.empty else pd.Series(dtype=float)
    ini = primeiro_ano if primeiro_ano is not None else int(anual.index.min())
    if ini >= hoje.year:
        return pd.Series(dtype=float)
    return anual.reindex(range(ini, hoje.year), fill_value=0.0).astype(float)


def indicadores(d: dict, hoje: pd.Timestamp | None = None) -> dict:
    hoje = hoje or pd.Timestamp(date.today())
    info, precos, prov = d["info"], d["precos"], d["proventos"]
    t = d["ticker"]
    preco = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
    if (np.isnan(preco) or d.get("info_antiga")) and not precos.empty:
        preco = float(precos.iloc[-1])  # indicadores de outro dia: o preço vem do histórico, que é de hoje

    # ---- Proventos (dividendos + JCP, pela data-ex) ----
    ult12 = float(prov[prov.index > hoje - pd.DateOffset(years=1)].sum()) if not prov.empty else 0.0
    primeiro = int(precos.index.min().year) + 1 if not precos.empty else None
    anual = proventos_por_ano(prov, hoje, primeiro)
    anos10 = anual[anual.index >= hoje.year - 10]
    anos_pagou = int((anos10 > 0).sum())
    anos_hist = max(1, min(10, hoje.year - int(precos.index.min().year))) if not precos.empty else 1
    media5 = float(anual[anual.index >= hoje.year - 5].mean()) if len(anual) else 0.0
    media3 = float(anual[anual.index >= hoje.year - 3].mean()) if len(anual) else 0.0
    ult5 = anual[anual.index >= hoje.year - 5]
    if len(ult5) >= 3 and ult5.iloc[0] > 0 and ult5.iloc[-1] > 0:
        cagr_div = (ult5.iloc[-1] / ult5.iloc[0]) ** (1 / (ult5.index[-1] - ult5.index[0])) - 1
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
    p6 = precos[precos.index <= hoje - pd.DateOffset(months=6)]
    var6 = float(precos.iloc[-1] / p6.iloc[-1] - 1) if len(p6) else np.nan

    # ---- Fundamentos ----
    lpa, vpa = _num(info.get("trailingEps")), _num(info.get("bookValue"))
    pl = preco / lpa if lpa and lpa > 0 else _num(info.get("trailingPE"))
    pvp = preco / vpa if vpa and vpa > 0 else _num(info.get("priceToBook"))
    if pvp == pvp and pvp <= 0:
        pvp = np.nan  # patrimônio negativo: P/VP negativo NÃO é "barato" (antes ganhava a melhor nota)
    roe = _num(info.get("returnOnEquity"))
    if np.isnan(roe) and lpa and vpa and vpa > 0:
        roe = lpa / vpa
    margem = _num(info.get("profitMargins"))
    div_pl = _num(info.get("debtToEquity"))
    div_pl = div_pl / 100 if not np.isnan(div_pl) else np.nan  # Yahoo informa em %
    if div_pl == div_pl and div_pl < 0:
        div_pl = np.nan  # dívida/patrimônio negativo = patrimônio negativo; não pode contar como "pouca dívida"
    payout = (ult12 / lpa) if lpa and lpa > 0 else _num(info.get("payoutRatio"))
    cresc_lucro = _num(info.get("earningsGrowth"))

    # ---- Preço-teto e preço justo ----
    base_div = media5 if media5 > 0 else ult12
    teto_bazin = base_div / DY_MINIMO_BAZIN if base_div > 0 else np.nan
    graham = math.sqrt(22.5 * lpa * vpa) if lpa and vpa and lpa > 0 and vpa > 0 else np.nan
    margem_bazin = teto_bazin / preco - 1 if teto_bazin == teto_bazin and preco else np.nan
    margem_graham = graham / preco - 1 if graham == graham and preco else np.nan

    alvo = _num(info.get("targetMeanPrice"))
    preco_hist = float(precos.iloc[-1]) if not precos.empty else np.nan
    return {
        "ticker": t, "nome": info.get("longName") or info.get("shortName") or t,
        "data_cotacao": precos.index[-1].date().isoformat() if not precos.empty else None,
        "preco_historico": preco_hist,
        "proventos_mediana_pagamento": float(prov[prov.index > hoje - pd.DateOffset(years=5)].median()) if not prov.empty else np.nan,
        "setor": universo.setor(t, info.get("sector")), "preco": preco, "var_dia": var_dia, "var_12m": var12, "var_6m": var6,
        "dy_12m": ult12 / preco if preco else np.nan, "dy_medio_5a": media5 / preco if preco else np.nan,
        "proventos_12m": ult12, "proventos_media_5a": media5, "proventos_media_3a": media3,
        "anos_pagou_10": anos_pagou, "anos_historico": anos_hist, "cresc_proventos_5a": cagr_div,
        "estabilidade_proventos": cv_div, "meses_pagamento": meses_pag,
        "pl_fonte": _num(info.get("trailingPE")), "moeda_balanco": info.get("financialCurrency"), "info_antiga": bool(d.get("info_antiga")),
        "pl": pl, "pvp": pvp, "roe": roe, "margem_liquida": margem, "divida_pl": div_pl, "payout": payout,
        "cresc_lucro": cresc_lucro, "lpa": lpa, "vpa": vpa, "volatilidade": vol, "queda_max_5a": queda_max,
        "preco_teto_bazin": teto_bazin, "margem_bazin": margem_bazin, "preco_justo_graham": graham,
        "margem_graham": margem_graham, "alvo_analistas": alvo,
        "potencial_analistas": alvo / preco - 1 if alvo == alvo and preco else np.nan,
        "recomendacao_analistas": info.get("recommendationKey"),
        "ex_dividendo": _data_ex(info.get("exDividendDate")),
        "proximo_balanco": _proximo_balanco(info, hoje),
        "ultimo_provento_data": prov.index[-1].date().isoformat() if not prov.empty else None,
        "ultimo_provento_valor": float(prov.iloc[-1]) if not prov.empty else np.nan,
    }


def _data_ex(v):
    try:
        return pd.Timestamp(int(v), unit="s").date().isoformat() if v else None
    except (TypeError, ValueError):
        return None


def _proximo_balanco(info: dict, hoje: pd.Timestamp) -> str | None:
    """Próxima divulgação de resultado informada pelo Yahoo (só datas futuras)."""
    for k in ("earningsTimestampStart", "earningsTimestamp", "earningsTimestampEnd"):
        d = _data_ex(info.get(k))
        if d and pd.Timestamp(d) >= hoje.normalize():
            return d
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
        (_escala(i.get("seguranca_div", np.nan), 30, 90), 1.3),
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
        (_escala(i.get("f_score_9", np.nan), 3, 8), 1.2),
        (_escala(i.get("payout_fcl", np.nan), 1.3, 0.6) if i.get("payout_fcl", np.nan) != float("inf") else 0.0, 0.8),
    ])
    preco = _media([
        (_escala(i["margem_bazin"], -0.40, 0.20), 1.5),
        (_escala(i["margem_graham"], -0.40, 0.30), 1),
        (_escala(i["pl"], 20, 5) if i["pl"] == i["pl"] and i["pl"] > 0 else 0.0, 1),
        (_escala(i["pvp"], 3.0, 0.8), 0.5),
        (_escala(i.get("margem_ddm", np.nan), -0.40, 0.20), 1.0),
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
    if i.get("lpa") != i.get("lpa"):
        return "Aguardar"  # lucro não informado pela fonte: sem dado não se compra, mas também não se condena
    if i["lpa"] <= 0:
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


def confianca(i: dict, hoje: pd.Timestamp | None = None) -> tuple[str, list[str]]:
    """Confere se os dados fazem sentido. Retorna ('Alta'|'Média'|'Baixa', avisos)."""
    hoje = hoje or pd.Timestamp(date.today())
    avisos, grave = [], False
    if i.get("data_cotacao"):
        atraso = len(pd.bdate_range(pd.Timestamp(i["data_cotacao"]), hoje)) - 1
        if atraso > 4:
            avisos.append(f"cotação desatualizada (última de {pd.Timestamp(i['data_cotacao']):%d/%m/%Y})")
            grave = True
    ph, p = i.get("preco_historico"), i.get("preco")
    if ph == ph and p and abs(p / ph - 1) > 0.10:
        avisos.append(f"preço diferente entre as fontes (R$ {p:.2f} × R$ {ph:.2f})")
        grave = True
    if i["dy_12m"] == i["dy_12m"] and i["dy_12m"] > 0.25:
        avisos.append("DY dos últimos 12 meses acima de 25%: provável provento extraordinário (não se repete) ou erro")
    up, med = i.get("ultimo_provento_valor"), i.get("proventos_mediana_pagamento")
    if up == up and med == med and med and up > 4 * med:
        avisos.append("último provento muito acima do normal (extraordinário?)")
    if i["lpa"] != i["lpa"] or i["vpa"] != i["vpa"]:
        avisos.append("lucro ou patrimônio por ação não informados pela fonte")
    pe_fonte = i.get("pl_fonte")
    if i.get("pl") == i.get("pl") and pe_fonte == pe_fonte and pe_fonte and pe_fonte > 0 and abs(i["pl"] / pe_fonte - 1) > 0.30:
        avisos.append(f"P/L calculado ({i['pl']:.1f}) difere do informado pela fonte ({pe_fonte:.1f}): lucro por ação pode estar em outra base (units?)")
        grave = True
    if i.get("moeda_balanco") and i["moeda_balanco"] != "BRL":
        avisos.append(f"balanço em {i['moeda_balanco']}: lucro e patrimônio por ação não estão em reais")
        grave = True
    if i.get("info_antiga"):
        avisos.append("indicadores de um dia anterior (a fonte falhou hoje); preço e proventos estão atualizados")
    if i["anos_historico"] < 5:
        avisos.append(f"pouco histórico na bolsa ({i['anos_historico']} anos)")
    nivel = "Baixa" if grave or len(avisos) >= 3 else "Média" if avisos else "Alta"
    return nivel, avisos


def _p(x) -> str:
    return f"{x * 100:.1f}%".replace(".", ",")


def _r(x) -> str:
    return f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def explicar(i: dict) -> str:
    """Por que a ação está onde está, em português simples."""
    partes = []
    if i["proventos_media_5a"] > 0:
        partes.append(f"paga em média {_r(i['proventos_media_5a'])} por ação por ano ({_p(i['dy_medio_5a'])} do preço de hoje) "
                      f"e pagou em {i['anos_pagou_10']} dos últimos {min(10, i['anos_historico'])} anos")
    else:
        partes.append("não pagou proventos nos últimos anos")
    mb = i["margem_bazin"]
    if mb == mb:
        razao = 1 / (1 + mb)  # preço ÷ teto
        partes.append(f"está {_p(1 - razao)} abaixo do preço-teto" if mb >= 0 else f"está {_p(razao - 1)} acima do preço-teto (cara para renda)")
    if i["roe"] == i["roe"]:
        partes.append(f"lucra {_p(i['roe'])} ao ano sobre o patrimônio (ROE)")
    if i["lpa"] == i["lpa"] and i["lpa"] <= 0:
        partes.append("está dando PREJUÍZO")
    if i["queda_max_5a"] == i["queda_max_5a"] and i["queda_max_5a"] < -0.45:
        partes.append(f"já caiu {_p(-i['queda_max_5a'])} do topo nos últimos 5 anos (oscila muito)")
    texto = "; ".join(partes)
    return texto[0].upper() + texto[1:] + "."


def ranking(dados: dict[str, dict], noticias_saldo: dict[str, float] | None = None,
            hoje: pd.Timestamp | None = None, selic: float | None = None) -> pd.DataFrame:
    noticias_saldo = noticias_saldo or {}
    linhas = []
    for t, d in dados.items():
        try:
            i = indicadores(d, hoje)
        except Exception as e:  # noqa: BLE001
            print(f"  [aviso] {t}: não deu para calcular ({e})")
            continue
        try:
            i.update(fundamentos.analisar(i, d.get("demos"), selic))
        except Exception as e:  # noqa: BLE001
            print(f"  [aviso] {t}: balanços indisponíveis ({e})")
        i.update(nota(i, noticias_saldo.get(t, 0.0)))
        i["confianca"], avisos = confianca(i, hoje)
        i["avisos_dados"] = " · ".join(avisos)
        i["sinal"] = sinal(i)
        if i["sinal"] == "Comprar" and i["confianca"] == "Baixa":
            i["sinal"] = "Acumular"  # dado duvidoso: não damos "Comprar" sem conferir
        i["por_que"] = explicar(i)
        i["conferir"] = f"https://statusinvest.com.br/acoes/{t.lower()}"
        linhas.append(i)
    if not linhas:
        return pd.DataFrame()
    df = pd.DataFrame(linhas).sort_values("nota", ascending=False).reset_index(drop=True)
    df.insert(0, "posicao", range(1, len(df) + 1))
    return graus_setoriais(df)


# ------------------------------------------------------------------ notas por fator, comparando com o próprio setor
FATORES = {
    "Valor": [("margem_bazin", 1), ("margem_ddm", 1), ("pl", -1), ("pvp", -1)],
    "Renda": [("dy_medio_5a", 1), ("seguranca_div", 1), ("cresc_proventos_5a", 1), ("anos_pagou_10", 1)],
    "Qualidade": [("roe", 1), ("margem_liquida", 1), ("f_score_9", 1)],
    "Saúde": [("divida_pl", -1), ("payout_fcl", -1), ("volatilidade", -1), ("queda_max_5a", 1)],
    "Momento": [("var_12m", 1), ("var_6m", 1)],
}
GRAUS = [(0.92, "A+"), (0.82, "A"), (0.72, "A-"), (0.62, "B+"), (0.52, "B"), (0.42, "B-"), (0.32, "C"), (0.20, "D")]


def _grau(p: float) -> str:
    if p != p:
        return "—"
    return next((g for lim, g in GRAUS if p >= lim), "F")


def graus_setoriais(df: pd.DataFrame) -> pd.DataFrame:
    """Para cada fator, o percentil da ação dentro do seu setor (setor com < 4 ações: compara com todas)."""
    df = df.copy()
    if "var_6m" not in df:
        df["var_6m"] = np.nan
    for fator, metricas in FATORES.items():
        partes = []
        for col, sentido in metricas:
            if col not in df:
                continue
            x = pd.to_numeric(df[col], errors="coerce").replace([np.inf, -np.inf], np.nan) * sentido
            if col == "divida_pl":
                x = x.where(~df["setor"].isin(fundamentos.FINANCEIRAS))
            tam = df.groupby("setor")["ticker"].transform("size")
            no_setor = x.groupby(df["setor"]).rank(pct=True)
            geral = x.rank(pct=True)
            partes.append(no_setor.where(tam >= 4, geral))
        pct = pd.concat(partes, axis=1).mean(axis=1, skipna=True) if partes else pd.Series(np.nan, index=df.index)
        df[f"pct_{fator}"] = (pct * 100).round(0)
        df[f"grau_{fator}"] = pct.map(_grau)
    return df
