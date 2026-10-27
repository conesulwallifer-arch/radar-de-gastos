"""Cérebro dos agentes: memória de cada voto e aprendizado pelo placar real.

Todo dia, cada voto de cada agente é guardado (data, ação, voto, preço). Depois de 63 pregões (~3 meses),
o voto é conferido contra o que aconteceu: retorno total da ação (preço + proventos) MENOS o retorno mediano
de todas as ações no mesmo período — assim um mês bom para a bolsa inteira não conta como mérito do agente.

Acertou = votou a favor e a ação foi melhor que a média, ou votou contra e foi pior.
O peso de cada agente no consenso passa a ser ajustado pelo seu acerto real (só depois de amostra suficiente).
"""
from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd

from . import DADOS, hoje_brt, salvar_csv

ARQ = DADOS / "memoria_votos.csv"
JANELA = 63           # pregões até conferir o voto
AMOSTRA_MINIMA = 150  # votos conferidos antes de mexer no peso


def registrar(opinioes: dict, precos_hoje: dict[str, float], hoje: date | None = None) -> None:
    hoje = (hoje or hoje_brt()).isoformat()
    linhas = [{"data": hoje, "agente": a, "ticker": t, "voto": o["voto"], "preco": precos_hoje.get(t)}
              for t, ops in opinioes.items() for a, o in ops.items()]
    novo = pd.DataFrame(linhas)
    try:
        antigo = pd.read_csv(ARQ)
        novo = pd.concat([antigo[antigo["data"] != hoje], novo], ignore_index=True)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        pass
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    salvar_csv(novo, ARQ)


def _retornos(reg: pd.DataFrame, precos: dict, proventos: dict) -> pd.DataFrame:
    """Retorno total em JANELA pregões para cada (data, ticker) já maduro."""
    saida = []
    for (d, t), _ in reg.groupby(["data", "ticker"]):
        s = precos.get(t)
        if s is None:
            continue
        ini = pd.Timestamp(d)
        depois = s[s.index > ini]
        antes = s[s.index <= ini]
        if len(depois) < JANELA or antes.empty:
            continue
        p0, p1 = float(antes.iloc[-1]), float(depois.iloc[JANELA - 1])
        fim = depois.index[JANELA - 1]
        pv = proventos.get(t, pd.Series(dtype=float))
        prov = float(pv[(pv.index > ini) & (pv.index <= fim)].sum()) if len(pv) else 0.0
        saida.append({"data": d, "ticker": t, "retorno": (p1 + prov) / p0 - 1})
    return pd.DataFrame(saida)


def avaliar(precos: dict, proventos: dict) -> dict:
    """{'por_agente': DataFrame, 'votos_guardados': int, 'desde': str|None, 'pendentes': int}."""
    try:
        reg = pd.read_csv(ARQ)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return {"por_agente": pd.DataFrame(), "votos_guardados": 0, "desde": None, "pendentes": 0}
    ret = _retornos(reg, precos, proventos)
    base = {"votos_guardados": int(len(reg)), "desde": str(reg["data"].min()), "pendentes": 0}
    if ret.empty:
        base["pendentes"] = int(len(reg))
        return {**base, "por_agente": pd.DataFrame()}
    ret["excesso"] = ret["retorno"] - ret.groupby("data")["retorno"].transform("median")
    m = reg.merge(ret, on=["data", "ticker"], how="inner")
    base["pendentes"] = int(len(reg) - len(m))
    m = m[m["voto"] != 0]
    linhas = []
    for a, g in m.groupby("agente"):
        acertou = np.sign(g["voto"]) == np.sign(g["excesso"])
        fav, contra = g[g["voto"] > 0], g[g["voto"] < 0]
        linhas.append({"agente": a, "conferidos": int(len(g)), "acerto": float(acertou.mean()),
                       "ganho_a_favor": float(fav["excesso"].mean()) if len(fav) else np.nan,
                       "ganho_contra": float(contra["excesso"].mean()) if len(contra) else np.nan})
    return {**base, "por_agente": pd.DataFrame(linhas)}


def fatores(aval: dict) -> dict[str, float]:
    """Multiplicador do peso de cada agente: 0,5 (erra muito) a 1,5 (acerta muito); 1 sem amostra suficiente."""
    df = aval.get("por_agente")
    if df is None or df.empty:
        return {}
    out = {}
    for _, r in df.iterrows():
        if r["conferidos"] >= AMOSTRA_MINIMA:
            out[r["agente"]] = float(np.clip(1 + (r["acerto"] - 0.5) * 4, 0.5, 1.5))
    return out
