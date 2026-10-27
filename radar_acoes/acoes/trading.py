"""Mesa de Trading (médio prazo): padrões de mercado testados no histórico, sinais de hoje e as suas operações.

Como funciona (e por que dá para confiar MAIS do que em "dica"):
1. Cinco padrões clássicos, com regras FIXAS (nada ajustado para "encaixar" no passado).
2. Mesmas regras de saída para todos: stop do tamanho da oscilação típica de 1 mês da ação, alvo a 2× o risco (2:1),
   stop vai para o preço de entrada quando o ganho chega a 1× o risco, e saída por tempo em 3 meses.
3. Cada padrão é testado em TODAS as ações, com custos, em dois períodos separados: "descoberta" (mais antigo)
   e "confirmação" (últimos 3 anos). E é comparado com o "chute": entrar em dias aleatórios com as mesmas saídas.
4. Só é ✅ aprovado o padrão que ganhou nos dois períodos, venceu o chute e tem amostra suficiente.
5. Os sinais de cada dia são registrados e conferidos depois: o placar real fica à vista.

Limitação honesta: usamos preços de fechamento (o stop é conferido no fechamento, o que é conservador) e o passado
não garante o futuro. Nenhum padrão acerta sempre — o lucro vem de ganhar mais nas que dão certo do que se perde nas
que dão errado, com disciplina de stop.
"""
from __future__ import annotations

import json
from datetime import date

import numpy as np
import pandas as pd

from . import DADOS, hoje_brt, salvar_csv

STOP_SIGMA = 1.2         # stop = entrada − 1,2 × oscilação típica de 1 mês (desvio diário × √20)
RISCO_MIN, RISCO_MAX = 0.05, 0.18  # distância do stop: entre 5% e 18%
ALVO_R = 2.0             # alvo = entrada + 2 × risco
PRAZO = 63               # pregões (~3 meses): saída por tempo
CUSTO = 0.0025           # corretagem + emolumentos + derrapagem (ida e volta)
ANOS_CONFIRMACAO = 3
MIN_TRADES_CONF = 30
REGISTRO = DADOS / "trading_sinais.csv"
OPERACOES = DADOS / "minhas_operacoes.csv"
ESTADO_ALERTAS = DADOS / "trading_alertas.json"

PADROES = {
    "pullback": ("Correção na tendência de alta",
                 "Ação em tendência de alta (acima da média de 200 dias, com a de 50 acima da de 200) que caiu forte no curto prazo "
                 "(IFR de 14 dias abaixo de 35). Compra a correção esperando a tendência retomar."),
    "rompimento": ("Rompimento de máxima de 3 meses",
                   "Fecha acima da maior cotação dos últimos 3 meses, em tendência de alta. Compra a força: preço que rompe topo "
                   "tende a continuar (efeito momento)."),
    "dividendos": ("Dividendos no topo + virada",
                   "O dividend yield está entre os 20% mais altos dos últimos 5 anos da própria ação (barata pela renda) e o preço "
                   "acabou de voltar para cima da média de 50 dias. Barata E começando a subir."),
    "cruzamento": ("Cruzamento dourado",
                   "A média de 50 dias cruza para cima da média de 200 dias: mudança de tendência de baixa para alta."),
    "virada": ("Queda forte + virada",
               "Caiu 25% ou mais do topo de 1 ano e voltou a fechar acima da média de 50 dias, com a média de 50 parando de cair. "
               "Procura ações baratas que começam a se recuperar."),
}


# ------------------------------------------------------------------ indicadores (só preço de fechamento)
def _ifr(p: pd.Series, n: int = 14) -> pd.Series:
    d = p.diff()
    alta = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    baixa = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return 100 - 100 / (1 + alta / baixa.replace(0, np.nan))


def indicadores(p: pd.Series, prov: pd.Series | None = None) -> pd.DataFrame:
    p = p.dropna()
    df = pd.DataFrame({"p": p})
    df["mm20"], df["mm50"], df["mm200"] = p.rolling(20).mean(), p.rolling(50).mean(), p.rolling(200).mean()
    df["ifr"] = _ifr(p)
    df["osc"] = p.pct_change().rolling(60).std()  # oscilação diária típica dos últimos 3 meses
    df["max63"] = p.rolling(63).max().shift(1)
    df["dd252"] = p / p.rolling(252).max() - 1
    if prov is not None and len(prov):
        acum = prov.sort_index().cumsum().reindex(p.index, method="ffill").fillna(0.0)
        ano = acum.reindex(p.index - pd.DateOffset(years=1), method="ffill").fillna(0.0).to_numpy()
        dy = (acum.to_numpy() - ano) / p.to_numpy()
        df["dy"] = dy
        df["dy_pct"] = pd.Series(dy, index=p.index).rolling(1260, min_periods=750).rank(pct=True)
    else:
        df["dy"], df["dy_pct"] = 0.0, np.nan
    return df


def gatilhos(df: pd.DataFrame) -> pd.DataFrame:
    """Dias em que cada padrão dispara (True/False por coluna)."""
    alta = (df["p"] > df["mm200"]) & (df["mm50"] > df["mm200"])
    cruza50 = (df["p"] > df["mm50"]) & (df["p"].shift(1) <= df["mm50"].shift(1))
    g = pd.DataFrame(index=df.index)
    g["pullback"] = alta & (df["ifr"] < 35) & (df["ifr"].shift(1) >= 35)
    g["rompimento"] = alta & (df["p"] > df["max63"]) & (df["p"].shift(1) <= df["max63"].shift(1))
    g["dividendos"] = (df["dy_pct"] >= 0.8) & (df["dy"] > 0.04) & cruza50
    g["cruzamento"] = (df["mm50"] > df["mm200"]) & (df["mm50"].shift(1) <= df["mm200"].shift(1))
    g["virada"] = (df["dd252"] <= -0.25) & cruza50 & (df["mm50"] >= df["mm50"].shift(5))
    return g.fillna(False)


def niveis(preco: float, osc: float) -> tuple[float, float]:
    """(stop, alvo). O stop fica a ~1 mês de oscilação normal: longe o bastante para o ruído não tirar você da operação."""
    risco = float(np.clip(STOP_SIGMA * osc * np.sqrt(20), RISCO_MIN, RISCO_MAX)) * preco
    return preco - risco, preco + ALVO_R * risco


# ------------------------------------------------------------------ simulação de uma operação
def simular(p: np.ndarray, i: int, osc: float) -> dict | None:
    """Entra no fechamento do dia i e segue as regras de saída. Devolve o resultado ou None se não deu tempo."""
    entrada = p[i]
    stop, alvo = niveis(entrada, osc)
    risco = entrada - stop
    fim = min(len(p) - 1, i + PRAZO)
    if fim <= i:
        return None
    for j in range(i + 1, fim + 1):
        if p[j] >= entrada + risco and stop < entrada:
            stop = entrada  # protegeu: stop no preço de entrada
        if p[j] >= alvo:
            return {"saida": j, "ret": alvo / entrada - 1 - CUSTO, "motivo": "alvo"}
        if p[j] <= stop:
            return {"saida": j, "ret": p[j] / entrada - 1 - CUSTO, "motivo": "stop" if stop < entrada else "empate"}
    if i + PRAZO > len(p) - 1:
        return None  # operação ainda aberta no fim dos dados
    return {"saida": fim, "ret": p[fim] / entrada - 1 - CUSTO, "motivo": "prazo"}


def operacoes_historicas(ticker: str, df: pd.DataFrame, g: pd.DataFrame) -> list[dict]:
    p = df["p"].to_numpy(dtype=float)
    osc = df["osc"].to_numpy(dtype=float)
    saida = []
    for nome in PADROES:
        idx = np.flatnonzero(g[nome].to_numpy())
        livre = 0
        for i in idx:
            if i < livre or i < 260 or not np.isfinite(osc[i]):
                continue
            if i + 1 >= len(p):
                continue
            r = simular(p, i + 1, osc[i])  # entra no fechamento do DIA SEGUINTE: o sinal só é conhecido depois do fechamento
            if r is None:
                continue
            saida.append({"ticker": ticker, "padrao": nome, "data": df.index[i], "dias": r["saida"] - i - 1, **r})
            livre = r["saida"] + 1  # uma operação por vez em cada padrão/ação
    return saida


def _base_aleatoria(ticker: str, df: pd.DataFrame, passo: int = 10) -> list[dict]:
    """O 'chute': entrar a cada 10 pregões, sem padrão nenhum, com as mesmas regras de saída."""
    p = df["p"].to_numpy(dtype=float)
    osc = df["osc"].to_numpy(dtype=float)
    out = []
    for i in range(260, len(p) - 2, passo):
        if np.isfinite(osc[i]):
            r = simular(p, i + 1, osc[i])  # mesma regra de entrada dos padrões (comparação justa)
            if r:
                out.append({"ticker": ticker, "padrao": "chute", "data": df.index[i], "dias": r["saida"] - i - 1, **r})
    return out


def _estatisticas(t: pd.DataFrame) -> dict:
    if t.empty:
        return {"n": 0}
    r = t["ret"]
    ganhos, perdas = r[r > 0], r[r <= 0]
    return {"n": int(len(t)), "acerto": float((r > 0).mean()), "ganho_medio": float(ganhos.mean()) if len(ganhos) else 0.0,
            "perda_media": float(perdas.mean()) if len(perdas) else 0.0, "expectativa": float(r.mean()),
            "fator_lucro": float(ganhos.sum() / -perdas.sum()) if len(perdas) and perdas.sum() < 0 else float("inf"),
            "dias_medio": float(t["dias"].mean()), "t": float(r.mean() / (r.std(ddof=1) / np.sqrt(len(r)))) if len(r) > 2 and r.std() > 0 else 0.0,
            "alvos": float((t["motivo"] == "alvo").mean()), "stops": float((t["motivo"] == "stop").mean())}


def _t_dif(o: pd.DataFrame, b: pd.DataFrame) -> float:
    """Vantagem do padrão sobre o chute, em erros-padrão. Agrupa por MÊS de entrada: operações do mesmo mês andam juntas
    com o mercado e não são independentes (contar cada uma como independente inflava a confiança)."""
    if len(o) < 3 or len(b) < 3:
        return 0.0
    om = o.groupby(pd.to_datetime(o["data"]).dt.to_period("M"))["ret"].mean()
    bm = b.groupby(pd.to_datetime(b["data"]).dt.to_period("M"))["ret"].mean()
    if len(om) < 3 or len(bm) < 3:
        return 0.0
    ep = np.sqrt(om.var(ddof=1) / len(om) + bm.var(ddof=1) / len(bm))
    return float((o["ret"].mean() - b["ret"].mean()) / ep) if ep > 0 else 0.0


T_CONFIRMACAO = 2.33  # ~1% de chance de ser sorte, já corrigido por testar 5 padrões ao mesmo tempo
T_DESCOBERTA = 1.65   # e também precisa ter vencido o chute no período antigo


def backtest(precos: dict[str, pd.Series], proventos: dict[str, pd.Series]) -> dict:
    """Testa todos os padrões em todas as ações. {'padroes': DataFrame com o placar, 'operacoes': DataFrame, 'ind': {...}}."""
    ops, base, ind = [], [], {}
    for t, s in precos.items():
        if s is None or len(s.dropna()) < 400:
            continue
        df = indicadores(s, proventos.get(t))
        g = gatilhos(df)
        ind[t] = (df, g)
        ops += operacoes_historicas(t, df, g)
        base += _base_aleatoria(t, df)
    ops, base = pd.DataFrame(ops), pd.DataFrame(base)
    if ops.empty or base.empty:
        return {"padroes": pd.DataFrame(), "operacoes": ops, "ind": ind, "chute": {}}
    corte = max(ops["data"].max(), base["data"].max()) - pd.DateOffset(years=ANOS_CONFIRMACAO)
    base_conf, base_desc = base[base["data"] > corte], base[base["data"] <= corte]
    chute_conf = _estatisticas(base_conf)
    linhas = []
    for nome, (titulo, _) in PADROES.items():
        o = ops[ops["padrao"] == nome]
        desc, conf = _estatisticas(o[o["data"] <= corte]), _estatisticas(o[o["data"] > corte])
        tudo = _estatisticas(o)
        t_chute = _t_dif(o[o["data"] > corte], base_conf)
        t_desc = _t_dif(o[o["data"] <= corte], base_desc)
        aprovado = (conf.get("n", 0) >= MIN_TRADES_CONF and desc.get("n", 0) >= MIN_TRADES_CONF
                    and conf["expectativa"] > 0 and desc["expectativa"] > 0
                    and t_chute >= T_CONFIRMACAO and t_desc >= T_DESCOBERTA)
        # em observação: venceu o chute nos dois períodos, mas sem folga suficiente. NÃO gera sinal — só fica no placar.
        observacao = (not aprovado and conf.get("n", 0) >= 10 and conf.get("expectativa", -1) > 0
                      and t_chute >= T_DESCOBERTA and t_desc >= 1.0)
        linhas.append({"padrao": nome, "nome": titulo,
                       "status": "✅ Aprovado" if aprovado else "👀 Em observação" if observacao else "❌ Reprovado",
                       **{f"{k}_conf": v for k, v in conf.items()}, **{f"{k}_desc": v for k, v in desc.items()},
                       **{f"{k}_total": v for k, v in tudo.items()},
                       "vantagem_vs_chute": conf.get("expectativa", np.nan) - chute_conf.get("expectativa", np.nan),
                       "t_vs_chute": t_chute, "t_vs_chute_desc": t_desc})
    tab = pd.DataFrame(linhas)
    ordem = {"✅ Aprovado": 0, "👀 Em observação": 1, "❌ Reprovado": 2}
    tab = tab.sort_values(["status", "expectativa_conf"], key=lambda c: c.map(ordem) if c.name == "status" else -c).reset_index(drop=True)
    return {"padroes": tab, "operacoes": ops, "ind": ind, "chute": chute_conf}


# ------------------------------------------------------------------ sinais de hoje
def sinais_hoje(bt: dict, rk: pd.DataFrame, dias: int = 3) -> pd.DataFrame:
    """Padrões que dispararam nos últimos `dias` pregões e cuja entrada ainda vale (preço não fugiu nem bateu o stop)."""
    pad = bt["padroes"].set_index("padrao") if len(bt["padroes"]) else pd.DataFrame()
    ops = bt["operacoes"]
    info = rk.set_index("ticker") if len(rk) else pd.DataFrame()
    linhas = []
    for t, (df, g) in bt["ind"].items():
        if len(df) < 260:
            continue
        ult = df.iloc[-1]
        for nome in PADROES:
            if nome not in pad.index or pad.loc[nome, "status"] != "✅ Aprovado":  # só padrão aprovado vira sinal
                continue
            rec = g[nome].iloc[-dias:]
            if not rec.any():
                continue
            dia = rec[rec].index[-1]
            preco_sinal = float(df.loc[dia, "p"])
            stop_s, _ = niveis(preco_sinal, float(df.loc[dia, "osc"]))
            preco = float(ult["p"])
            if preco > preco_sinal * 1.02 or preco <= stop_s:
                continue  # a entrada já passou (subiu demais) ou já bateu o stop
            stop, alvo = niveis(preco, float(ult["osc"]))
            proprias = ops[(ops["ticker"] == t) & (ops["padrao"] == nome)] if len(ops) else pd.DataFrame()
            r = info.loc[t] if t in info.index else {}
            mb, mg, pvp = (r.get(k) if hasattr(r, "get") else None for k in ("margem_bazin", "margem_graham", "pvp"))
            barata = any(x is not None and x == x and c(x) for x, c in ((mb, lambda v: v > 0), (mg, lambda v: v > 0.2), (pvp, lambda v: 0 < v < 1)))
            linhas.append({
                "ticker": t, "padrao": nome, "padrao_nome": PADROES[nome][0], "status": pad.loc[nome, "status"],
                "data_sinal": dia.date(), "preco": preco, "stop": stop, "alvo": alvo,
                "ganho_alvo": alvo / preco - 1, "perda_stop": stop / preco - 1,
                "acerto_padrao": pad.loc[nome, "acerto_conf"], "expectativa_padrao": pad.loc[nome, "expectativa_conf"],
                "dias_medio": pad.loc[nome, "dias_medio_conf"],
                "acerto_acao": float((proprias["ret"] > 0).mean()) if len(proprias) >= 5 else np.nan, "n_acao": int(len(proprias)),
                "barata": barata, "nome": r.get("nome") if hasattr(r, "get") else t,
                "nota": r.get("nota") if hasattr(r, "get") else np.nan, "sinal_equipe": r.get("sinal") if hasattr(r, "get") else None,
                "consenso": r.get("consenso") if hasattr(r, "get") else None, "vetado": bool(r.get("vetado")) if hasattr(r, "get") and r.get("vetado") == r.get("vetado") else False,
            })
    s = pd.DataFrame(linhas)
    if s.empty:
        return s
    s = s[~s["vetado"]]  # Rex vetou (prejuízo, dado duvidoso, notícia grave): fora do trading também
    s["ordem"] = s["status"].map({"✅ Aprovado": 0, "👀 Em observação": 1}).fillna(2)
    return s.sort_values(["ordem", "barata", "expectativa_padrao"], ascending=[True, False, False]).drop(columns="ordem").reset_index(drop=True)


# ------------------------------------------------------------------ placar real (sinais registrados e conferidos depois)
def registrar(sinais: pd.DataFrame, hoje: date) -> None:
    if sinais is None or sinais.empty:
        return
    novo = sinais[["ticker", "padrao", "preco", "stop", "alvo", "data_sinal"]].assign(data=hoje.isoformat())
    novo["data_sinal"] = novo["data_sinal"].astype(str)
    try:
        antigo = pd.read_csv(REGISTRO, dtype={"data_sinal": str})
        if "data_sinal" not in antigo:
            antigo["data_sinal"] = antigo["data"]
        # o sinal vale por até 3 pregões: registra uma vez só (a primeira, que é a entrada que valeria)
        novo = pd.concat([antigo, novo], ignore_index=True).drop_duplicates(["ticker", "padrao", "data_sinal"], keep="first")
    except (FileNotFoundError, pd.errors.EmptyDataError):
        pass
    REGISTRO.parent.mkdir(parents=True, exist_ok=True)
    salvar_csv(novo, REGISTRO)


def placar_real(precos: dict[str, pd.Series]) -> dict:
    """Confere cada sinal registrado com o que o preço fez depois (mesmas regras de saída)."""
    try:
        reg = pd.read_csv(REGISTRO)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return {"n": 0, "abertos": 0, "tabela": pd.DataFrame()}
    linhas = []
    for _, r in reg.iterrows():
        s = precos.get(r["ticker"])
        if s is None:
            continue
        depois = s[s.index > pd.Timestamp(r["data"])].dropna()
        entrada, stop, alvo = float(r["preco"]), float(r["stop"]), float(r["alvo"])
        risco, res = entrada - stop, None
        for k, (d, v) in enumerate(depois.items()):  # mesmas regras do teste: alvo/stop, e saída no 63º pregão
            if v >= entrada + risco and stop < entrada:
                stop = entrada
            if v >= alvo:
                res = (d, alvo / entrada - 1 - CUSTO, "alvo")
                break
            if v <= stop:
                res = (d, v / entrada - 1 - CUSTO, "stop" if stop < entrada else "empate")
                break
            if k == PRAZO - 1:
                res = (d, v / entrada - 1 - CUSTO, "prazo")
                break
        linhas.append({**r.to_dict(), "resultado": res[2] if res else "aberto", "retorno": res[1] if res else
                       (float(depois.iloc[-1]) / entrada - 1 - CUSTO if len(depois) else 0.0), "fechou_em": res[0].date() if res else None})
    t = pd.DataFrame(linhas)
    if t.empty:
        return {"n": 0, "abertos": 0, "tabela": t}
    fech = t[t["resultado"] != "aberto"]
    return {"n": int(len(fech)), "abertos": int((t["resultado"] == "aberto").sum()),
            "acerto": float((fech["retorno"] > 0).mean()) if len(fech) else np.nan,
            "retorno_medio": float(fech["retorno"].mean()) if len(fech) else np.nan, "tabela": t}


# ------------------------------------------------------------------ as SUAS operações
COLS_OP = ["ticker", "data_compra", "preco_compra", "quantidade", "stop", "alvo", "status", "preco_venda", "data_venda", "obs"]


def ler_operacoes() -> pd.DataFrame:
    try:
        df = pd.read_csv(OPERACOES, dtype={c: str for c in ("ticker", "status", "obs", "data_compra", "data_venda")})
    except (FileNotFoundError, pd.errors.EmptyDataError):
        df = pd.DataFrame(columns=COLS_OP)
    for c in COLS_OP:
        if c not in df:
            df[c] = np.nan
    df["ticker"] = df["ticker"].fillna("").astype(str).str.upper().str.strip()
    df["status"] = df["status"].fillna("aberta")
    for c in ("data_compra", "data_venda", "obs"):  # texto sempre texto: coluna vazia não vira número (quebrava o editor do painel)
        df[c] = df[c].astype("object").where(df[c].notna(), None)
    for c in ("preco_compra", "quantidade", "stop", "alvo", "preco_venda"):
        df[c] = pd.to_numeric(df[c], errors="coerce").astype(float)
    return df[COLS_OP]


def salvar_operacoes(df: pd.DataFrame) -> None:
    df = df.copy()
    for c in COLS_OP:
        if c not in df:
            df[c] = np.nan
    df = df[df["ticker"].fillna("").astype(str).str.strip() != ""]
    df["ticker"] = df["ticker"].astype(str).str.upper().str.strip()
    OPERACOES.parent.mkdir(parents=True, exist_ok=True)
    salvar_csv(df[COLS_OP], OPERACOES)


def acompanhar(ops: pd.DataFrame, precos_agora: dict[str, float], hoje: date | None = None) -> pd.DataFrame:
    """Para cada operação aberta: resultado agora e o que fazer (vender no alvo, sair no stop, proteger o ganho...)."""
    hoje = pd.Timestamp(hoje or hoje_brt())
    linhas = []
    for _, o in ops[ops["status"].fillna("aberta").str.lower() == "aberta"].iterrows():
        t, pc = o["ticker"], float(o["preco_compra"]) if o["preco_compra"] == o["preco_compra"] else np.nan
        p = precos_agora.get(t)
        if p is None or not pc == pc:
            continue
        stop, alvo = o["stop"], o["alvo"]
        q = float(o["quantidade"]) if o["quantidade"] == o["quantidade"] else 0.0
        dias = len(pd.bdate_range(pd.Timestamp(o["data_compra"]), hoje)) - 1 if isinstance(o["data_compra"], str) and o["data_compra"] else 0
        risco = pc - stop if stop == stop else np.nan
        if alvo == alvo and p >= alvo:
            acao = "🟢 ALVO atingido: vender (ou subir o stop para garantir a maior parte do ganho)"
        elif stop == stop and p <= stop:
            acao = "🔴 STOP atingido: vender para limitar a perda (disciplina é o que protege o capital)"
        elif risco == risco and risco > 0 and p >= pc + risco and stop < pc:
            acao = f"🛡️ Ganho já cobre o risco: suba o stop para o preço de compra ({pc:.2f})".replace(".", ",")
        elif dias >= PRAZO:
            acao = "⏳ Prazo de 3 meses vencido: o padrão não andou — avalie vender e liberar o dinheiro"
        else:
            acao = "⚪ Manter: dentro do plano"
        linhas.append({"ticker": t, "preco_compra": pc, "preco_agora": p, "quantidade": q, "resultado": p / pc - 1,
                       "resultado_rs": (p - pc) * q, "stop": stop, "alvo": alvo, "dias": dias, "o_que_fazer": acao})
    return pd.DataFrame(linhas)


def alertas_operacoes(precos_agora: dict[str, float]) -> list[str]:
    """Avisos de venda (alvo/stop/proteger) das SUAS operações — uma vez por dia para cada situação."""
    acomp = acompanhar(ler_operacoes(), precos_agora)
    if acomp.empty:
        return []
    try:
        est = json.loads(ESTADO_ALERTAS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        est = {}
    hoje = hoje_brt().isoformat()
    if est.get("data") != hoje:
        est = {"data": hoje, "enviados": []}
    novos = []
    for _, a in acomp.iterrows():
        if a["o_que_fazer"].startswith("⚪"):
            continue
        chave = f"{a['ticker']}:{a['o_que_fazer'][:2]}"
        if chave in est["enviados"]:
            continue
        est["enviados"].append(chave)
        novos.append(f"⚡ Trading {a['ticker']}: {a['o_que_fazer']}. Comprou a {a['preco_compra']:.2f}, agora {a['preco_agora']:.2f} "
                     f"({a['resultado'] * 100:+.1f}%).".replace(".", ","))
    ESTADO_ALERTAS.parent.mkdir(parents=True, exist_ok=True)
    ESTADO_ALERTAS.write_text(json.dumps(est), encoding="utf-8")
    return novos


def tamanho_posicao(capital: float, risco_pct: float, preco: float, stop: float) -> dict:
    """Quantas ações comprar para que, se bater o stop, a perda seja só `risco_pct` do capital de trading."""
    if preco <= 0 or stop >= preco:
        return {"quantidade": 0, "valor": 0.0, "perda_maxima": 0.0}
    perda_max = capital * risco_pct
    q = int(perda_max // (preco - stop))
    q = min(q, int(capital // preco))  # nunca mais do que o capital
    return {"quantidade": q, "valor": q * preco, "perda_maxima": q * (preco - stop)}


def resumir(bt: dict) -> dict:
    """O que vai para o arquivo da apuração (sem os DataFrames grandes)."""
    return {"padroes": bt["padroes"], "chute": bt["chute"],
            "n_operacoes": int(len(bt["operacoes"]))}
