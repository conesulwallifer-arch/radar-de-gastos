"""Teste no passado: e se você tivesse seguido o sistema nos últimos anos?

Todo mês, usando SÓ o que se sabia naquela data (preços e proventos até ali), escolhe as ações que pagaram
proventos com regularidade e estão mais baratas em relação ao preço-teto, aporta o valor do mês nelas e
reinveste os proventos. Compara com o mesmo aporte no CDI e no Ibovespa (BOVA11).

Limites honestos: (1) só testa a parte de proventos e preço (os indicadores de balanço do Yahoo são só os de
hoje, usá-los no passado seria "colar na prova"); (2) usa a lista de empresas de hoje, que sobreviveram —
isso deixa o resultado um pouco melhor do que seria na vida real; (3) não desconta corretagem nem imposto.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import universo


def _escolher_no_mes(base: dict, dia: pd.Timestamp, n: int, max_setor: int) -> list[str]:
    cand = []
    for t, d in base.items():
        p = d["precos"]
        p = p[p.index <= dia]
        if len(p) < 500:  # precisa de ~2 anos de histórico naquela data
            continue
        preco = float(p.iloc[-1])
        prov = d["proventos"]
        prov = prov[prov.index < dia]
        anual = prov.groupby(prov.index.year).sum() if len(prov) else pd.Series(dtype=float)
        anos = [dia.year - k for k in range(1, 6)]
        valores = [float(anual.get(a, 0.0)) for a in anos]
        pagou = sum(v > 0 for v in valores)
        media = float(np.mean(valores))
        dy = media / preco if preco > 0 else 0.0
        if pagou < 4 or dy < 0.05:
            continue
        ret = np.log(p[p.index > dia - pd.DateOffset(years=2)]).diff().dropna()
        vol = float(ret.std() * np.sqrt(252)) if len(ret) > 20 else 0.4
        margem = (media / 0.06) / preco - 1
        pontos = min(dy, 0.12) * (pagou / 5) * (1 - min(vol, 0.6) / 2) * (1 + max(-0.3, min(margem, 0.5)))
        cand.append((pontos, t))
    cand.sort(reverse=True)
    escolhidas, por_setor = [], {}
    for _, t in cand:
        s = universo.setor(t)
        if por_setor.get(s, 0) >= max_setor:
            continue
        escolhidas.append(t)
        por_setor[s] = por_setor.get(s, 0) + 1
        if len(escolhidas) >= n:
            break
    return escolhidas


def _tir_anual(fluxos: list[float]) -> float:
    """Taxa interna de retorno (mensal → anual) por bisseção. fluxos: aportes negativos, valor final positivo."""
    def vpl(r):
        return sum(f / (1 + r) ** i for i, f in enumerate(fluxos))
    lo, hi = -0.99, 1.0
    if vpl(lo) * vpl(hi) > 0:
        return float("nan")
    for _ in range(200):
        mid = (lo + hi) / 2
        if vpl(lo) * vpl(mid) <= 0:
            hi = mid
        else:
            lo = mid
    return (1 + mid) ** 12 - 1


def rodar(base: dict[str, dict], anos: int = 5, aporte: float = 1000.0, n_acoes: int = 6, max_setor: int = 2,
          cdi: pd.Series | None = None, ibov: pd.Series | None = None, hoje: date | None = None) -> dict:
    hoje = pd.Timestamp(hoje or date.today())
    inicio = (hoje - pd.DateOffset(years=anos)).to_period("M").to_timestamp()
    datas = pd.bdate_range(inicio, hoje)
    meses = sorted({d.to_period("M") for d in datas})
    primeiros = [datas[datas.to_period("M") == m][0] for m in meses]

    cotas: dict[str, float] = {}
    caixa = 0.0
    v_cdi = 0.0
    cotas_ibov = 0.0
    linhas, fluxos, compras = [], [], []
    anterior = None
    for k, dia in enumerate(primeiros):
        # proventos recebidos desde o mês anterior (data-ex entre as duas datas)
        if anterior is not None:
            for t, q in cotas.items():
                pr = base[t]["proventos"]
                caixa += q * float(pr[(pr.index > anterior) & (pr.index <= dia)].sum())
            if cdi is not None:
                v_cdi *= 1 + float(cdi.get(anterior.to_period("M"), cdi.iloc[-1] if len(cdi) else 0.008))
        caixa += aporte
        v_cdi += aporte
        if ibov is not None and len(ibov[ibov.index <= dia]):
            cotas_ibov += aporte / float(ibov[ibov.index <= dia].iloc[-1])
        escolha = _escolher_no_mes(base, dia, n_acoes, max_setor)
        if escolha:
            parte = caixa / len(escolha)
            for t in escolha:
                preco = float(base[t]["precos"].asof(dia))
                cotas[t] = cotas.get(t, 0.0) + parte / preco
            compras.append({"mes": dia.date(), "acoes": ", ".join(escolha)})
            caixa = 0.0
        fluxos.append(-aporte)
        valor = caixa + sum(q * float(base[t]["precos"].asof(dia)) for t, q in cotas.items())
        linhas.append({"data": dia, "investido": aporte * (k + 1), "sistema": valor,
                       "cdi": v_cdi if cdi is not None else np.nan,
                       "ibovespa": cotas_ibov * float(ibov.asof(dia)) if ibov is not None and cotas_ibov else np.nan})
        anterior = dia

    df = pd.DataFrame(linhas)
    fim = df.iloc[-1]
    res = {"serie": df, "compras": pd.DataFrame(compras), "meses": len(df), "investido": float(fim["investido"])}
    for col in ("sistema", "cdi", "ibovespa"):
        v = float(fim[col])
        res[col] = v
        res[f"tir_{col}"] = _tir_anual(fluxos[:-1] + [fluxos[-1] + v]) if v == v else float("nan")
    # carteira atual do teste: renda de proventos dos últimos 12 meses
    ult = sum(q * float(base[t]["proventos"][base[t]["proventos"].index > hoje - pd.DateOffset(years=1)].sum())
              for t, q in cotas.items())
    res["proventos_12m"] = ult
    return res
