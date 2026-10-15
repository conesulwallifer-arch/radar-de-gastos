"""Juros e inflação oficiais do Banco Central (SGS), atualizados todo dia útil, com cache diário.

Séries: 432 = meta Selic (% a.a.) · 13522 = IPCA acumulado 12 meses (%) · 4391 = CDI acumulado no mês (%).
Sem internet, usa valores padrão e marca como "estimado".
"""
from __future__ import annotations

import json
from datetime import date

import pandas as pd
import requests

from . import DADOS

CACHE = DADOS / "cache"
PADRAO = {"selic": 0.14, "ipca_12m": 0.045}
URL = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{cod}/dados"


def serie(cod: int, inicio: date | None = None, ultimos: int | None = None) -> pd.Series:
    CACHE.mkdir(parents=True, exist_ok=True)
    arq = CACHE / f"bcb_{cod}_{inicio or ''}_{ultimos or ''}_{date.today():%Y%m%d}.json"
    if arq.exists():
        dados = json.loads(arq.read_text())
    else:
        if ultimos:
            url, params = URL.format(cod=cod) + f"/ultimos/{ultimos}", {"formato": "json"}
        else:
            url = URL.format(cod=cod)
            params = {"formato": "json", "dataInicial": f"{inicio or date(date.today().year - 9, 1, 1):%d/%m/%Y}",
                      "dataFinal": f"{date.today():%d/%m/%Y}"}
        r = requests.get(url, params=params, timeout=30)
        r.raise_for_status()
        dados = r.json()
        for velho in CACHE.glob(f"bcb_{cod}_*.json"):
            velho.unlink(missing_ok=True)
        arq.write_text(json.dumps(dados))
    s = pd.Series({pd.to_datetime(d["data"], dayfirst=True): float(d["valor"]) for d in dados}).sort_index()
    return s


def indicadores() -> dict:
    """{'selic', 'ipca_12m', 'cdi_liquido', 'data_selic', 'data_ipca', 'estimado'} — taxas em fração ao ano."""
    saida = {**PADRAO, "data_selic": None, "data_ipca": None, "estimado": False}
    try:
        s = serie(432, ultimos=1)
        saida["selic"], saida["data_selic"] = s.iloc[-1] / 100, s.index[-1].date()
    except Exception:  # noqa: BLE001
        saida["estimado"] = True
    try:
        s = serie(13522, ultimos=1)
        saida["ipca_12m"], saida["data_ipca"] = s.iloc[-1] / 100, s.index[-1].date()
    except Exception:  # noqa: BLE001
        saida["estimado"] = True
    # CDI ≈ Selic − 0,10 p.p.; aplicação de mais de 2 anos paga 15% de IR sobre o rendimento
    saida["cdi"] = max(0.0, saida["selic"] - 0.001)
    saida["cdi_liquido"] = saida["cdi"] * 0.85
    return saida


FOCUS = "https://olinda.bcb.gov.br/olinda/servico/Expectativas/versao/v1/odata/ExpectativasMercadoAnuais"


def expectativas() -> dict:
    """Boletim Focus (mediana das projeções do mercado): Selic e IPCA no fim deste ano e do próximo.

    É o que o mercado ESPERA — o jeito honesto de "estar um passo à frente": saber o que vem antes de acontecer."""
    hoje = date.today()
    arq = CACHE / f"focus_{hoje:%Y%m%d}.json"
    try:
        if arq.exists():
            dados = json.loads(arq.read_text())
        else:
            params = {"$top": "200", "$orderby": "Data desc", "$format": "json",
                      "$filter": "(Indicador eq 'Selic' or Indicador eq 'IPCA') and baseCalculo eq 0",
                      "$select": "Indicador,Data,DataReferencia,Mediana"}
            r = requests.get(FOCUS, params=params, timeout=30)
            r.raise_for_status()
            dados = r.json().get("value", [])
            CACHE.mkdir(parents=True, exist_ok=True)
            for velho in CACHE.glob("focus_*.json"):
                velho.unlink(missing_ok=True)
            arq.write_text(json.dumps(dados))
    except Exception:  # noqa: BLE001
        return {}
    df = pd.DataFrame(dados)
    if df.empty:
        return {}
    ultima = df["Data"].max()
    df = df[df["Data"] == ultima]
    saida = {"data_focus": ultima}
    for ind in ("Selic", "IPCA"):
        for ano in (hoje.year, hoje.year + 1):
            v = df[(df["Indicador"] == ind) & (df["DataReferencia"].astype(str) == str(ano))]["Mediana"]
            if len(v):
                saida[f"{ind.lower()}_{ano}"] = float(v.iloc[0]) / 100
    return saida


def leitura_juros(selic_hoje: float, exp: dict) -> str | None:
    """Uma frase sobre para onde o mercado espera que os juros andem e o que isso costuma significar."""
    prox = exp.get(f"selic_{date.today().year + 1}")
    if prox is None:
        return None
    dif = prox - selic_hoje
    p = lambda x: f"{x * 100:.2f}%".replace(".", ",")  # noqa: E731
    if dif <= -0.01:
        return (f"O mercado (Focus) espera a Selic caindo de {p(selic_hoje)} para {p(prox)} até o fim de {date.today().year + 1}. "
                "Quando os juros caem, a renda fixa rende menos e boas pagadoras de dividendos costumam se valorizar — "
                "comprar antes da queda é estar um passo à frente.")
    if dif >= 0.01:
        return (f"O mercado (Focus) espera a Selic subindo de {p(selic_hoje)} para {p(prox)}. Juros em alta pressionam as ações: "
                "priorize empresas pouco endividadas e preço bem abaixo do teto.")
    return f"O mercado (Focus) espera a Selic estável perto de {p(prox)} até o fim de {date.today().year + 1}."


def cdi_mensal(inicio: date) -> tuple[pd.Series, bool]:
    """(CDI de cada mês em fração, é_real). Sem internet devolve uma taxa constante de 10% a.a."""
    try:
        s = serie(4391, inicio=inicio) / 100
        s.index = s.index.to_period("M")
        return s, True
    except Exception:  # noqa: BLE001
        meses = pd.period_range(inicio, date.today(), freq="M")
        return pd.Series((1.10) ** (1 / 12) - 1, index=meses), False
