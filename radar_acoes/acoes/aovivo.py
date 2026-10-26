"""Mercado ao vivo: cotação do pregão de todas as ações vigiadas — o que sobe e o que cai agora.

Fonte: Yahoo Finance. Para a B3, o Yahoo entrega as cotações com cerca de 15 minutos de atraso
(cotação em tempo real de verdade só com contrato pago de dados da B3). O painel avisa isso na tela.
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

import pandas as pd

FUSO = ZoneInfo("America/Sao_Paulo")
FONTE = "Yahoo Finance · B3 com atraso de ~15 min"
IBOV = "^BVSP"


def pregao_aberto(t: datetime | None = None) -> bool:
    t = t or datetime.now(FUSO)
    return t.weekday() < 5 and (10, 0) <= (t.hour, t.minute) < (18, 0)


def _local(s: pd.Series) -> pd.Series:
    """Índice no horário de Brasília, sem fuso (o Yahoo devolve em UTC ou no fuso da bolsa)."""
    s = s.dropna()
    idx = pd.to_datetime(s.index)
    if idx.tz is not None:
        idx = idx.tz_convert(FUSO).tz_localize(None)
    return pd.Series(s.to_numpy(dtype=float), index=idx).sort_index()


def _colunas(df: pd.DataFrame, simbolos: list[str]) -> dict[str, pd.Series]:
    saida = {}
    for s in simbolos:
        try:
            col = df[s]["Close"] if isinstance(df.columns, pd.MultiIndex) else df["Close"]
        except KeyError:
            continue
        col = _local(col)
        if not col.empty:
            saida[s.removesuffix(".SA")] = col
    return saida


def baixar(tickers: list[str]) -> tuple[dict[str, pd.Series], dict[str, pd.Series]]:
    """(intradiário de 5 em 5 min, fechamentos diários) por ticker. Duas chamadas em lote para todas as ações."""
    import yfinance as yf  # import tardio: os testes não precisam da biblioteca

    simbolos = [f"{t}.SA" for t in tickers] + [IBOV]
    comum = dict(group_by="ticker", progress=False, threads=True, auto_adjust=False, prepost=False)
    intra = yf.download(simbolos, period="5d", interval="5m", **comum)
    diario = yf.download(simbolos, period="10d", interval="1d", **comum)
    return _colunas(intra, simbolos), _colunas(diario, simbolos)


def resumir(intra: dict[str, pd.Series], diario: dict[str, pd.Series]) -> pd.DataFrame:
    """Uma linha por ação: preço agora, fechamento anterior, variação do dia, mínima/máxima e o gráfico do dia."""
    linhas = []
    for t in sorted(set(intra) | set(diario)):
        s_i, s_d = intra.get(t), diario.get(t)
        if s_i is not None and not s_i.empty:
            dia = s_i.index[-1].normalize()
            hoje = s_i[s_i.index >= dia]
            preco, hora = float(hoje.iloc[-1]), s_i.index[-1]
            antes_i = s_i[s_i.index < dia]
        elif s_d is not None and not s_d.empty:
            dia, hoje, antes_i = s_d.index[-1].normalize(), s_d.iloc[-1:], None
            preco, hora = float(s_d.iloc[-1]), s_d.index[-1]
        else:
            continue
        # fechamento anterior: o oficial (diário) do último pregão antes de hoje; se faltar, a última cotação de ontem
        anterior = None
        if s_d is not None:
            antes_d = s_d[s_d.index.normalize() < dia]
            if not antes_d.empty:
                anterior = float(antes_d.iloc[-1])
        if anterior is None and antes_i is not None and not antes_i.empty:
            anterior = float(antes_i.iloc[-1])
        var = preco / anterior - 1 if anterior else float("nan")
        linhas.append({
            "ticker": t, "preco": preco, "anterior": anterior, "var_dia": var,
            "abertura": float(hoje.iloc[0]), "minima": float(hoje.min()), "maxima": float(hoje.max()),
            "hora": hora, "pregao": dia.date(), "grafico": [round(float(x), 4) for x in hoje.to_numpy()],
        })
    df = pd.DataFrame(linhas)
    if df.empty:
        return df
    return df.sort_values("var_dia", ascending=False, na_position="last").reset_index(drop=True)


def placar(df: pd.DataFrame, faixa: float = 0.001) -> dict:
    """Quantas sobem, caem e estão estáveis (variação dentro de ±0,1%)."""
    v = df["var_dia"].dropna()
    return {"sobem": int((v > faixa).sum()), "caem": int((v < -faixa).sum()), "estaveis": int((v.abs() <= faixa).sum())}
