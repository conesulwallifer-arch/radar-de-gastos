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


def cdi_mensal(inicio: date) -> tuple[pd.Series, bool]:
    """(CDI de cada mês em fração, é_real). Sem internet devolve uma taxa constante de 10% a.a."""
    try:
        s = serie(4391, inicio=inicio) / 100
        s.index = s.index.to_period("M")
        return s, True
    except Exception:  # noqa: BLE001
        meses = pd.period_range(inicio, date.today(), freq="M")
        return pd.Series((1.10) ** (1 / 12) - 1, index=meses), False
