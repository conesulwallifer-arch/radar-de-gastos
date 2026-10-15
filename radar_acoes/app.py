"""Painel do Radar de Ações:  python -m streamlit run app.py"""
from __future__ import annotations

import os
import pickle
import sys

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acoes import AVISO, aporte, meta, plano, universo  # noqa: E402
from apurar import ULTIMO, apurar  # noqa: E402

st.set_page_config(page_title="Radar de Ações", page_icon="📈", layout="wide")

COR_SINAL = {"Comprar": "🟢", "Acumular": "🟡", "Aguardar": "🟠", "Evitar": "🔴"}
COR_CONF = {"Alta": "✅ Alta", "Média": "⚠️ Média", "Baixa": "❌ Baixa"}
NUM = "localized"  # números no formato do seu computador (1.234,56)


def brl(x, casas: int = 2) -> str:
    if x is None or x != x:
        return "—"
    return f"R$ {x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x, casas: int = 1) -> str:
    return "—" if x is None or x != x else f"{x * 100:.{casas}f}%".replace(".", ",")


def col_rs(titulo: str, ajuda: str | None = None):
    return st.column_config.NumberColumn(f"{titulo} (R$)", format=NUM, help=ajuda)


def col_pct(titulo: str, ajuda: str | None = None):
    return st.column_config.NumberColumn(f"{titulo} (%)", format=NUM, help=ajuda)


@st.cache_data(show_spinner=False)
def carregar(_marca: float) -> dict | None:
    if not ULTIMO.exists():
        return None
    with open(ULTIMO, "rb") as f:
        return pickle.load(f)


def rodar(demo: bool):
    with st.spinner("Apurando: cotações, proventos, indicadores, notícias, juros do Banco Central e teste no passado "
                    "(alguns minutos na 1ª vez do dia)..."):
        apurar(universo.tickers(), plano.ler()["aporte_mensal"], usar_demo=demo, enviar=False)
    st.cache_data.clear()
    st.rerun()


# ======================================================================= topo
st.title("📈 Radar de Ações")
st.caption("Renda passiva e patrimônio no longo prazo, com dados reais atualizados todo dia. " + AVISO)

with st.sidebar:
    st.header("Atualizar")
    if st.button("🔄 Apurar agora (dados reais)", width="stretch", type="primary"):
        rodar(False)
    if st.button("🧪 Testar com dados fictícios", width="stretch"):
        rodar(True)
    st.caption("O ideal é apurar todo dia útil depois das 18h (fechamento da B3). "
               "Agende o arquivo *Apurar Acoes.bat* no Windows ou use o GitHub Actions (veja o README).")

R = carregar(ULTIMO.stat().st_mtime if ULTIMO.exists() else 0)
if R is None:
    st.info("Ainda não há apuração. Clique em **🔄 Apurar agora** na barra lateral (precisa de internet).")
    st.stop()

rk: pd.DataFrame = R["ranking"]
mac: dict = R.get("macro") or {"selic": 0.14, "ipca_12m": 0.045, "cdi_liquido": 0.119, "estimado": True}
pl = plano.ler()
cart = aporte.ler_carteira()

if R.get("demo"):
    st.error("⚠️ **MODO DEMONSTRAÇÃO — NÚMEROS FICTÍCIOS.** Nada aqui vale para investir. "
             "Clique em **🔄 Apurar agora (dados reais)** na barra lateral.")

# barra de "frescor" dos dados: o usuário sempre sabe de quando é cada número
datas = pd.to_datetime(rk["data_cotacao"].dropna()) if "data_cotacao" in rk else pd.Series(dtype="datetime64[ns]")
ult_cot = datas.max() if len(datas) else None
atraso = len(pd.bdate_range(ult_cot, pd.Timestamp.today().normalize())) - 1 if ult_cot is not None else 99
fresco = (f"📅 Apuração de **{R['data']:%d/%m/%Y}** · cotações até **{ult_cot:%d/%m/%Y}** (Yahoo Finance) · "
          if ult_cot is not None else f"📅 Apuração de **{R['data']:%d/%m/%Y}** · ")
fresco += (f"Selic **{pct(mac['selic'], 2)}**, IPCA 12m **{pct(mac['ipca_12m'], 2)}** "
           + ("(⚠️ estimados: Banco Central fora do ar)" if mac.get("estimado") else "(Banco Central)"))
(st.warning if atraso > 3 else st.caption)(fresco + (" — **dados com mais de 3 dias úteis: clique em Apurar agora.**" if atraso > 3 else ""))

abas = st.tabs(["✅ O que fazer hoje", "🎯 Rumo ao R$ 1 milhão", "🏆 Ranking", "🏢 Empresa", "💼 Minha carteira",
                "🧪 O sistema funciona?", "🔔 Alertas", "❓ Como funciona e limites"])

# carteira-alvo e números da meta, usados em várias abas
esc = aporte.escolher(rk, 10, 2)
cart_esp = R.get("carteira_esperada") or meta.carteira_esperada(esc)
pat_hoje = plano.patrimonio_atual(pl, cart, rk)

# ======================================================================= HOJE
with abas[0]:
    st.subheader(f"Este mês, com {brl(pl['aporte_mensal'])} de aporte, compre:")
    compras, sobra = aporte.sugerir(rk, pl["aporte_mensal"], cart)
    if compras.empty:
        st.warning("Hoje nenhuma ação está com preço bom (sinal Comprar/Acumular). Guarde o dinheiro na renda fixa "
                   "(Tesouro Selic ou CDB de liquidez diária) e aporte quando aparecer oportunidade — o sistema avisa.")
    else:
        info_rk = rk.set_index("ticker")
        tab = pd.DataFrame([{
            "Ação": f"{COR_SINAL.get(r['sinal'], '')} {r['ticker']}",
            "Comprar": f"{int(r['comprar_qtd'])} cota(s)",
            "Preço hoje": brl(r["preco"]),
            "Total": brl(r["valor"]),
            "Renda por ano": brl(r["renda_anual_estimada"]),
            "Dados": COR_CONF.get(info_rk.at[r["ticker"], "confianca"], "—"),
            "Por que": info_rk.at[r["ticker"], "por_que"],
            "Conferir": info_rk.at[r["ticker"], "conferir"],
        } for _, r in compras.iterrows()])
        st.dataframe(tab.drop(columns=["Por que"]), hide_index=True, width="stretch",
                     column_config={"Conferir": st.column_config.LinkColumn("Conferir", display_text="Status Invest ↗")})
        with st.expander("📖 Por que cada uma foi escolhida", expanded=True):
            st.markdown("\n".join(f"- **{r['Ação']}** — {r['Por que']}" for _, r in tab.iterrows()))
        k = st.columns(3)
        k[0].metric("Total a investir", brl(compras["valor"].sum()))
        k[1].metric("Sobra (fica para o mês que vem)", brl(sobra))
        k[2].metric("Renda extra por ano com esta compra", brl(compras["renda_anual_estimada"].sum()))
        st.caption("Compre no **mercado fracionário** (código com F no final, ex.: TAEE11F) para comprar 1 cota de cada vez. "
                   "Antes de comprar, clique em *Status Invest ↗* e confira o preço e os proventos.")

    st.divider()
    st.subheader(f"🎯 Sua meta: {brl(pl['meta'], 0)}")
    sim = meta.simular(pl["meta"], pat_hoje, pl["aporte_mensal"], cart_esp["retorno"], cart_esp["volatilidade"],
                       pl["aumento_aporte_aa"], mac["ipca_12m"] if pl["corrigir_inflacao"] else 0.0)
    m = st.columns(3)
    m[0].metric("Você tem hoje", brl(pat_hoje, 0))
    m[1].metric("Chega lá em (metade das simulações)", meta.fmt_tempo(sim["meses_50"]))
    m[2].metric("Com 90% de chance, até", meta.fmt_tempo(sim["meses_90"]))
    rf = meta.meses_ate(pl["meta"], pat_hoje, pl["aporte_mensal"], mac["cdi_liquido"], pl["aumento_aporte_aa"],
                        mac["ipca_12m"] if pl["corrigir_inflacao"] else 0.0)
    if rf is not None and sim["meses_50"] is not None and rf <= sim["meses_50"]:
        st.info(f"💡 **Comparação honesta:** com a Selic em {pct(mac['selic'], 2)}, a renda fixa (≈ {pct(mac['cdi_liquido'])} a.a. "
                f"já descontado o IR) chegaria em {meta.fmt_tempo(rf)}, sem oscilação — tão rápido quanto ou mais que a carteira "
                f"de ações esperada ({pct(cart_esp['retorno'])} a.a.). Ações compensam no longo prazo quando os juros caem; "
                "muitos investidores dividem entre as duas. Veja a aba 🎯.")
    st.caption("Ajuste aporte, meta e o que você já tem na aba 🎯 Rumo ao R$ 1 milhão.")

    st.divider()
    st.subheader("🔔 O mais importante de hoje")
    imp = [a for a in R["alertas"] if a["nivel"] == 1]
    if not imp:
        st.success("Nada urgente hoje.")
    for a in imp[:8]:
        st.warning(f"**{a['tipo']}** — {a['texto']}")
    if len(imp) > 8:
        st.caption(f"+ {len(imp) - 8} alertas na aba 🔔 Alertas.")

# ======================================================================= META
with abas[1]:
    st.subheader("🎯 Quanto tempo até a sua meta — e o que te leva mais rápido")
    st.caption("O sistema simula 5.000 futuros possíveis para a bolsa (anos bons e ruins, na proporção do passado) "
               "e mostra a CHANCE de você chegar até cada ano. Ninguém consegue prometer uma data exata.")
    c = st.columns(3)
    pl["meta"] = c[0].number_input("Meta (R$)", 10_000.0, 100_000_000.0, float(pl["meta"]), 50_000.0, format="%.0f")
    pl["aporte_mensal"] = c[1].number_input("Aporte por mês (R$)", 0.0, 1_000_000.0, float(pl["aporte_mensal"]), 100.0, format="%.0f")
    pl["aumento_aporte_aa"] = c[2].number_input("Aumento do aporte por ano (%)", 0.0, 50.0,
                                                float(pl["aumento_aporte_aa"]) * 100, 1.0) / 100
    c = st.columns(3)
    pl["patrimonio_fora_bolsa"] = c[0].number_input("Já tenho fora da bolsa (renda fixa, poupança) R$", 0.0, 1e9,
                                                    float(pl["patrimonio_fora_bolsa"]), 1000.0, format="%.0f")
    ret = c[1].number_input("Rentabilidade esperada (% a.a.)", -5.0, 40.0, round(cart_esp["retorno"] * 100, 1), 0.5,
                            help="Sugestão: proventos previstos + tendência de preço da carteira-alvo de hoje (dividendos reinvestidos).") / 100
    vol = c[2].number_input("Oscilação da carteira (% a.a.)", 1.0, 80.0, round(cart_esp["volatilidade"] * 100, 1), 1.0,
                            help="Quanto a carteira sobe e desce num ano típico (volatilidade histórica, já considerando a diversificação).") / 100
    pl["corrigir_inflacao"] = st.checkbox(f"Quero {brl(pl['meta'], 0)} com o poder de compra de HOJE (corrige a meta pela inflação de "
                                          f"{pct(mac['ipca_12m'])} ao ano)", value=bool(pl["corrigir_inflacao"]))
    if st.button("💾 Salvar meu plano"):
        plano.salvar(pl)
        st.success("Plano salvo. A apuração diária e o alerta passam a usar estes valores.")
    pat_hoje = plano.patrimonio_atual(pl, cart, rk)
    infl = mac["ipca_12m"] if pl["corrigir_inflacao"] else 0.0

    sim = meta.simular(pl["meta"], pat_hoje, pl["aporte_mensal"], ret, vol, pl["aumento_aporte_aa"], infl)
    st.markdown(f"**Patrimônio hoje: {brl(pat_hoje, 0)}** (carteira de ações da aba 💼 pelos preços de hoje + o que você tem fora da bolsa). "
                f"Tempo até {brl(pl['meta'], 0)}:")
    k = st.columns(3)
    k[0].metric("🍀 Com anos bons", meta.fmt_tempo(sim["meses_10"]), help="Só 10% das simulações chegam antes disso.")
    k[1].metric("🎯 Mais provável", meta.fmt_tempo(sim["meses_50"]), help="Metade das simulações chega até aqui.")
    k[2].metric("🌧️ Com anos ruins", meta.fmt_tempo(sim["meses_90"]), help="9 em cada 10 simulações chegam até aqui.")

    f = sim["faixas"].copy()
    lim = min(40, max(10, int(((sim["meses_90"] or 480) / 12) + 3)))
    f = f[f["ano"] <= lim]
    rf_ret = mac["cdi_liquido"]
    f["renda fixa"] = [pat_hoje * (1 + rf_ret) ** a + sum(pl["aporte_mensal"] * (1 + pl["aumento_aporte_aa"]) ** (mm // 12)
                       * (1 + rf_ret) ** ((a * 12 - mm - 1) / 12) for mm in range(a * 12)) for a in f["ano"]]
    base = alt.Chart(f).encode(x=alt.X("ano:Q", title="Anos a partir de hoje"))
    faixa = base.mark_area(opacity=0.18, color="#4c78a8").encode(
        y=alt.Y("pessimista:Q", title="Patrimônio (R$)", axis=alt.Axis(format="~s")), y2="otimista:Q")
    longo = f.melt(id_vars="ano", value_vars=["mediana", "renda fixa", "meta", "investido"], var_name="linha", value_name="valor")
    nomes_l = {"mediana": "Ações — mais provável", "renda fixa": f"Renda fixa líquida ({pct(rf_ret)} a.a.)",
               "meta": "Meta", "investido": "Só o que você aportou"}
    longo["linha"] = longo["linha"].map(nomes_l)
    linhas = alt.Chart(longo).mark_line(strokeWidth=2.5).encode(
        x="ano:Q", y="valor:Q",
        color=alt.Color("linha:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=300),
                        scale=alt.Scale(domain=list(nomes_l.values()), range=["#1f77b4", "#ff7f0e", "#d62728", "#9d9d9d"])),
        strokeDash=alt.condition(alt.datum.linha == "Meta", alt.value([6, 4]), alt.value([0])),
        tooltip=["ano", "linha", alt.Tooltip("valor:Q", format=",.0f")])
    st.altair_chart(faixa + linhas, width="stretch")
    st.caption("Faixa azul: entre o cenário ruim e o bom (80% das simulações caem aí). Valores nominais"
               + (", com a meta corrigida pela inflação." if infl else " (sem descontar inflação)."))

    c1, c2 = st.columns(2)
    with c1:
        st.markdown("**🚀 O que te leva mais rápido**")
        alv = meta.alavancas(pl["meta"], pat_hoje, pl["aporte_mensal"], ret, pl["aumento_aporte_aa"], infl)
        alv["Tempo até a meta"] = alv["meses"].map(meta.fmt_tempo)
        alv["Ganho"] = alv["diferenca_meses"].map(lambda d: "—" if d is None or d != d or d == 0 else
                                                  (f"{meta.fmt_tempo(int(-d))} mais rápido" if d < 0 else f"{meta.fmt_tempo(int(d))} mais devagar"))
        st.dataframe(alv[["cenario", "Tempo até a meta", "Ganho"]].rename(columns={"cenario": "Se você..."}),
                     hide_index=True, width="stretch")
        st.caption("O aporte é a alavanca que você controla. Buscar rentabilidade alta demais costuma aumentar o risco de perder.")
    with c2:
        st.markdown("**📆 Quanto aportar para chegar em X anos**")
        anos_q = st.slider("Quero chegar em (anos)", 3, 35, 15)
        need = meta.aporte_necessario(pl["meta"], pat_hoje, ret, anos_q * 12, pl["aumento_aporte_aa"], infl)
        need_rf = meta.aporte_necessario(pl["meta"], pat_hoje, rf_ret, anos_q * 12, pl["aumento_aporte_aa"], infl)
        st.metric(f"Aporte mensal em ações ({pct(ret)} a.a.)", brl(need, 0))
        st.metric(f"Aporte mensal em renda fixa ({pct(rf_ret)} a.a. líquido)", brl(need_rf, 0))
        st.caption(f"Valores do 1º ano, subindo {pct(pl['aumento_aporte_aa'], 0)} ao ano. Caminho médio, sem oscilação.")

    st.markdown("**🎲 Chance de já ter atingido a meta até cada ano**")
    ch = sim["faixas"][sim["faixas"]["ano"].isin([5, 10, 15, 20, 25, 30])][["ano", "chance_ate_ano", "mediana", "pessimista"]]
    st.dataframe(pd.DataFrame({"Em": ch["ano"].map(lambda a: f"{a} anos"),
                               "Chance de já ter chegado": ch["chance_ate_ano"].map(lambda x: pct(x, 0)),
                               "Patrimônio mais provável": ch["mediana"].map(lambda x: brl(x, 0)),
                               "Cenário ruim": ch["pessimista"].map(lambda x: brl(x, 0))}),
                 hide_index=True, width="stretch")

# ======================================================================= RANKING
with abas[2]:
    st.caption("Todas as ações acompanhadas, da melhor para a pior para quem quer **renda + patrimônio no longo prazo**. "
               "Passe o mouse no título de cada coluna para ver o que significa.")
    f1, f2, f3 = st.columns([2, 2, 1])
    setores = f1.multiselect("Setor", sorted(rk["setor"].unique()))
    sinais = f2.multiselect("Sinal", ["Comprar", "Acumular", "Aguardar", "Evitar"], default=["Comprar", "Acumular"])
    dy_min = f3.number_input("Proventos mín. (% a.a.)", 0.0, 30.0, 0.0, 0.5) / 100
    v = rk.copy()
    if setores:
        v = v[v["setor"].isin(setores)]
    if sinais:
        v = v[v["sinal"].isin(sinais)]
    v = v[v["dy_medio_5a"].fillna(0) >= dy_min]
    v["sinal"] = v["sinal"].map(lambda s: f"{COR_SINAL.get(s, '')} {s}")
    v["confianca"] = v["confianca"].map(lambda c: COR_CONF.get(c, c))
    for c in ["dy_12m", "dy_medio_5a", "dy_previsto", "margem_bazin", "cresc_proventos_5a", "roe", "var_12m", "retorno_total_esperado_aa"]:
        v[c] = (v[c] * 100).round(1)
    for c in ["preco", "preco_teto_bazin", "preco_justo_graham", "proventos_previstos_12m"]:
        v[c] = v[c].round(2)
    cols = ["posicao", "ticker", "nome", "sinal", "nota", "confianca", "preco", "preco_teto_bazin", "margem_bazin",
            "dy_medio_5a", "dy_previsto", "proventos_previstos_12m", "retorno_total_esperado_aa", "anos_pagou_10",
            "cresc_proventos_5a", "roe", "pl", "pvp", "var_12m", "meses_provaveis", "setor", "conferir"]
    st.dataframe(v[[c for c in cols if c in v]], hide_index=True, width="stretch", height=600, column_config={
        "posicao": st.column_config.NumberColumn("#", width="small"),
        "ticker": "Ação", "nome": "Empresa", "sinal": "Sinal", "setor": "Setor",
        "nota": st.column_config.ProgressColumn("Nota (0–100)", min_value=0, max_value=100, format="%.0f"),
        "confianca": st.column_config.TextColumn("Dados", help="Alta = dados conferidos e coerentes. Média/Baixa = veja os avisos na aba Empresa."),
        "preco": col_rs("Preço hoje"),
        "preco_teto_bazin": col_rs("Preço-teto", "Preço máximo para que os proventos médios rendam pelo menos 6% ao ano (método Bazin)."),
        "margem_bazin": col_pct("Abaixo do teto", "Positivo = está barata (abaixo do preço-teto). Negativo = está acima."),
        "dy_medio_5a": col_pct("Proventos/ano (média 5a)", "Quanto a empresa pagou por ano, em média, nos últimos 5 anos, dividido pelo preço de hoje."),
        "dy_previsto": col_pct("Proventos previstos 12m"),
        "proventos_previstos_12m": col_rs("Previsto por ação 12m"),
        "retorno_total_esperado_aa": col_pct("Retorno esperado/ano", "Proventos previstos + tendência de preço (estimativa)."),
        "anos_pagou_10": st.column_config.NumberColumn("Anos pagando (de 10)"),
        "cresc_proventos_5a": col_pct("Crescimento proventos/ano"),
        "roe": col_pct("ROE", "Lucro do ano dividido pelo patrimônio: quanto a empresa rende sobre o próprio capital."),
        "pl": st.column_config.NumberColumn("P/L", format="%.1f", help="Preço ÷ lucro por ação: anos de lucro para 'pagar' a ação."),
        "pvp": st.column_config.NumberColumn("P/VP", format="%.2f", help="Preço ÷ patrimônio por ação."),
        "var_12m": col_pct("Variação 12m"),
        "meses_provaveis": "Meses em que costuma pagar",
        "conferir": st.column_config.LinkColumn("Conferir", display_text="Status Invest ↗"),
    })
    st.caption("🟢 **Comprar**: nota ≥ 65, preço abaixo do teto e dados confiáveis · 🟡 **Acumular**: nota ≥ 55 e até 10% acima do teto · "
               "🟠 **Aguardar**: boa, mas cara ou paga menos de 4% ao ano · 🔴 **Evitar**: nota baixa ou prejuízo.")
    if R.get("sem_dados"):
        st.caption(f"Sem dados nesta apuração (código pode ter mudado na B3): {', '.join(R['sem_dados'])}")

# ======================================================================= EMPRESA
with abas[3]:
    nomes = rk.set_index("ticker")["nome"]
    t = st.selectbox("Escolha a empresa", rk["ticker"], format_func=lambda x: f"{x} — {nomes[x]}")
    r = rk.set_index("ticker").loc[t]
    info = R["info"].get(t, {})
    precos: pd.Series = R["precos"][t]
    prov: pd.Series = R["proventos"][t]
    st.subheader(f"{COR_SINAL.get(r['sinal'], '')} {t} — {r['nome']}")
    st.markdown(f"**Veredito: {r['sinal'].upper()}** (nota {r['nota']:.0f}/100, {int(r['posicao'])}º de {len(rk)}). {r['por_que']}")
    links = [f"[Status Invest ↗]({r['conferir']})"] + ([f"[Site da empresa ↗]({info['website']})"] if info.get("website") else [])
    st.caption(f"{r['setor']} · cotação de {pd.Timestamp(r['data_cotacao']):%d/%m/%Y} · " + " · ".join(links))
    if r.get("avisos_dados"):
        st.warning(f"**Confiança dos dados: {r['confianca']}** — {r['avisos_dados']}. Confira no Status Invest antes de comprar.")
    m = st.columns(6)
    m[0].metric("Preço hoje", brl(r["preco"]), pct(r["var_dia"]) + " no dia" if r["var_dia"] == r["var_dia"] else None)
    m[1].metric("Preço-teto", brl(r["preco_teto_bazin"]),
                (f"{pct(r['margem_bazin'])} abaixo" if r["margem_bazin"] >= 0 else f"{pct(-r['margem_bazin'])} acima")
                if r["margem_bazin"] == r["margem_bazin"] else None,
                delta_color="normal" if r["margem_bazin"] == r["margem_bazin"] and r["margem_bazin"] >= 0 else "inverse")
    m[2].metric("Pagou (12 meses)", brl(r["proventos_12m"]), help="Proventos pagos por ação nos últimos 12 meses.")
    m[3].metric("Previsto (12 meses)", brl(r.get("proventos_previstos_12m")), help="Previsão de proventos por ação nos próximos 12 meses.")
    m[4].metric("Rende ao ano", pct(r.get("dy_previsto")), help="Proventos previstos ÷ preço de hoje.")
    m[5].metric("100 ações rendem", brl(r.get("proventos_previstos_12m", 0) * 100, 0), help="Por ano, pela previsão.")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Cotação (5 anos) × preço-teto**")
        p5 = precos[precos.index > precos.index.max() - pd.DateOffset(years=5)].reset_index()
        p5.columns = ["data", "preco"]
        camadas = [alt.Chart(p5).mark_line().encode(x=alt.X("data:T", title=None, axis=alt.Axis(format="%m/%Y")), y=alt.Y("preco:Q", title="R$", scale=alt.Scale(zero=False)),
                                                      tooltip=[alt.Tooltip("data:T", format="%d/%m/%Y"), alt.Tooltip("preco:Q", format=".2f")])]
        if r["preco_teto_bazin"] == r["preco_teto_bazin"]:
            camadas.append(alt.Chart(pd.DataFrame({"y": [r["preco_teto_bazin"]]})).mark_rule(color="green", strokeDash=[6, 4]).encode(y="y:Q"))
        st.altair_chart(alt.layer(*camadas), width="stretch")
        st.caption("Linha verde: preço-teto. Abaixo dela = boa hora para comprar pensando em renda.")
    with g2:
        st.markdown("**Proventos pagos por ação, ano a ano (dividendos + JCP)**")
        if prov.empty:
            st.info("Sem proventos registrados.")
        else:
            anual = prov.groupby(prov.index.year).sum().rename_axis("ano").reset_index(name="valor")
            anual["ano"] = anual["ano"].astype(str)
            anual.loc[anual.index[-1], "ano"] += " (parcial)" if int(anual["ano"].iloc[-1][:4]) == R["data"].year else ""
            st.altair_chart(alt.Chart(anual).mark_bar().encode(
                x=alt.X("ano:N", title=None), y=alt.Y("valor:Q", title="R$ por ação"),
                tooltip=["ano", alt.Tooltip("valor:Q", format=".2f", title="R$ por ação")]), width="stretch")
            st.caption(f"Costuma pagar em: **{r.get('meses_provaveis', '—')}**. "
                       f"Próxima data-ex informada: **{pd.Timestamp(r['ex_dividendo']):%d/%m/%Y}**." if r['ex_dividendo'] else "Próxima data-ex: não informada.")

    st.markdown("**🔮 Previsão (estatística, não é garantia)**")
    pv = pd.DataFrame([{"Daqui a": f"{a} ano{'s' if a > 1 else ''}",
                        "Cenário ruim": brl(r.get(f"preco_{a}a_pessimista")), "Mais provável": brl(r.get(f"preco_{a}a_mediana")),
                        "Cenário bom": brl(r.get(f"preco_{a}a_otimista"))} for a in (1, 3, 5)])
    p1, p2 = st.columns([3, 2])
    p1.dataframe(pv, hide_index=True, width="stretch")
    p2.markdown(f"- Proventos esperados: **{pct(r.get('dy_previsto'))} ao ano**\n"
                f"- Valorização esperada: **{pct(r.get('tendencia_preco_aa'))} ao ano**\n"
                f"- Retorno total esperado: **{pct(r.get('retorno_total_esperado_aa'))} ao ano**\n"
                f"- Maior queda nos últimos 5 anos: {pct(r['queda_max_5a'])}\n"
                f"- Analistas: preço-alvo {brl(r['alvo_analistas'])}" + (f" ({pct(r['potencial_analistas'])})" if r['potencial_analistas'] == r['potencial_analistas'] else ""))
    st.caption("80% de chance de o preço ficar entre o cenário ruim e o bom, segundo o comportamento passado da ação.")

    st.markdown("**📋 Saúde da empresa**")
    ind = pd.DataFrame([
        ("Lucro sobre o patrimônio (ROE)", pct(r["roe"]), "acima de 15% é bom"),
        ("Margem de lucro", pct(r["margem_liquida"]), "quanto sobra de cada R$ 100 vendidos"),
        ("Dívida ÷ patrimônio", f"{r['divida_pl']:.2f}".replace(".", ",") if r["divida_pl"] == r["divida_pl"] else "—", "abaixo de 1 é confortável (não vale para bancos)"),
        ("Parte do lucro paga aos sócios (payout)", pct(r["payout"]), "entre 25% e 90% é sustentável"),
        ("P/L (anos de lucro no preço)", f"{r['pl']:.1f}".replace(".", ",") if r["pl"] == r["pl"] else "—", "abaixo de 10 é barato"),
        ("P/VP", f"{r['pvp']:.2f}".replace(".", ",") if r["pvp"] == r["pvp"] else "—", "perto de 1 = preço ≈ patrimônio"),
        ("Anos pagando proventos (de 10)", str(int(r["anos_pagou_10"])), "quanto mais, mais confiável"),
        ("Crescimento dos proventos por ano", pct(r["cresc_proventos_5a"]), "positivo = renda crescendo"),
    ], columns=["Indicador", "Valor", "Como ler"])
    st.dataframe(ind, hide_index=True, width="stretch")
    n = st.columns(4)
    for col, kk, nome in zip(n, ["renda", "qualidade", "preco", "risco"], ["Renda", "Qualidade", "Preço", "Risco (baixo = bom)"]):
        col.progress(min(1.0, r[f"nota_{kk}"] / 100), text=f"{nome}: {r[f'nota_{kk}']:.0f}/100")

    st.markdown("**📰 Notícias dos últimos 30 dias**")
    itens = R["noticias"].get(t, [])
    if not itens:
        st.caption("Sem notícias coletadas (buscamos para as 30 primeiras do ranking e para as da sua carteira).")
    for x in itens:
        tom = {"positiva": "🟢", "negativa": "🔴"}.get(x["tom"], "⚪")
        quando = f"{x['quando']:%d/%m %H:%M}" if x["quando"] else ""
        titulo = f"[{x['titulo']}]({x['link']})" if x["link"] else x["titulo"]
        st.markdown(f"{tom} {titulo}  \n<span style='color:#8a8f98;font-size:12px'>{x['fonte']} · {quando} · "
                    f"{', '.join(x['assuntos'])}</span>", unsafe_allow_html=True)
    if info.get("longBusinessSummary"):
        with st.expander("O que a empresa faz"):
            st.write(info["longBusinessSummary"])
    with st.expander("Todos os proventos pagos"):
        st.dataframe(pd.DataFrame({"Data-ex": prov.index.strftime("%d/%m/%Y"), "R$ por ação": prov.round(4).values})[::-1],
                     hide_index=True, width="stretch")

# ======================================================================= CARTEIRA
with abas[4]:
    st.markdown("**Minha carteira** — digite as ações que você já tem e clique em Salvar. "
                "O aporte do mês passa a completar o que está abaixo do alvo, e os alertas acompanham as suas ações.")
    base_cart = cart if not cart.empty else pd.DataFrame({"ticker": pd.Series(dtype=str), "quantidade": pd.Series(dtype=float),
                                                          "preco_medio": pd.Series(dtype=float)})
    ed = st.data_editor(base_cart, num_rows="dynamic", hide_index=True, width="stretch", key="cart",
                        column_config={"ticker": "Ação (ex.: TAEE11)", "quantidade": "Quantidade",
                                       "preco_medio": st.column_config.NumberColumn("Preço médio pago (R$)", format=NUM)})
    if st.button("💾 Salvar carteira"):
        ed = ed.dropna(subset=["ticker"])
        ed["ticker"] = ed["ticker"].str.upper().str.strip()
        ed.to_csv(aporte.ARQ_CARTEIRA, index=False)
        st.success("Carteira salva.")
        st.rerun()
    rev = aporte.revisar_carteira(rk, cart)
    if not rev.empty:
        k = st.columns(3)
        k[0].metric("Valor hoje", brl(rev["valor_atual"].sum()))
        custo = (rev["quantidade"] * rev["preco_medio"]).sum()
        k[1].metric("Resultado", brl(rev["valor_atual"].sum() - custo),
                    pct(rev["valor_atual"].sum() / custo - 1) if custo else None)
        k[2].metric("Renda de proventos estimada", brl(rev["renda_anual_estimada"].sum()) + "/ano")
        st.dataframe(pd.DataFrame({
            "Ação": rev["ticker"], "Qtd": rev["quantidade"], "Preço médio": rev["preco_medio"].map(brl),
            "Preço hoje": rev["preco"].map(brl), "Valor hoje": rev["valor_atual"].map(brl),
            "Resultado": rev["resultado"].map(pct), "Sinal hoje": rev["sinal"].map(lambda s: f"{COR_SINAL.get(s, '')} {s}"),
            "Renda/ano": rev["renda_anual_estimada"].map(brl)}), hide_index=True, width="stretch")
        st.caption("'Evitar' numa ação que você já tem não é ordem de venda: é um sinal para olhar as notícias e os resultados.")

# ======================================================================= BACKTEST
with abas[5]:
    bt = R.get("backtest")
    st.subheader("🧪 E se você tivesse seguido o sistema nos últimos 5 anos?")
    if not bt:
        st.info("O teste no passado roda junto com a apuração. Clique em Apurar agora.")
    else:
        st.caption(f"Simulação: {brl(bt['investido'] / bt['meses'], 0)} por mês, de {bt['serie']['data'].iloc[0]:%m/%Y} até hoje, "
                   "comprando todo mês as ações que o sistema escolheria NAQUELA data (só com o que se sabia então) "
                   "e reinvestindo os proventos.")
        k = st.columns(4)
        k[0].metric("Total aportado", brl(bt["investido"], 0))
        k[1].metric("Seguindo o sistema", brl(bt["sistema"], 0), pct(bt["tir_sistema"]) + " ao ano")
        k[2].metric("No CDI (bruto)", brl(bt["cdi"], 0), pct(bt["tir_cdi"]) + " ao ano", delta_color="off")
        k[3].metric("No Ibovespa (BOVA11)", brl(bt["ibovespa"], 0) if bt["ibovespa"] == bt["ibovespa"] else "—",
                    pct(bt["tir_ibovespa"]) + " ao ano" if bt["tir_ibovespa"] == bt["tir_ibovespa"] else None, delta_color="off")
        s = bt["serie"].melt(id_vars="data", value_vars=["sistema", "cdi", "ibovespa", "investido"], var_name="linha", value_name="valor").dropna()
        nomes_b = {"sistema": "Seguindo o sistema", "cdi": "CDI", "ibovespa": "Ibovespa", "investido": "Só o aportado"}
        s["linha"] = s["linha"].map(nomes_b)
        st.altair_chart(alt.Chart(s).mark_line(strokeWidth=2.5).encode(
            x=alt.X("data:T", title=None, axis=alt.Axis(format="%m/%Y")), y=alt.Y("valor:Q", title="R$", axis=alt.Axis(format="~s")),
            color=alt.Color("linha:N", title=None, legend=alt.Legend(orient="bottom"),
                            scale=alt.Scale(domain=list(nomes_b.values()), range=["#2ca02c", "#ff7f0e", "#1f77b4", "#9d9d9d"])),
            tooltip=[alt.Tooltip("data:T", format="%m/%Y"), "linha", alt.Tooltip("valor:Q", format=",.0f")]), width="stretch")
        st.metric("Proventos que essa carteira pagou nos últimos 12 meses", brl(bt["proventos_12m"]))
        if not bt.get("cdi_real", True):
            st.caption("⚠️ CDI estimado (10% a.a.): o Banco Central não respondeu nesta apuração.")
        st.warning("**Limites deste teste (leia):** (1) testa só a parte de proventos e preço — os dados de balanço do Yahoo são só os de hoje; "
                   "(2) usa as empresas que existem hoje, o que deixa o resultado um pouco melhor que a realidade; "
                   "(3) não desconta corretagem nem IR; (4) resultado passado não garante resultado futuro. "
                   "Serve para mostrar se o MÉTODO fez sentido, não para prometer retorno.")
        with st.expander("O que o sistema teria comprado em cada mês"):
            st.dataframe(bt["compras"].iloc[::-1], hide_index=True, width="stretch")

# ======================================================================= ALERTAS
with abas[6]:
    if not R["alertas"]:
        st.success("Nenhum alerta hoje.")
    icones = {"Oportunidade": "🟢", "Queda forte": "📉", "Provento": "💰", "Data-com": "📅", "Ranking": "🏆",
              "Carteira": "⚠️", "Notícia": "📰"}
    tipos = sorted({a["tipo"] for a in R["alertas"]})
    escolha = st.multiselect("Tipos", tipos, default=tipos)
    for a in R["alertas"]:
        if a["tipo"] in escolha:
            (st.warning if a["nivel"] == 1 else st.info)(f"{icones.get(a['tipo'], '•')} **{a['tipo']}** — {a['texto']}")

# ======================================================================= COMO FUNCIONA
with abas[7]:
    st.markdown("""
### De onde vêm os dados (todos reais e atualizados a cada apuração)
- **Cotações, proventos (dividendos + JCP) e balanço**: Yahoo Finance. A data da última cotação aparece no topo.
- **Selic, IPCA e CDI**: Banco Central do Brasil (oficial).
- **Notícias**: Google Notícias, últimos 30 dias.
- Cada ação passa por uma **checagem de confiança**: cotação velha, preço divergente entre fontes, provento fora do normal,
  dado faltando. Ação com dado duvidoso **nunca recebe "Comprar"**. Use o link *Status Invest ↗* para conferir.

### Como a nota é feita (0 a 100)
- **Renda (40%)**: quanto paga por ano em relação ao preço (média de 5 anos), há quantos anos paga, se os proventos crescem e se são estáveis.
- **Qualidade (30%)**: ROE, margem de lucro, dívida, se o lucro sustenta os proventos, se dá lucro.
- **Preço (20%)**: distância até o preço-teto (Bazin) e o preço justo (Graham), P/L e P/VP.
- **Risco (10%)**: quanto oscila e qual foi a maior queda. Notícias mexem no máximo 3 pontos.

### Como o aporte do mês é dividido
As 10 melhores com sinal Comprar/Acumular, no máximo 2 por setor. O dinheiro vai primeiro para as que estão
mais abaixo do peso ideal na sua carteira e mais baratas em relação ao preço-teto. Sempre cotas inteiras.

### O que NENHUM sistema consegue fazer — leia antes de investir
- **Ninguém prevê o preço de amanhã.** O que dá para fazer é escolher boas empresas, pagar um preço justo, diversificar e
  aportar todo mês por muitos anos. É isso que este sistema organiza para você.
- **O caminho até R$ 1 milhão depende principalmente de quanto você aporta e por quanto tempo.** A rentabilidade ajuda,
  mas quem promete muito retorno rápido está te vendendo risco (ou golpe).
- **Tenha uma reserva de emergência** (6 meses de gastos, em renda fixa de liquidez diária) antes de colocar dinheiro em ações.
- **Ações oscilam**: haverá anos de queda de 20–40%. Quem vende no pânico transforma oscilação em prejuízo.
- **Diversifique**: nunca coloque tudo numa ação só. O sistema limita 2 por setor por isso.
- **Impostos**: dividendos são isentos para a maioria das pessoas; JCP tem 15% retido na fonte; vendas acima de
  R$ 20 mil/mês com lucro pagam 15% de IR. Confira as regras vigentes.
- Use o sistema como um **assistente que faz a lição de casa todo dia**, não como garantia. Na dúvida, um planejador
  financeiro certificado (CFP) pode revisar seu plano.
""")
    st.warning(AVISO)
