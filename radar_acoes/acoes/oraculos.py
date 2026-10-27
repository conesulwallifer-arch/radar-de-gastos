"""Equipe de previsibilidade: três especialistas em prever, cada um testado no passado antes de ganhar voz.

- 💵 Otto — Previsor de Proventos: quanto cada ação deve pagar nos próximos 12 meses (com faixa) e a chance de
  CORTAR os proventos. É a previsão mais importante para um projeto de dividendos — e a mais previsível:
  empresas boas pagadoras mudam pouco de um ano para o outro.
- 🎯 Bento — Estrategista de Entrada: a que preço pôr a ordem de compra. Mede, no histórico da própria ação,
  até onde o preço costuma descer em 1 mês, e diz o preço com 80% e 50% de chance de ser atingido.
- 🧮 Sofia — Cientista de Dados: um modelo que junta vários sinais (momento, tendência, oscilação, dividendos,
  queda do topo) e estima a chance de cada ação render MAIS que a mediana das outras nos próximos 3 meses.

Regra de ouro (honestidade): cada previsão é validada "sem colar" — só com dados que existiam em cada data do
passado — e o placar fica visível. Quem não bate o chute no teste não vota (fica neutro) até provar valor.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TOLERANCIA_PROVENTOS = 0.25    # previsão de proventos "acertou" se o real ficou a até ±25% do previsto
LIMIAR_CORTE = 0.75            # "corte": pagou menos de 75% da média dos 3 anos anteriores
PRIOR_CORTE = 0.15             # taxa de corte típica (puxa para cá quando a ação tem pouco histórico)
JANELA_ENTRADA = 20            # pregões (~1 mês) para a ordem de compra ser executada
HORIZONTE_SOFIA = 63           # pregões (~3 meses)
EMBARGO_DIAS = 100             # dias corridos entre o fim do treino e a data testada (o futuro do treino não vaza)


def _ok(x) -> bool:
    return x is not None and x == x


# ===================================================================== 💵 OTTO — proventos
def _por_ano(prov: pd.Series, precos: pd.Series, hoje: pd.Timestamp) -> pd.Series:
    """Proventos por ano civil COMPLETO, com zero nos anos em que a ação já existia e não pagou."""
    if precos is None or precos.empty:
        return pd.Series(dtype=float)
    primeiro = int(precos.index.min().year) + 1  # primeiro ano inteiro com cotação
    anos = range(primeiro, hoje.year)
    soma = prov.groupby(prov.index.year).sum() if prov is not None and len(prov) else pd.Series(dtype=float)
    return soma.reindex(anos, fill_value=0.0).astype(float)


def _prever_ano(anual: pd.Series, ano: int) -> float | None:
    """O MESMO método da previsão ao vivo (previsao.proventos_12m): média de 3 anos × crescimento de 5 anos (±10%)."""
    ant = anual[(anual.index >= ano - 3) & (anual.index < ano)]
    if len(ant) < 3:
        return None
    base = float(ant.mean())
    u5 = anual[(anual.index >= ano - 5) & (anual.index < ano)]
    g = 0.0
    if len(u5) >= 3 and u5.iloc[0] > 0 and u5.iloc[-1] > 0:
        g = float(np.clip((u5.iloc[-1] / u5.iloc[0]) ** (1 / (len(u5) - 1)) - 1, -0.10, 0.10))
    return base * (1 + g)


def otto_historico(prov: pd.Series, precos: pd.Series, hoje: pd.Timestamp, anos_teste: int = 6) -> pd.DataFrame:
    """Para cada um dos últimos anos: o que o método teria previsto (só com dados até o ano anterior) × o que pagou."""
    anual = _por_ano(prov, precos, hoje)
    linhas = []
    for ano in [a for a in anual.index if a >= hoje.year - anos_teste]:
        prev = _prever_ano(anual, ano)
        if prev is None:
            continue
        media3 = float(anual[(anual.index >= ano - 3) & (anual.index < ano)].mean())
        real = float(anual.loc[ano])
        # chance de corte que o Otto daria naquele ano (frequência de cortes até ali, puxada para a taxa típica)
        cortes_antes = [float(anual.loc[a]) < LIMIAR_CORTE * float(anual[(anual.index >= a - 3) & (anual.index < a)].mean())
                        for a in anual.index if a < ano and len(anual[(anual.index >= a - 3) & (anual.index < a)]) == 3
                        and anual[(anual.index >= a - 3) & (anual.index < a)].mean() > 0]
        p_corte = (sum(cortes_antes) + PRIOR_CORTE * 4) / (len(cortes_antes) + 4)
        linhas.append({"ano": ano, "previsto": prev, "real": real, "razao": real / prev if prev > 0 else np.nan,
                       "corte": bool(media3 > 0 and real < LIMIAR_CORTE * media3), "p_corte": p_corte})
    return pd.DataFrame(linhas)


def otto(r: dict, prov: pd.Series, precos: pd.Series, hoje: pd.Timestamp, erros_gerais: np.ndarray | None = None) -> dict:
    """Previsão de proventos dos próximos 12 meses com faixa, chance de corte e o placar da própria ação."""
    h = otto_historico(prov, precos, hoje)
    prev = r.get("proventos_previstos_12m")
    prev = float(prev) if _ok(prev) else np.nan
    pagos = h[h["previsto"] > 0]
    acerto = float((abs(pagos["razao"] - 1) <= TOLERANCIA_PROVENTOS).mean()) if len(pagos) else np.nan
    erro_med = float(abs(pagos["razao"] - 1).median()) if len(pagos) else np.nan
    razoes = pagos["razao"].dropna().to_numpy()
    if len(razoes) < 4 and erros_gerais is not None and len(erros_gerais):
        razoes = np.concatenate([razoes, erros_gerais])
    p10, p90 = (np.quantile(razoes, [0.10, 0.90]) if len(razoes) >= 3 else (np.nan, np.nan))
    # chance de corte: histórico da própria ação (puxado para a taxa típica) × sinais de alerta de hoje
    anual = _por_ano(prov, precos, hoje)
    eventos = []
    for a in anual.index:
        m3 = anual[(anual.index >= a - 3) & (anual.index < a)]
        if len(m3) == 3 and m3.mean() > 0:
            eventos.append(float(anual.loc[a]) < LIMIAR_CORTE * float(m3.mean()))
    p_corte = (sum(eventos) + PRIOR_CORTE * 4) / (len(eventos) + 4)
    motivos = []
    pay, cl, seg = r.get("payout"), r.get("cresc_lucro"), r.get("seguranca_div")
    if _ok(pay) and pay > 1.0:
        p_corte *= 1.6
        motivos.append("paga mais do que lucra")
    if _ok(cl) and cl <= -0.25:
        p_corte *= 1.4
        motivos.append("lucro caindo forte")
    if _ok(seg) and seg <= 40:
        p_corte *= 1.3
        motivos.append("segurança dos dividendos baixa")
    if r.get("payout_fcl") == float("inf"):
        p_corte *= 1.3
        motivos.append("caixa livre negativo")
    if not _ok(prev) or prev <= 0:
        p_corte = max(p_corte, 0.5)
    return {
        "otto_prov_12m": prev,
        "otto_prov_p10": prev * p10 if _ok(prev) and _ok(p10) else np.nan,
        "otto_prov_p90": prev * p90 if _ok(prev) and _ok(p90) else np.nan,
        "otto_acerto": acerto, "otto_erro_mediano": erro_med, "otto_anos_testados": int(len(pagos)),
        "otto_prob_corte": float(min(0.95, p_corte)), "otto_motivos_corte": ", ".join(motivos),
    }


def otto_validacao(historicos: list[pd.DataFrame]) -> dict:
    """Placar do Otto em todas as ações juntas: acerto de valor e se a 'chance de corte' foi bem calibrada."""
    h = pd.concat([x for x in historicos if x is not None and len(x)], ignore_index=True) if historicos else pd.DataFrame()
    if h.empty:
        return {"n": 0}
    pagos = h[h["previsto"] > 0]
    taxa = float(h["corte"].mean())
    return {
        "n": int(len(pagos)),
        "acerto": float((abs(pagos["razao"] - 1) <= TOLERANCIA_PROVENTOS).mean()) if len(pagos) else np.nan,
        "erro_mediano": float(abs(pagos["razao"] - 1).median()) if len(pagos) else np.nan,
        "taxa_corte": taxa,
        "brier_corte": float(((h["p_corte"] - h["corte"]) ** 2).mean()),
        "brier_chute": float(((taxa - h["corte"]) ** 2).mean()),
        "razoes": pagos["razao"].dropna().clip(0, 3).to_numpy(),
    }


# ===================================================================== 🎯 BENTO — ponto de entrada
def _minimos_futuros(p: pd.Series, janela: int = JANELA_ENTRADA) -> pd.Series:
    """Para cada dia: menor preço dos próximos `janela` pregões ÷ preço do dia (≤ 1)."""
    v = p.to_numpy(dtype=float)
    n = len(v)
    out = np.full(n, np.nan)
    if n > janela:
        from numpy.lib.stride_tricks import sliding_window_view
        mins = sliding_window_view(v[1:], janela).min(axis=1)  # mínimo de i+1 .. i+janela
        out[: len(mins)] = mins / v[: len(mins)]
    return pd.Series(out, index=p.index)


def bento(r: dict, precos: pd.Series, anos: int = 5) -> dict:
    p = precos.dropna()
    p = p[p.index > p.index.max() - pd.DateOffset(years=anos)]
    m = _minimos_futuros(p).dropna()
    preco = r.get("preco")
    if len(m) < 250 or not _ok(preco):
        return {}
    q80, q50 = float(np.quantile(m, 0.80)), float(np.quantile(m, 0.50))
    teto = r.get("preco_teto_bazin")
    if _ok(teto) and teto > 0:
        prob_teto = 1.0 if preco <= teto else float((m <= teto / preco).mean())
    else:
        prob_teto = np.nan
    return {"bento_preco_80": preco * q80, "bento_preco_50": preco * q50, "bento_prob_tocar_teto": prob_teto,
            "bento_desconto_80": q80 - 1, "bento_desconto_50": q50 - 1}


def bento_validacao(precos: dict[str, pd.Series], anos: int = 5) -> dict:
    """Calibração sem colar: aprende os níveis com os dados até 1 ano atrás e confere no último ano.
    Se o Bento promete '80% de chance', o certo é ter batido perto de 80% das vezes."""
    bate80, bate50 = [], []
    for s in precos.values():
        p = s.dropna()
        p = p[p.index > p.index.max() - pd.DateOffset(years=anos)]
        m = _minimos_futuros(p).dropna()
        corte = p.index.max() - pd.DateOffset(years=1)
        treino = m[m.index <= corte - pd.Timedelta(days=35)]
        teste = m[m.index > corte]
        if len(treino) < 250 or len(teste) < 60:
            continue
        q80, q50 = np.quantile(treino, 0.80), np.quantile(treino, 0.50)
        bate80.append((teste <= q80).to_numpy())
        bate50.append((teste <= q50).to_numpy())
    if not bate80:
        return {"n": 0}
    b80, b50 = np.concatenate(bate80), np.concatenate(bate50)
    return {"n": int(len(b80)), "real_80": float(b80.mean()), "real_50": float(b50.mean())}


# ===================================================================== 🧮 SOFIA — modelo conjunto
NOMES_SINAIS = {"mom12": "momento de 12 meses", "r1": "movimento do último mês", "d200": "distância da média de 200 dias",
                "vol": "oscilação", "dy": "dividendos dos últimos 12 meses", "dd": "distância do topo de 1 ano"}


def _sinais(p: pd.Series, prov: pd.Series | None) -> pd.DataFrame:
    """Sinais de cada ação no último pregão de cada mês (e o retorno total dos 3 meses seguintes, quando já existe)."""
    p = p.dropna()
    if len(p) < 300:
        return pd.DataFrame()
    logret = np.log(p).diff()
    df = pd.DataFrame({
        "mom12": p.shift(21) / p.shift(252) - 1,
        "r1": p / p.shift(21) - 1,
        "d200": p / p.rolling(200).mean() - 1,
        "vol": logret.rolling(126).std() * np.sqrt(252),
        "dd": p / p.rolling(252).max() - 1,
    })
    prov = prov if prov is not None else pd.Series(dtype=float)
    acum = prov.sort_index().cumsum().reindex(p.index, method="ffill").fillna(0.0) if len(prov) else pd.Series(0.0, index=p.index)
    ano_antes = acum.reindex(p.index - pd.DateOffset(years=1), method="ffill").fillna(0.0).to_numpy()
    df["dy"] = (acum.to_numpy() - ano_antes) / p.to_numpy()
    # retorno total dos próximos 3 meses (preço + proventos pagos no período)
    fut_p = p.shift(-HORIZONTE_SOFIA)
    fut_div = acum.shift(-HORIZONTE_SOFIA) - acum
    df["ret_fut"] = (fut_p + fut_div) / p - 1
    df["data"] = p.index
    fim_mes = p.groupby(p.index.to_period("M")).tail(1).index
    df = df.loc[fim_mes]
    df["mes"] = df.index.to_period("M")
    return df


def _ajustar(X: np.ndarray, y: np.ndarray, l2: float = 0.05, iters: int = 400, passo: float = 1.0) -> np.ndarray:
    """Regressão logística com regularização L2 (descida de gradiente), sem bibliotecas extras.
    A regularização forte é de propósito: mercado tem muito ruído, e um modelo "confiante demais" erra feio."""
    Xb = np.c_[np.ones(len(X)), X]
    w = np.zeros(Xb.shape[1])
    for _ in range(iters):
        pr = 1 / (1 + np.exp(-np.clip(Xb @ w, -30, 30)))
        grad = Xb.T @ (pr - y) / len(y) + l2 * np.r_[0.0, w[1:]]
        w -= passo * grad
    return w


def _prob(w: np.ndarray, X: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-np.clip(np.c_[np.ones(len(X)), X] @ w, -30, 30)))


COLS = ["mom12", "r1", "d200", "vol", "dy", "dd"]


def _painel(precos: dict[str, pd.Series], proventos: dict[str, pd.Series]) -> pd.DataFrame:
    partes = []
    for t, p in precos.items():
        s = _sinais(p, proventos.get(t))
        if len(s):
            partes.append(s.assign(ticker=t))
    if not partes:
        return pd.DataFrame()
    d = pd.concat(partes, ignore_index=True).dropna(subset=COLS)
    d[COLS] = d[COLS].clip(d[COLS].quantile(0.01), d[COLS].quantile(0.99), axis=1)
    # alvo: render MAIS que a mediana das outras ações no mesmo mês (o que importa para escolher o que comprar)
    med = d.groupby("mes")["ret_fut"].transform("median")
    d["alvo"] = np.where(d["ret_fut"].notna(), (d["ret_fut"] > med).astype(float), np.nan)
    d["excesso"] = d["ret_fut"] - med
    return d


def _padronizar(treino: pd.DataFrame, *outros: pd.DataFrame):
    mu, sd = treino[COLS].mean(), treino[COLS].std().replace(0, 1)
    return [((x[COLS] - mu) / sd).to_numpy() for x in (treino, *outros)]


def sofia(precos: dict[str, pd.Series], proventos: dict[str, pd.Series], anos_teste: int = 3) -> dict:
    """Treina e testa sem colar (janela que anda mês a mês). Retorna previsões de hoje + placar + o que o modelo aprendeu."""
    d = _painel(precos, proventos)
    vazio = {"previsoes": pd.DataFrame(), "validacao": {"n": 0}, "fator": 0.0, "pesos": {}}
    if d.empty:
        return vazio
    rotulado = d[d["alvo"].notna()]
    meses = sorted(rotulado["mes"].unique())
    ultimo = rotulado["data"].max()
    teste_meses = [m for m in meses if m.to_timestamp() > ultimo - pd.DateOffset(years=anos_teste)]
    casos = []
    for m in teste_meses:
        alvo_m = rotulado[rotulado["mes"] == m]
        treino = rotulado[rotulado["data"] < alvo_m["data"].min() - pd.Timedelta(days=EMBARGO_DIAS)]
        if len(treino) < 300 or treino["mes"].nunique() < 24 or len(alvo_m) < 5:
            continue
        Xtr, Xte = _padronizar(treino, alvo_m)
        w = _ajustar(Xtr, treino["alvo"].to_numpy())
        pr = _prob(w, Xte)
        casos.append(alvo_m[["ticker", "mes", "alvo", "excesso"]].assign(prob=pr))
    val = {"n": 0}
    if casos:
        c = pd.concat(casos, ignore_index=True)
        acerto = float(((c["prob"] >= 0.5) == (c["alvo"] == 1)).mean())
        # carteira das 20% com maior probabilidade × 20% com menor, mês a mês
        c["quintil"] = c.groupby("mes")["prob"].rank(pct=True)
        topo = c[c["quintil"] > 0.8].groupby("mes")["excesso"].mean()
        fundo = c[c["quintil"] <= 0.2].groupby("mes")["excesso"].mean()
        dif = (topo - fundo).dropna()
        spread = float(dif.mean()) if len(dif) else np.nan
        # teste de significância: os retornos de 3 meses se sobrepõem mês a mês (3 meses "contam" como ~1),
        # então o t é dividido por √3. Só t ≥ 2 conta como padrão de verdade, não sorte.
        t_stat = float(dif.mean() / (dif.std(ddof=1) / np.sqrt(len(dif))) / np.sqrt(3)) if len(dif) > 6 and dif.std() > 0 else 0.0
        val = {"n": int(len(c)), "meses": int(c["mes"].nunique()), "acerto": acerto,
               "ganho_topo_3m": float(topo.mean()) if len(topo) else np.nan,
               "spread_3m": spread, "t_stat": t_stat,
               "meses_topo_ganhou": float((topo > 0).mean()) if len(topo) else np.nan}
    # só ganha voz se o padrão for estatisticamente real (t ≥ 2) e o acerto bater o chute (50%)
    fator = 0.0
    if val.get("n", 0) >= 300 and val.get("t_stat", 0) >= 2.0 and val["acerto"] > 0.5:
        fator = float(np.clip((val["acerto"] - 0.5) / 0.04, 0, 1) * np.clip((val["t_stat"] - 1.0) / 2.0, 0, 1))
    # modelo final: treina com tudo que já tem resultado e prevê o último mês de cada ação
    Xtr, = _padronizar(rotulado)
    w = _ajustar(Xtr, rotulado["alvo"].to_numpy())
    hoje = d.sort_values("data").groupby("ticker").tail(1)
    hoje = hoje[hoje["data"] >= d["data"].max() - pd.Timedelta(days=10)]
    if hoje.empty:
        return {**vazio, "validacao": val, "fator": fator}
    _, Xh = _padronizar(rotulado, hoje)
    bruta = _prob(w, Xh)
    prev = pd.DataFrame({"ticker": hoje["ticker"].to_numpy(), "sofia_prob_bruta": bruta,
                         "sofia_prob": 0.5 + (bruta - 0.5) * fator})
    pesos = {NOMES_SINAIS[c]: float(v) for c, v in zip(COLS, w[1:])}
    return {"previsoes": prev, "validacao": val, "fator": fator, "pesos": pesos}


# ===================================================================== a equipe toda
def rodar(rk: pd.DataFrame, precos: dict[str, pd.Series], proventos: dict[str, pd.Series], hoje=None) -> dict:
    """Roda Otto, Bento e Sofia. Devolve {'tabela': DataFrame por ticker, 'placar': {...}}."""
    hoje = pd.Timestamp(hoje or pd.Timestamp.today().normalize())
    historicos = {t: otto_historico(proventos.get(t, pd.Series(dtype=float)), precos[t], hoje) for t in rk["ticker"] if t in precos}
    v_otto = otto_validacao(list(historicos.values()))
    gerais = v_otto.get("razoes")
    linhas = []
    for _, r in rk.iterrows():
        t = r["ticker"]
        if t not in precos:
            continue
        d = r.to_dict()
        try:
            o = otto(d, proventos.get(t, pd.Series(dtype=float)), precos[t], hoje, gerais)
        except Exception:  # noqa: BLE001
            o = {}
        try:
            b = bento(d, precos[t])
        except Exception:  # noqa: BLE001
            b = {}
        linhas.append({"ticker": t, **o, **b})
    tab = pd.DataFrame(linhas)
    s = sofia({t: precos[t] for t in rk["ticker"] if t in precos}, proventos)
    if len(s["previsoes"]):
        tab = tab.merge(s["previsoes"], on="ticker", how="left")
    v_otto.pop("razoes", None)
    return {"tabela": tab, "placar": {"otto": v_otto, "bento": bento_validacao({t: precos[t] for t in rk["ticker"] if t in precos}),
                                      "sofia": {**s["validacao"], "fator": s["fator"], "pesos": s["pesos"]}}}
