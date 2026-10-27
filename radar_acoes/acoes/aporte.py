"""Sugestão do aporte do mês: em quais ações colocar o dinheiro, quantas cotas comprar de cada uma."""
from __future__ import annotations

import math

import pandas as pd

from . import DADOS

ARQ_CARTEIRA = DADOS / "carteira.csv"  # colunas: ticker,quantidade[,preco_medio]


def _numero(serie: pd.Series) -> pd.Series:
    """Aceita 1000, 1.000, 1.000,50, 35,50 e 35.50 (Excel em português ou inglês)."""
    def um(v):
        t = str(v).strip().replace("R$", "").replace(" ", "")
        if t in ("", "nan", "None"):
            return float("nan")
        if "," in t:                      # vírgula decimal: o ponto é separador de milhar
            t = t.replace(".", "").replace(",", ".")
        elif t.count(".") > 1 or (t.count(".") == 1 and len(t.split(".")[1]) == 3 and t.split(".")[0].lstrip("-").isdigit()
                                  and len(t.split(".")[0].lstrip("-")) <= 3 and float(t.replace(".", "")) >= 1000):
            t = t.replace(".", "")        # 1.000 / 12.500 = milhar
        try:
            return float(t)
        except ValueError:
            return float("nan")
    return serie.map(um)


def ler_carteira(caminho=None) -> pd.DataFrame:
    """Lê a carteira (CSV de vírgula ou ponto e vírgula, com ou sem BOM do Excel). Nunca derruba a apuração:
    se o arquivo estiver estranho, avisa e segue com a carteira vazia."""
    arq = caminho or ARQ_CARTEIRA
    vazio = pd.DataFrame(columns=["ticker", "quantidade", "preco_medio"])
    try:
        df = pd.read_csv(arq, sep=None, engine="python", encoding="utf-8-sig", dtype=str)
    except (FileNotFoundError, pd.errors.EmptyDataError):
        return vazio
    except Exception as e:  # noqa: BLE001
        print(f"  [aviso] não consegui ler a carteira ({e}); seguindo sem ela.")
        return vazio
    df.columns = [str(c).strip().lower().replace("\ufeff", "") for c in df.columns]
    if "ticker" not in df or "quantidade" not in df:
        print("  [aviso] a carteira precisa das colunas ticker e quantidade; seguindo sem ela.")
        return vazio
    df["ticker"] = df["ticker"].astype(str).str.strip().str.upper()
    df = df[df["ticker"].str.len() >= 4]
    df["quantidade"] = _numero(df["quantidade"]).fillna(0)
    df["preco_medio"] = _numero(df["preco_medio"]) if "preco_medio" in df else float("nan")
    return df.groupby("ticker", as_index=False).agg(quantidade=("quantidade", "sum"), preco_medio=("preco_medio", "mean"))


def escolher(ranking: pd.DataFrame, n_ativos: int = 10, max_por_setor: int = 2) -> pd.DataFrame:
    """As melhores do ranking com sinal Comprar/Acumular, limitando ações por setor (diversificação)."""
    elegiveis = ranking[ranking["sinal"].isin(["Comprar", "Acumular"])].sort_values("nota", ascending=False)
    escolhidas, por_setor = [], {}
    for _, r in elegiveis.iterrows():
        if por_setor.get(r["setor"], 0) >= max_por_setor:
            continue
        escolhidas.append(r)
        por_setor[r["setor"]] = por_setor.get(r["setor"], 0) + 1
        if len(escolhidas) >= n_ativos:
            break
    return pd.DataFrame(escolhidas)


def sugerir(ranking: pd.DataFrame, valor: float, carteira: pd.DataFrame | None = None,
            n_ativos: int = 10, max_por_setor: int = 2) -> tuple[pd.DataFrame, float]:
    """Retorna (tabela de compras, sobra em R$).

    Alvo de cada ação proporcional à nota; o aporte vai primeiro para quem está mais abaixo do alvo,
    com bônus para quem está mais barata em relação ao preço-teto. Compra cotas inteiras (mercado fracionário)."""
    carteira = carteira if carteira is not None else ler_carteira()
    alvo = escolher(ranking, n_ativos, max_por_setor)
    if alvo.empty or valor <= 0:
        return pd.DataFrame(), valor
    qtd_atual = dict(zip(carteira["ticker"], carteira["quantidade"])) if len(carteira) else {}
    precos = dict(zip(ranking["ticker"], ranking["preco"]))
    atual = {t: qtd_atual.get(t, 0) * precos.get(t, 0) for t in alvo["ticker"]}
    total = sum(qtd_atual.get(t, 0) * (precos.get(t) or 0) for t in qtd_atual) + valor

    pesos = alvo.set_index("ticker")["nota"]
    pesos = pesos / pesos.sum()
    margem = alvo.set_index("ticker")["margem_bazin"].fillna(0).clip(lower=0, upper=0.3)
    falta = {t: max(0.0, total * pesos[t] - atual[t]) for t in alvo["ticker"]}
    prioridade = {t: falta[t] * (1 + margem[t]) for t in falta}
    soma = sum(prioridade.values()) or 1.0
    if sum(prioridade.values()) == 0:
        prioridade, soma = dict(pesos), 1.0

    compra = {t: math.floor(valor * prioridade[t] / soma / precos[t]) for t in prioridade if precos[t] > 0}
    sobra = valor - sum(compra[t] * precos[t] for t in compra)
    # com a sobra, compra mais 1 cota de cada (em ordem de prioridade) enquanto couber
    ordem = sorted(compra, key=prioridade.get, reverse=True)
    comprou = True
    while comprou:
        comprou = False
        for t in ordem:
            if precos[t] <= sobra:
                compra[t] += 1
                sobra -= precos[t]
                comprou = True

    linhas = []
    for _, r in alvo.iterrows():
        t = r["ticker"]
        q = compra.get(t, 0)
        linhas.append({"ticker": t, "nome": r["nome"], "setor": r["setor"], "sinal": r["sinal"], "nota": r["nota"],
                       "preco": r["preco"], "preco_teto": r["preco_teto_bazin"], "dy_medio_5a": r["dy_medio_5a"],
                       "comprar_qtd": q, "valor": q * r["preco"],
                       "renda_anual_estimada": q * (r.get("proventos_media_3a") or 0),
                       "ja_tenho": qtd_atual.get(t, 0)})
    df = pd.DataFrame(linhas)
    df = df[df["comprar_qtd"] > 0].sort_values("valor", ascending=False).reset_index(drop=True)
    return df, round(sobra, 2)


def revisar_carteira(ranking: pd.DataFrame, carteira: pd.DataFrame | None = None) -> pd.DataFrame:
    """Ações que você já tem e merecem atenção (sinal Evitar ou nota caindo). Não é ordem de venda."""
    carteira = carteira if carteira is not None else ler_carteira()
    if carteira.empty:
        return pd.DataFrame()
    m = carteira.merge(ranking, on="ticker", how="left")
    m["valor_atual"] = m["quantidade"] * m["preco"]
    m["resultado"] = m["preco"] / m["preco_medio"] - 1
    m["renda_anual_estimada"] = m["quantidade"] * m["proventos_media_3a"]
    return m
