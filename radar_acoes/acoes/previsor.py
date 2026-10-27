"""Previsor de curto prazo: chance de cada ação subir ou cair no próximo mês (21 pregões), com placar de acertos.

Método ("situações parecidas"): para cada ação, olha o próprio histórico e procura os dias em que ela estava
numa situação parecida com a de hoje (tendência de 6 meses, distância da média de 200 dias e movimento do
último mês). Conta quantas vezes, nesses dias, o preço estava mais alto 1 mês depois. A estimativa é puxada
para a média geral quando há poucos casos parecidos.

Honestidade: o curto prazo da bolsa é quase aleatório. Por isso o previsor
1) é testado no passado sem "colar" (só usa dados anteriores a cada data) e mostra a taxa de acerto;
2) registra todas as previsões diárias e confere depois de 1 mês, para você ver o placar real.
Use como termômetro de timing, nunca como certeza.
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import DADOS, salvar_csv

HORIZONTE = 21          # pregões (~1 mês)
K_VIZINHOS = 60
ENCOLHIMENTO = 25       # quanto puxar para a média geral (em "casos equivalentes")
LIMIAR_ALTA, LIMIAR_QUEDA = 0.58, 0.42
REGISTRO = DADOS / "previsoes_registro.csv"


def _features(p: pd.Series) -> pd.DataFrame:
    return pd.DataFrame({
        "m6": p / p.shift(126) - 1,
        "d200": p / p.rolling(200).mean() - 1,
        "m1": p / p.shift(21) - 1,
    })


def _prever_em(f: pd.DataFrame, fut: pd.Series, i: int) -> dict | None:
    """Previsão usando só as linhas cujo resultado já era conhecido no dia i (sem olhar o futuro)."""
    x0 = f.iloc[i]
    if x0.isna().any():
        return None
    hist = f.iloc[: max(0, i - HORIZONTE + 1)]
    y = fut.iloc[: len(hist)]
    ok = hist.notna().all(axis=1) & y.notna()
    hist, y = hist[ok], y[ok]
    if len(hist) < 250:
        return None
    escala = hist.std().replace(0, 1)
    dist = (((hist - x0) / escala) ** 2).sum(axis=1)
    k = min(K_VIZINHOS, len(hist))
    viz = y.loc[dist.nsmallest(k).index]
    base = float((y > 0).mean())
    p = (float((viz > 0).mean()) * k + base * ENCOLHIMENTO) / (k + ENCOLHIMENTO)
    return {"prob_alta": p, "ret_mediano": float(viz.median()), "ret_p10": float(viz.quantile(0.10)),
            "ret_p90": float(viz.quantile(0.90)), "casos": int(k), "base": base}


def direcao(p: float) -> str:
    return "Alta" if p >= LIMIAR_ALTA else "Queda" if p <= LIMIAR_QUEDA else "Indefinida"


def prever(precos: pd.Series) -> dict | None:
    p = precos.dropna()
    p = p[p.index > p.index.max() - pd.DateOffset(years=8)]
    if len(p) < 500:
        return None
    f = _features(p)
    fut = p.shift(-HORIZONTE) / p - 1
    r = _prever_em(f, fut, len(p) - 1)
    if r:
        r["direcao"] = direcao(r["prob_alta"])
    return r


def prever_todas(precos: dict[str, pd.Series]) -> pd.DataFrame:
    linhas = []
    for t, s in precos.items():
        try:
            r = prever(s)
        except Exception:  # noqa: BLE001
            r = None
        if r:
            linhas.append({"ticker": t, **r})
    return pd.DataFrame(linhas)


def validar_historico(precos: dict[str, pd.Series], anos: int = 3, passo: int = 21) -> dict:
    """Teste sem colar: a cada mês dos últimos `anos`, prevê com os dados até ali e confere 1 mês depois."""
    casos = []
    for t, s in precos.items():
        p = s.dropna()
        p = p[p.index > p.index.max() - pd.DateOffset(years=8)]
        if len(p) < 800:
            continue
        f = _features(p)
        fut = p.shift(-HORIZONTE) / p - 1
        inicio = p.index.searchsorted(p.index.max() - pd.DateOffset(years=anos))
        for i in range(max(inicio, 300), len(p) - HORIZONTE, passo):
            r = _prever_em(f, fut, i)
            if r is None or fut.iloc[i] != fut.iloc[i]:
                continue
            casos.append({"ticker": t, "data": p.index[i], "prob_alta": r["prob_alta"], "real": float(fut.iloc[i])})
    df = pd.DataFrame(casos)
    return {"casos": df, **resumo_acertos(df)}


def resumo_acertos(df: pd.DataFrame) -> dict:
    """Taxa de acerto das previsões com direção definida, comparada com 'chutar sempre alta'."""
    if df is None or df.empty:
        return {"n": 0, "n_direcionais": 0, "acerto": float("nan"), "acerto_alta": float("nan"),
                "acerto_queda": float("nan"), "chute_alta": float("nan"), "brier": float("nan"), "brier_chute": float("nan")}
    d = df.copy()
    d["subiu"] = d["real"] > 0
    d["dir"] = d["prob_alta"].map(direcao)
    dirc = d[d["dir"] != "Indefinida"]
    acerto = ((dirc["dir"] == "Alta") == dirc["subiu"]).mean() if len(dirc) else float("nan")
    a = dirc[dirc["dir"] == "Alta"]
    q = dirc[dirc["dir"] == "Queda"]
    taxa_sobe = d["subiu"].mean()
    return {
        "n": int(len(d)), "n_direcionais": int(len(dirc)), "acerto": float(acerto),
        "acerto_alta": float(a["subiu"].mean()) if len(a) else float("nan"),
        "acerto_queda": float((~q["subiu"]).mean()) if len(q) else float("nan"),
        "chute_alta": float(taxa_sobe),  # acerto de quem sempre diz "vai subir"
        "brier": float(((d["prob_alta"] - d["subiu"]) ** 2).mean()),
        "brier_chute": float(((taxa_sobe - d["subiu"]) ** 2).mean()),
    }


# ------------------------------------------------------------------ placar real (previsões registradas)
def registrar(prev: pd.DataFrame, precos_hoje: dict[str, float], hoje: date | None = None) -> None:
    if prev is None or prev.empty:
        return
    hoje = hoje or date.today()
    novo = prev[["ticker", "prob_alta", "direcao"]].copy()
    novo["data"] = hoje.isoformat()
    novo["preco"] = novo["ticker"].map(precos_hoje)
    try:
        antigo = pd.read_csv(REGISTRO)
        antigo = antigo[antigo["data"] != hoje.isoformat()]
        novo = pd.concat([antigo, novo], ignore_index=True)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        pass
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    salvar_csv(novo, REGISTRO)


def placar_real(precos: dict[str, pd.Series]) -> dict:
    """Confere as previsões registradas que já completaram 1 mês."""
    try:
        reg = pd.read_csv(REGISTRO)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return {**resumo_acertos(pd.DataFrame()), "pendentes": 0}
    linhas, pendentes = [], 0
    for _, r in reg.iterrows():
        s = precos.get(r["ticker"])
        if s is None or r["preco"] != r["preco"]:
            continue
        depois = s[s.index > pd.Timestamp(r["data"])]
        if len(depois) < HORIZONTE:
            pendentes += 1
            continue
        linhas.append({"prob_alta": r["prob_alta"], "real": float(depois.iloc[HORIZONTE - 1]) / r["preco"] - 1})
    return {**resumo_acertos(pd.DataFrame(linhas)), "pendentes": pendentes}


def calibrar(prev: pd.DataFrame, validacao: dict) -> tuple[pd.DataFrame, float]:
    """Só deixa a previsão valer na medida em que ela provou vantagem no teste histórico.

    fator 0 = não bateu o chute (todas as previsões viram 'Indefinida'); 1 = vantagem de 5+ pontos sobre o chute."""
    if prev is None or prev.empty:
        return prev, 0.0
    ac, chute = validacao.get("acerto"), validacao.get("chute_alta")
    if ac != ac or chute != chute or validacao.get("n_direcionais", 0) < 100:
        fator = 0.0
    else:
        fator = float(np.clip((ac - max(chute, 0.5)) / 0.05, 0.0, 1.0))
    p = prev.copy()
    p["prob_bruta"] = p["prob_alta"]
    p["prob_alta"] = p["base"] + (p["prob_alta"] - p["base"]) * fator
    p["direcao"] = p["prob_alta"].map(direcao)
    return p, fator
