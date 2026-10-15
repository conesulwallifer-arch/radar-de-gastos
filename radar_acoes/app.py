"""Painel do Radar de Ações:  streamlit run radar_acoes/app.py"""
from __future__ import annotations

import os
import pickle
import sys
from datetime import date

import altair as alt
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acoes import AVISO, DADOS, aporte, previsao  # noqa: E402
from apurar import ULTIMO, apurar  # noqa: E402
from acoes import universo  # noqa: E402

st.set_page_config(page_title="Radar de Ações", page_icon="📈", layout="wide")

PCT = st.column_config.NumberColumn(format="percent")
BRL = st.column_config.NumberColumn(format="R$ %.2f")
COR_SINAL = {"Comprar": "🟢", "Acumular": "🟡", "Aguardar": "🟠", "Evitar": "🔴"}


def brl(x) -> str:
    return "—" if x is None or x != x else f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(x) -> str:
    return "—" if x is None or x != x else f"{x*100:.1f}%".replace(".", ",")


@st.cache_data(show_spinner=False)
def carregar(_marca: float) -> dict | None:
    if not ULTIMO.exists():
        return None
    with open(ULTIMO, "rb") as f:
        return pickle.load(f)


def rodar(demo: bool, valor: float):
    with st.spinner("Apurando: coletando cotações, proventos, indicadores e notícias (alguns minutos na 1ª vez)..."):
        apurar(universo.tickers(), valor, usar_demo=demo, enviar=False)
    st.cache_data.clear()
    st.rerun()


st.title("📈 Radar de Ações — renda passiva de longo prazo")
st.caption(AVISO)

with st.sidebar:
    st.header("Apuração")
    valor_padrao = float(os.getenv("APORTE_MENSAL", "1000") or 1000)
    if st.button("🔄 Apurar agora", width="stretch", type="primary"):
        rodar(False, valor_padrao)
    if st.button("🧪 Testar com dados fictícios", width="stretch"):
        rodar(True, valor_padrao)
    st.caption("A apuração diária automática roda pelo agendador (veja o README). "
               "Aqui você pode forçar uma nova a qualquer hora.")

R = carregar(ULTIMO.stat().st_mtime if ULTIMO.exists() else 0)
if R is None:
    st.info("Ainda não há apuração. Clique em **Apurar agora** na barra lateral (precisa de internet) "
            "ou em **Testar com dados fictícios**.")
    st.stop()

rk: pd.DataFrame = R["ranking"]
if R.get("demo"):
    st.error("⚠️ MODO DEMONSTRAÇÃO: os números abaixo são FICTÍCIOS. Clique em **Apurar agora** para usar dados reais.")

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Apurado em", f"{R['data']:%d/%m/%Y}")
c2.metric("Ações analisadas", len(rk))
c3.metric("🟢 Comprar", int((rk["sinal"] == "Comprar").sum()))
c4.metric("🟡 Acumular", int((rk["sinal"] == "Acumular").sum()))
c5.metric("🔔 Alertas importantes", sum(a["nivel"] == 1 for a in R["alertas"]))

abas = st.tabs(["🏆 Ranking", "🔔 Alertas", "🏢 Empresa", "🛒 Aporte do mês", "📊 Simulador", "❓ Como funciona"])

# ------------------------------------------------------------------ Ranking
with abas[0]:
    f1, f2, f3 = st.columns([2, 2, 1])
    setores = f1.multiselect("Setor", sorted(rk["setor"].unique()))
    sinais = f2.multiselect("Sinal", ["Comprar", "Acumular", "Aguardar", "Evitar"], default=["Comprar", "Acumular"])
    dy_min = f3.number_input("DY médio mín. (%)", 0.0, 30.0, 0.0, 0.5) / 100
    v = rk.copy()
    if setores:
        v = v[v["setor"].isin(setores)]
    if sinais:
        v = v[v["sinal"].isin(sinais)]
    v = v[v["dy_medio_5a"].fillna(0) >= dy_min]
    v["sinal"] = v["sinal"].map(lambda s: f"{COR_SINAL.get(s, '')} {s}")
    cols = ["posicao", "ticker", "nome", "setor", "sinal", "nota", "preco", "preco_teto_bazin", "margem_bazin",
            "preco_justo_graham", "dy_12m", "dy_medio_5a", "dy_previsto", "anos_pagou_10", "cresc_proventos_5a",
            "roe", "pl", "pvp", "divida_pl", "payout", "var_12m", "meses_provaveis",
            "nota_renda", "nota_qualidade", "nota_preco", "nota_risco"]
    st.dataframe(v[[c for c in cols if c in v]], hide_index=True, width="stretch", height=560,
                 column_config={
                     "posicao": st.column_config.NumberColumn("#", width="small"),
                     "nota": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%.0f"),
                     "preco": BRL, "preco_teto_bazin": st.column_config.NumberColumn("Preço-teto (Bazin)", format="R$ %.2f"),
                     "preco_justo_graham": st.column_config.NumberColumn("Preço justo (Graham)", format="R$ %.2f"),
                     "margem_bazin": st.column_config.NumberColumn("Margem até o teto", format="percent"),
                     "dy_12m": st.column_config.NumberColumn("DY 12m", format="percent"),
                     "dy_medio_5a": st.column_config.NumberColumn("DY médio 5a", format="percent"),
                     "dy_previsto": st.column_config.NumberColumn("DY previsto 12m", format="percent"),
                     "anos_pagou_10": st.column_config.NumberColumn("Anos pagando (10)"),
                     "cresc_proventos_5a": st.column_config.NumberColumn("Cresc. proventos a.a.", format="percent"),
                     "roe": PCT, "divida_pl": st.column_config.NumberColumn("Dív./PL", format="%.2f"),
                     "payout": PCT, "var_12m": st.column_config.NumberColumn("Var. 12m", format="percent"),
                     "pl": st.column_config.NumberColumn("P/L", format="%.1f"),
                     "pvp": st.column_config.NumberColumn("P/VP", format="%.2f"),
                     "meses_provaveis": "Meses que costuma pagar",
                 })
    st.caption("**Comprar**: nota ≥ 65 e preço abaixo do teto de Bazin (dividendo médio ÷ 6%). "
               "**Acumular**: nota ≥ 55 e até 10% acima do teto. **Aguardar**: boa empresa, mas cara ou com DY < 4%. "
               "**Evitar**: nota baixa ou prejuízo.")
    if R.get("sem_dados"):
        st.caption(f"Sem dados nesta apuração (o código pode ter mudado na B3): {', '.join(R['sem_dados'])}")

# ------------------------------------------------------------------ Alertas
with abas[1]:
    if not R["alertas"]:
        st.success("Nenhum alerta hoje.")
    icones = {"Oportunidade": "🟢", "Queda forte": "📉", "Provento": "💰", "Data-com": "📅", "Ranking": "🏆",
              "Carteira": "⚠️", "Notícia": "📰"}
    tipos = sorted({a["tipo"] for a in R["alertas"]})
    escolha = st.multiselect("Tipos", tipos, default=tipos)
    for a in R["alertas"]:
        if a["tipo"] in escolha:
            (st.warning if a["nivel"] == 1 else st.info)(f"{icones.get(a['tipo'], '•')} **{a['tipo']}** — {a['texto']}")

# ------------------------------------------------------------------ Empresa
with abas[2]:
    t = st.selectbox("Empresa", rk["ticker"], format_func=lambda x: f"{x} — {rk.set_index('ticker').at[x, 'nome']}")
    r = rk.set_index("ticker").loc[t]
    info = R["info"].get(t, {})
    precos: pd.Series = R["precos"][t]
    prov: pd.Series = R["proventos"][t]
    st.subheader(f"{COR_SINAL.get(r['sinal'], '')} {t} — {r['nome']}")
    st.caption(f"{r['setor']} · posição {int(r['posicao'])}º · sinal **{r['sinal']}**"
               + (f" · [site]({info['website']})" if info.get("website") else ""))
    m = st.columns(6)
    m[0].metric("Preço", brl(r["preco"]), pct(r["var_dia"]) if r["var_dia"] == r["var_dia"] else None)
    m[1].metric("Nota", f"{r['nota']:.0f}/100")
    m[2].metric("DY médio 5 anos", pct(r["dy_medio_5a"]))
    m[3].metric("Preço-teto (Bazin)", brl(r["preco_teto_bazin"]), pct(r["margem_bazin"]) + " de margem")
    m[4].metric("Preço justo (Graham)", brl(r["preco_justo_graham"]))
    m[5].metric("Proventos previstos 12m", brl(r.get("proventos_previstos_12m")), pct(r.get("dy_previsto")) + " DY")

    g1, g2 = st.columns(2)
    with g1:
        st.markdown("**Cotação (5 anos) e preço-teto**")
        p5 = precos[precos.index > precos.index.max() - pd.DateOffset(years=5)].rename("preco").reset_index()
        p5.columns = ["data", "preco"]
        linha = alt.Chart(p5).mark_line().encode(x="data:T", y=alt.Y("preco:Q", title="R$"))
        camadas = [linha]
        if r["preco_teto_bazin"] == r["preco_teto_bazin"]:
            camadas.append(alt.Chart(pd.DataFrame({"y": [r["preco_teto_bazin"]]})).mark_rule(color="green", strokeDash=[6, 4]).encode(y="y:Q"))
        st.altair_chart(alt.layer(*camadas), width="stretch")
        st.caption("Linha verde tracejada: preço-teto de Bazin. Abaixo dela, o dividendo médio rende ≥ 6% a.a.")
    with g2:
        st.markdown("**Proventos por ano (dividendos + JCP, por ação)**")
        if prov.empty:
            st.info("Sem proventos registrados.")
        else:
            anual = prov.groupby(prov.index.year).sum().rename_axis("ano").reset_index(name="valor")
            anual["ano"] = anual["ano"].astype(str)
            st.altair_chart(alt.Chart(anual).mark_bar().encode(x="ano:N", y=alt.Y("valor:Q", title="R$ por ação"),
                                                                tooltip=["ano", alt.Tooltip("valor:Q", format=".4f")]),
                            width="stretch")
            st.caption(f"Costuma pagar em: {r.get('meses_provaveis', '—')}. Ano corrente parcial. "
                       f"Próxima data-ex informada: {r['ex_dividendo'] or '—'}.")

    st.markdown("**🔮 Previsão**")
    pv = pd.DataFrame([{"Prazo": f"{a} ano{'s' if a > 1 else ''}",
                        "Pessimista (10%)": r.get(f"preco_{a}a_pessimista"), "Mediana": r.get(f"preco_{a}a_mediana"),
                        "Otimista (90%)": r.get(f"preco_{a}a_otimista")} for a in (1, 3, 5)])
    p1, p2 = st.columns([3, 2])
    p1.dataframe(pv, hide_index=True, width="stretch",
                 column_config={k: BRL for k in ["Pessimista (10%)", "Mediana", "Otimista (90%)"]})
    p2.markdown(f"- Tendência de preço estimada: **{pct(r.get('tendencia_preco_aa'))} a.a.**\n"
                f"- Proventos estimados: **{pct(r.get('dy_previsto'))} a.a.**\n"
                f"- Retorno total esperado: **{pct(r.get('retorno_total_esperado_aa'))} a.a.**\n"
                f"- Volatilidade: {pct(r.get('volatilidade_aa'))} a.a. · maior queda em 5 anos: {pct(r['queda_max_5a'])}\n"
                f"- Analistas (Yahoo): alvo {brl(r['alvo_analistas'])} ({pct(r['potencial_analistas'])}), "
                f"recomendação {r['recomendacao_analistas'] or '—'}")
    st.caption("Faixa com 80% de chance segundo o modelo estatístico (log-normal) — não é garantia.")

    st.markdown("**📋 Indicadores**")
    ind = {"P/L": f"{r['pl']:.1f}" if r["pl"] == r["pl"] else "—", "P/VP": f"{r['pvp']:.2f}" if r["pvp"] == r["pvp"] else "—",
           "ROE": pct(r["roe"]), "Margem líquida": pct(r["margem_liquida"]),
           "Dívida/Patrimônio": f"{r['divida_pl']:.2f}" if r["divida_pl"] == r["divida_pl"] else "—",
           "Payout": pct(r["payout"]), "LPA": brl(r["lpa"]), "VPA": brl(r["vpa"]),
           "Cresc. lucro": pct(r["cresc_lucro"]), "Anos pagando (de 10)": int(r["anos_pagou_10"]),
           "Cresc. proventos a.a. (5a)": pct(r["cresc_proventos_5a"]), "Var. 12 meses": pct(r["var_12m"])}
    st.dataframe(pd.DataFrame([ind]), hide_index=True, width="stretch")
    n = st.columns(4)
    for col, k in zip(n, ["renda", "qualidade", "preco", "risco"]):
        col.progress(min(1.0, r[f"nota_{k}"] / 100), text=f"{k.capitalize()}: {r[f'nota_{k}']:.0f}")

    st.markdown("**📰 Notícias (30 dias)**")
    itens = R["noticias"].get(t, [])
    if not itens:
        st.caption("Sem notícias coletadas (só buscamos para as 30 primeiras do ranking e as da sua carteira).")
    for x in itens:
        tom = {"positiva": "🟢", "negativa": "🔴"}.get(x["tom"], "⚪")
        quando = f"{x['quando']:%d/%m %H:%M}" if x["quando"] else ""
        titulo = f"[{x['titulo']}]({x['link']})" if x["link"] else x["titulo"]
        st.markdown(f"{tom} {titulo}  \n<span style='color:#8a8f98;font-size:12px'>{x['fonte']} · {quando} · "
                    f"{', '.join(x['assuntos'])}</span>", unsafe_allow_html=True)
    if info.get("longBusinessSummary"):
        with st.expander("Sobre a empresa"):
            st.write(info["longBusinessSummary"])
    with st.expander("Histórico de proventos"):
        st.dataframe(prov.sort_index(ascending=False).rename("R$ por ação").rename_axis("data-ex").reset_index(),
                     hide_index=True, width="stretch")

# ------------------------------------------------------------------ Aporte
with abas[3]:
    a1, a2, a3 = st.columns(3)
    valor = a1.number_input("Valor do aporte (R$)", 50.0, 1_000_000.0, float(R.get("aporte") or 1000.0), 50.0)
    n_at = a2.slider("Quantas ações na carteira-alvo", 3, 20, 10)
    max_s = a3.slider("Máximo de ações por setor", 1, 5, 2)
    st.markdown("**Minha carteira atual** (opcional — edite e salve; o aporte completa o que está abaixo do alvo)")
    cart = aporte.ler_carteira()
    if cart.empty:
        cart = pd.DataFrame({"ticker": pd.Series(dtype=str), "quantidade": pd.Series(dtype=float),
                             "preco_medio": pd.Series(dtype=float)})
    ed = st.data_editor(cart, num_rows="dynamic", hide_index=True, width="stretch", key="cart")
    if st.button("💾 Salvar carteira"):
        ed = ed.dropna(subset=["ticker"])
        ed["ticker"] = ed["ticker"].str.upper().str.strip()
        ed.to_csv(aporte.ARQ_CARTEIRA, index=False)
        st.success(f"Carteira salva em {aporte.ARQ_CARTEIRA}.")
    compras, sobra = aporte.sugerir(rk, valor, aporte.ler_carteira(), n_at, max_s)
    if compras.empty:
        st.warning("Nenhuma ação com sinal Comprar/Acumular cabe neste aporte hoje. Guarde o valor para o próximo mês.")
    else:
        st.dataframe(compras, hide_index=True, width="stretch",
                     column_config={"preco": BRL, "preco_teto": BRL, "valor": BRL, "renda_anual_estimada": BRL,
                                    "dy_medio_5a": PCT, "comprar_qtd": "Comprar (cotas)",
                                    "nota": st.column_config.NumberColumn(format="%.0f")})
        k1, k2, k3 = st.columns(3)
        k1.metric("Total a investir", brl(compras["valor"].sum()))
        k2.metric("Sobra para o próximo mês", brl(sobra))
        k3.metric("Renda anual estimada desta compra", brl(compras["renda_anual_estimada"].sum()))
        st.caption("Cotas inteiras no mercado fracionário (código com F, ex.: TAEE11F). "
                   "Prioriza as de maior nota, as mais abaixo do peso-alvo e as mais baratas em relação ao preço-teto.")
    rev = aporte.revisar_carteira(rk)
    if not rev.empty:
        st.markdown("**Situação da minha carteira**")
        st.dataframe(rev[["ticker", "quantidade", "preco_medio", "preco", "valor_atual", "resultado", "sinal", "nota",
                          "renda_anual_estimada"]], hide_index=True, width="stretch",
                     column_config={"preco_medio": BRL, "preco": BRL, "valor_atual": BRL, "resultado": PCT,
                                    "renda_anual_estimada": BRL})

# ------------------------------------------------------------------ Simulador
with abas[4]:
    alvo = aporte.escolher(rk, 10, 2)
    dy_sug = float(alvo["dy_previsto"].median()) if len(alvo) and "dy_previsto" in alvo else 0.07
    val_sug = float(alvo["tendencia_preco_aa"].median()) if len(alvo) and "tendencia_preco_aa" in alvo else 0.04
    s1, s2, s3 = st.columns(3)
    ap_m = s1.number_input("Aporte mensal (R$)", 0.0, 1_000_000.0, 1000.0, 100.0)
    anos = s2.slider("Anos", 1, 40, 20)
    ini = s3.number_input("Já investido (R$)", 0.0, 100_000_000.0, 0.0, 1000.0)
    s4, s5, s6 = st.columns(3)
    dy = s4.number_input("DY esperado (% a.a.)", 0.0, 20.0, round(dy_sug * 100, 1), 0.5) / 100
    val = s5.number_input("Valorização esperada (% a.a.)", -10.0, 20.0, round(val_sug * 100, 1), 0.5) / 100
    aum = s6.number_input("Aumento anual do aporte (%)", 0.0, 20.0, 5.0, 0.5) / 100
    meta = st.number_input("Meta de renda passiva mensal (R$)", 0.0, 1_000_000.0, 5000.0, 500.0)
    st.caption(f"Sugestões vindas da carteira-alvo de hoje: DY previsto {pct(dy_sug)} e tendência de preço {pct(val_sug)} a.a. "
               "Valores nominais (sem descontar inflação).")
    cen = previsao.cenarios(ap_m, anos, dy, val, inicial=ini, aumento_aporte_aa=aum)
    tab = pd.concat([d.assign(cenario=k) for k, d in cen.items()])
    graf = tab[tab["mes"] % 12 == 0]
    st.altair_chart(alt.Chart(graf).mark_line(point=True).encode(
        x=alt.X("ano:Q", title="Ano"), y=alt.Y("patrimonio:Q", title="Patrimônio (R$)"), color="cenario:N",
        tooltip=["cenario", "ano", alt.Tooltip("patrimonio:Q", format=",.0f"), alt.Tooltip("renda_mensal_estimada:Q", format=",.0f")]),
        width="stretch")
    b = cen["Base"].iloc[-1]
    q = st.columns(4)
    q[0].metric("Total aportado", brl(b["investido"]))
    q[1].metric(f"Patrimônio em {anos} anos (base)", brl(b["patrimonio"]))
    q[2].metric("Renda passiva mensal (base)", brl(b["renda_mensal_estimada"]))
    mes_meta = previsao.meta_renda(meta, dy, val, ap_m, ini)
    q[3].metric(f"Tempo até {brl(meta)}/mês", f"{mes_meta // 12} anos e {mes_meta % 12} meses" if mes_meta else "mais de 60 anos")
    anual = cen["Base"][cen["Base"]["mes"] % 12 == 0][["ano", "investido", "patrimonio", "proventos_acumulados", "renda_mensal_estimada"]]
    st.dataframe(anual, hide_index=True, width="stretch",
                 column_config={c: BRL for c in ["investido", "patrimonio", "proventos_acumulados", "renda_mensal_estimada"]})
    st.caption("Obs.: a meta usa aporte constante (sem o aumento anual). Pessimista: DY −25% e valorização −3 p.p.; "
               "otimista: DY +15% e valorização +2 p.p.")

# ------------------------------------------------------------------ Como funciona
with abas[5]:
    st.markdown("""
**Fontes**: cotações, proventos (dividendos + JCP, pela data-ex) e indicadores do Yahoo Finance; notícias do Google Notícias.

**Nota (0–100)** — pensada para quem investe todo mês para viver de renda:
- **Renda (40%)**: dividend yield médio de 5 anos, regularidade (anos pagando nos últimos 10), crescimento e estabilidade dos proventos.
  DY acima de 14% é penalizado (costuma ser pagamento extraordinário que não se repete).
- **Qualidade (30%)**: ROE, margem líquida, dívida/patrimônio (não vale para bancos e seguradoras), payout sustentável e lucro positivo.
- **Preço (20%)**: margem até o preço-teto de Bazin e o preço justo de Graham (√(22,5 × LPA × VPA)), P/L e P/VP.
- **Risco (10%)**: volatilidade e maior queda dos últimos 5 anos.
- Notícias ajustam no máximo ±3 pontos.

**Previsões**: proventos dos próximos 12 meses = média dos últimos 3 anos × crescimento histórico (limitado a ±10%).
Preço = modelo log-normal (tendência = 50% histórico + 50% expectativa de longo prazo; incerteza = volatilidade histórica).

**Alertas diários**: nova oportunidade (abaixo do teto), entrada/saída do top 10, queda forte de ação boa,
novo provento anunciado, data-com chegando, ação da sua carteira virando "Evitar" e notícias negativas relevantes.
""")
    st.warning(AVISO)
