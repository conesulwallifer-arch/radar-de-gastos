"""🌎 Helena — Analista de Política e Macro: governo, juros, câmbio, commodities e relações exteriores.

Duas partes, com regras diferentes de confiança:

1. MEDIDA (pode votar): quanto cada ação costuma reagir a dólar, petróleo, minério de ferro e juros dos EUA,
   descontado o movimento da bolsa (regressão com retornos semanais dos últimos 3 anos). Junta essas sensibilidades
   com o que esses fatores fizeram nos últimos 3 meses = "vento a favor ou contra" de cada ação.
   O vento é testado no passado sem colar (mês a mês, com as sensibilidades estimadas só com dados anteriores);
   a Helena só vota se o teste mostrar vantagem estatisticamente real — igual à Sofia.

2. LEITURA (não vota): manchetes por tema (contas do governo, Copom, política/eleição, EUA, China, petróleo,
   impostos sobre dividendos, câmbio) com o tom de cada uma. Com a chave da IA, ela pesquisa a internet e escreve
   uma leitura de cenário dizendo quais setores ganham e quais perdem. Isso orienta, mas não entra no voto —
   opinião sobre política não é testável como os números.
"""
from __future__ import annotations

import pickle
from datetime import date

import numpy as np
import pandas as pd

from . import DADOS

FATORES = {  # nome: (símbolo no Yahoo, descrição, tipo de variação)
    "dolar": ("BRL=X", "Dólar (R$ por US$)", "pct"),
    "petroleo": ("BZ=F", "Petróleo Brent", "pct"),
    "minerio": ("TIO=F", "Minério de ferro", "pct"),
    "juros_eua": ("^TNX", "Juros dos EUA (10 anos)", "dif"),
}
IBOV = "^BVSP"
NOMES = {k: v[1] for k, v in FATORES.items()}

TEMAS = {
    "Contas do governo": ["arcabouço fiscal", "gastos do governo dívida pública", "Haddad Fazenda meta fiscal"],
    "Juros e inflação (Copom)": ["Copom Selic", "Banco Central juros inflação"],
    "Política e eleição": ["governo Lula mercado financeiro", "eleição presidente mercado bolsa"],
    "Estados Unidos": ["Estados Unidos tarifas Brasil", "Fed juros Estados Unidos"],
    "China": ["China economia Brasil exportações", "China minério de ferro demanda"],
    "Petróleo": ["petróleo Brent OPEP", "Petrobras preço combustíveis governo"],
    "Impostos sobre dividendos": ["tributação de dividendos imposto de renda", "reforma tributária empresas lucros"],
    "Câmbio": ["dólar hoje real câmbio"],
}

# o que cada tema costuma significar para os setores (conhecimento de mercado; orienta a leitura, não vota)
IMPACTO_TEMAS = {
    "Juros caindo": ("Construção, Varejo/Consumo, Shoppings, Energia elétrica e Saneamento (dívidas ficam mais baratas e "
                     "os dividendos ficam mais atraentes que a renda fixa)", "Bancos e seguradoras ganham um pouco menos com o caixa"),
    "Juros subindo": ("Bancos e Seguradoras (ganham com o dinheiro em caixa)", "Construção, Varejo, empresas endividadas"),
    "Dólar subindo": ("Exportadoras: Mineração, Papel e celulose, Petróleo, Frigoríficos, WEGE3, EMBR3",
                      "Quem importa ou tem dívida em dólar; inflação pressiona os juros"),
    "Risco fiscal (gastos sem controle)": ("Exportadoras (dólar sobe)", "Quase toda a bolsa: juros longos sobem; pior para Construção e Varejo"),
    "Tarifas/tensão com os EUA": ("Pouco: algumas vendem mais para outros mercados", "Exportadoras que dependem dos EUA (aço, aviões, carne, café)"),
    "China crescendo": ("Mineração e siderurgia, Papel e celulose, agronegócio", "—"),
    "Petróleo subindo": ("PETR4, PRIO3, RECV3", "Companhias aéreas, transporte, distribuidoras (custo)"),
    "Imposto sobre dividendos": ("—", "Quem vive de dividendos (veja se o seu volume passa do limite de isenção)"),
}

ANOS_BETA = 3
HORIZONTE = 63   # pregões (~3 meses)


# ------------------------------------------------------------------ dados
def baixar_fatores(anos: int = 10, forcar: bool = False) -> dict[str, pd.Series]:
    """Fechamentos diários de cada fator + Ibovespa (Yahoo Finance), com cache do dia."""
    arq = DADOS / "cache" / f"fatores_macro_{date.today():%Y%m%d}.pkl"
    if arq.exists() and not forcar:
        with open(arq, "rb") as f:
            return pickle.load(f)
    import yfinance as yf

    simbolos = [v[0] for v in FATORES.values()] + [IBOV]
    df = yf.download(simbolos, period=f"{anos}y", interval="1d", group_by="ticker", progress=False,
                     auto_adjust=False, threads=True)
    saida = {}
    for nome, sym in [*[(k, v[0]) for k, v in FATORES.items()], ("ibov", IBOV)]:
        try:
            s = df[sym]["Close"].dropna()
        except KeyError:
            continue
        idx = pd.to_datetime(s.index)
        s.index = idx.tz_convert(None) if idx.tz is not None else idx
        if len(s) > 250:
            saida[nome] = s.astype(float)
    if saida:
        arq.parent.mkdir(parents=True, exist_ok=True)
        for velho in arq.parent.glob("fatores_macro_*.pkl"):
            velho.unlink(missing_ok=True)
        with open(arq, "wb") as f:
            pickle.dump(saida, f)
    return saida


def noticias_temas(dias: int = 7, n: int = 8) -> dict[str, list[dict]]:
    from .noticias import buscar_consulta
    saida = {}
    for tema, consultas in TEMAS.items():
        vistos, itens = set(), []
        for q in consultas:
            for x in buscar_consulta(q, dias, n):
                if x["titulo"] not in vistos:
                    vistos.add(x["titulo"])
                    itens.append(x)
        itens.sort(key=lambda x: x["quando"] or pd.Timestamp(0), reverse=True)
        saida[tema] = itens[:n]
    return saida


# ------------------------------------------------------------------ sensibilidades (betas)
def _semanal(s: pd.Series, tipo: str = "pct") -> pd.Series:
    w = s.dropna().resample("W-FRI").last()
    return w.diff() / 100 if tipo == "dif" else np.log(w).diff()  # juros: variação em pontos percentuais (÷100)


def _matriz(precos: dict[str, pd.Series], fatores: dict[str, pd.Series]):
    """Retornos semanais alinhados: ações (colunas) e fatores (ibov + os disponíveis)."""
    fx = {"ibov": _semanal(fatores["ibov"])}
    for k, (_, _, tipo) in FATORES.items():
        if k in fatores:
            fx[k] = _semanal(fatores[k], tipo)
    F = pd.DataFrame(fx)
    A = pd.DataFrame({t: _semanal(s) for t, s in precos.items() if s is not None and len(s) > 300})
    idx = F.index.intersection(A.index)
    return A.loc[idx], F.loc[idx]


def _ols(y: np.ndarray, X: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Coeficientes e estatística t (MQO com intercepto)."""
    Xb = np.c_[np.ones(len(X)), X]
    beta, *_ = np.linalg.lstsq(Xb, y, rcond=None)
    resid = y - Xb @ beta
    gl = max(1, len(y) - Xb.shape[1])
    s2 = resid @ resid / gl
    try:
        cov = s2 * np.linalg.inv(Xb.T @ Xb)
        t = beta / np.sqrt(np.clip(np.diag(cov), 1e-18, None))
    except np.linalg.LinAlgError:
        t = np.zeros_like(beta)
    return beta[1:], t[1:]


def exposicoes(A: pd.DataFrame, F: pd.DataFrame, ate: pd.Timestamp | None = None, anos: int = ANOS_BETA) -> pd.DataFrame:
    """Sensibilidade de cada ação a cada fator, descontado o Ibovespa, usando só dados até `ate`."""
    ate = ate or A.index.max()
    janela = (A.index <= ate) & (A.index > ate - pd.DateOffset(years=anos))
    Fj = F.loc[janela]
    linhas = []
    for t in A.columns:
        d = pd.concat([A.loc[janela, t].rename("y"), Fj], axis=1).dropna()
        if len(d) < 80:
            continue
        b, tt = _ols(d["y"].to_numpy(), d[Fj.columns].to_numpy())
        linhas.append({"ticker": t, **{f"beta_{c}": v for c, v in zip(Fj.columns, b)}, **{f"t_{c}": v for c, v in zip(Fj.columns, tt)}})
    return pd.DataFrame(linhas)


def movimentos(fatores: dict[str, pd.Series], ate: pd.Timestamp | None = None, dias: int = HORIZONTE) -> dict[str, float]:
    """Quanto cada fator andou nos últimos ~3 meses (até `ate`)."""
    out = {}
    for k, (_, _, tipo) in [("ibov", (IBOV, "Ibovespa", "pct")), *FATORES.items()]:
        s = fatores.get(k)
        if s is None:
            continue
        s = s[s.index <= ate] if ate is not None else s
        if len(s) <= dias:
            continue
        a, b = float(s.iloc[-dias - 1]), float(s.iloc[-1])
        out[k] = (b - a) / 100 if tipo == "dif" else np.log(b / a)
    return out


def vento(expo: pd.DataFrame, mov: dict[str, float], t_min: float = 2.0) -> pd.DataFrame:
    """Efeito estimado dos movimentos recentes dos fatores em cada ação (só sensibilidades estatisticamente claras)."""
    if expo.empty:
        return pd.DataFrame(columns=["ticker", "vento"])
    linhas = []
    for _, r in expo.iterrows():
        contrib = {}
        for k in FATORES:
            b, t = r.get(f"beta_{k}"), r.get(f"t_{k}")
            if k in mov and b == b and t == t and abs(t) >= t_min:
                contrib[k] = float(b) * mov[k]
        total = sum(contrib.values())
        motor = max(contrib, key=lambda k: abs(contrib[k])) if contrib else None
        linhas.append({"ticker": r["ticker"], "vento": total, "motor": motor,
                       "motor_efeito": contrib.get(motor, 0.0) if motor else 0.0, **{f"efeito_{k}": v for k, v in contrib.items()}})
    return pd.DataFrame(linhas)


# ------------------------------------------------------------------ teste sem colar
def validar(precos: dict[str, pd.Series], fatores: dict[str, pd.Series], anos_teste: int = 4) -> dict:
    """Mês a mês: sensibilidades estimadas SÓ com os 3 anos anteriores + movimento dos fatores nos 3 meses anteriores
    → vento; confere se as ações com mais vento a favor renderam mais que as outras nos 3 meses SEGUINTES."""
    if "ibov" not in fatores:
        return {"n": 0}
    A, F = _matriz(precos, fatores)
    if A.empty:
        return {"n": 0}
    diario = pd.DataFrame({t: s for t, s in precos.items() if s is not None and len(s) > 300}).sort_index().ffill()
    fim = diario.index.max()
    datas = pd.date_range(fim - pd.DateOffset(years=anos_teste), fim - pd.Timedelta(days=95), freq="ME")
    casos = []
    for d in datas:
        expo = exposicoes(A, F, ate=d)
        if len(expo) < 10:
            continue
        v = vento(expo, movimentos(fatores, ate=d))
        pos = diario.index.searchsorted(d, side="right") - 1
        if pos < 0 or pos + HORIZONTE >= len(diario):
            continue
        ret = diario.iloc[pos + HORIZONTE] / diario.iloc[pos] - 1
        exc = (ret - ret.median()).rename("excesso")
        m = v.merge(exc, left_on="ticker", right_index=True).dropna(subset=["excesso"])
        m = m[m["vento"] != 0]
        if len(m) >= 8:
            casos.append(m.assign(mes=d))
    if not casos:
        return {"n": 0}
    c = pd.concat(casos, ignore_index=True)
    c["q"] = c.groupby("mes")["vento"].rank(pct=True)
    topo = c[c["q"] > 0.8].groupby("mes")["excesso"].mean()
    fundo = c[c["q"] <= 0.2].groupby("mes")["excesso"].mean()
    dif = (topo - fundo).dropna()
    t_stat = float(dif.mean() / (dif.std(ddof=1) / np.sqrt(len(dif))) / np.sqrt(3)) if len(dif) > 6 and dif.std() > 0 else 0.0
    acerto = float((np.sign(c["vento"]) == np.sign(c["excesso"])).mean())
    return {"n": int(len(c)), "meses": int(c["mes"].nunique()), "acerto": acerto,
            "spread_3m": float(dif.mean()) if len(dif) else np.nan, "t_stat": t_stat}


# ------------------------------------------------------------------ leitura com IA (opcional)
def leitura_ia(temas: dict[str, list[dict]], mov: dict[str, float], macro: dict) -> str | None:
    from . import ia
    if not ia.disponivel():
        return None
    manchetes = "\n".join(f"[{tema}] {x['titulo']} ({x['fonte']})" for tema, itens in temas.items() for x in itens[:5])
    movs = ", ".join(f"{NOMES.get(k, 'Ibovespa')}: {v * 100:+.1f}{' p.p.' if k == 'juros_eua' else '%'}" for k, v in mov.items())
    sistema = ("Você é Helena, analista de política e macroeconomia de uma mesa de ações brasileiras para investidor de LONGO PRAZO focado "
               "em dividendos, que também faz trades de médio prazo. Seja objetiva, apartidária e honesta: diga o que é fato, o que é "
               "expectativa do mercado e o que é incerteza. Nunca invente números; cite as fontes.")
    pedido = (f"Data: {date.today():%d/%m/%Y}. Selic {macro.get('selic', 0) * 100:.2f}%, IPCA 12m {macro.get('ipca_12m', 0) * 100:.1f}%. "
              f"Movimentos dos últimos 3 meses: {movs}.\nManchetes da semana:\n{manchetes}\n\n"
              "Pesquise na internet o que mudou nos últimos 7 dias em: governo e contas públicas, Copom/juros, política (inclusive "
              "eleição e transição de governo, se houver), relação com EUA (tarifas) e China, petróleo e minério, e regras de "
              "tributação de dividendos. Responda em português, em tópicos curtos:\n"
              "1) O que mudou (3–6 fatos, com fonte).\n2) Setores da B3 favorecidos e prejudicados, com o porquê.\n"
              "3) O que isso significa para quem aporta todo mês buscando dividendos.\n4) O que vigiar nas próximas semanas.")
    return ia.chamar(sistema, [{"role": "user", "content": pedido}], [ia.pesquisa_web(6)])


# ------------------------------------------------------------------ tudo junto
def clima_temas(temas: dict[str, list[dict]]) -> pd.DataFrame:
    linhas = []
    for tema, itens in temas.items():
        pos = sum(1 for x in itens if x["tom"] == "positiva")
        neg = sum(1 for x in itens if x["tom"] == "negativa")
        linhas.append({"tema": tema, "manchetes": len(itens), "positivas": pos, "negativas": neg,
                       "clima": (pos - neg) / len(itens) if itens else 0.0})
    return pd.DataFrame(linhas)


def rodar(rk: pd.DataFrame, precos: dict[str, pd.Series], fatores: dict[str, pd.Series], temas: dict[str, list[dict]],
          macro: dict, usar_ia: bool = False) -> dict:
    """{'tabela': vento por ação, 'setores': vento por setor, 'movimentos', 'validacao', 'fator', 'clima', 'temas', 'leitura_ia'}."""
    vazio = {"tabela": pd.DataFrame(), "setores": pd.DataFrame(), "movimentos": {}, "validacao": {"n": 0}, "fator": 0.0,
             "clima": clima_temas(temas), "temas": temas, "leitura_ia": None}
    if not fatores or "ibov" not in fatores:
        return vazio
    usados = {t: precos[t] for t in rk["ticker"] if t in precos}
    A, F = _matriz(usados, fatores)
    expo = exposicoes(A, F)
    mov = movimentos(fatores)
    v = vento(expo, mov)
    tab = expo.merge(v, on="ticker", how="left") if len(expo) else pd.DataFrame()
    val = validar(usados, fatores)
    fator = 0.0
    if val.get("n", 0) >= 300 and val.get("t_stat", 0) >= 2.0 and val.get("acerto", 0) > 0.5:
        fator = float(np.clip((val["t_stat"] - 1.0) / 2.0, 0, 1))
    setores = pd.DataFrame()
    if len(tab):
        tab = tab.merge(rk[["ticker", "setor"]], on="ticker", how="left")
        tab["vento_quintil"] = tab["vento"].rank(pct=True)
        setores = (tab.groupby("setor").agg(vento=("vento", "median"), acoes=("ticker", "count"))
                   .reset_index().sort_values("vento", ascending=False))
    leitura = None
    if usar_ia:
        try:
            leitura = leitura_ia(temas, mov, macro)
        except Exception:  # noqa: BLE001
            leitura = None
    return {**vazio, "tabela": tab, "setores": setores, "movimentos": mov, "validacao": val, "fator": fator, "leitura_ia": leitura}


def resumir(res: dict) -> dict:
    return res
