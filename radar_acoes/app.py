"""Painel do Radar de Ações:  python -m streamlit run app.py"""
from __future__ import annotations

import os
import pickle
import threading
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import altair as alt
import numpy as np
import pandas as pd
import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# Painel aberto sem janela no Windows: a saída vai para arquivo em cp1252, que não escreve emojis.
# Fica aqui (e não só em acoes/__init__) porque o Streamlit relê este arquivo a cada clique: vale na hora,
# mesmo com o painel antigo ainda rodando.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        if (getattr(_fluxo, "encoding", "") or "").lower().replace("-", "") != "utf8":
            _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from acoes import AVISO, agenda, aovivo, trading, aporte, atlas, aurum, escritorio, memoria, mesa, meta, plano, universo, visual  # noqa: E402
import segundo_plano  # noqa: E402
from apurar import ULTIMO, apurar  # noqa: E402

st.set_page_config(page_title="AURUM · Inteligência de Investimentos", page_icon="🪙", layout="wide")
visual.aplicar()

COR_SINAL = {"Comprar": "🟢", "Acumular": "🟡", "Aguardar": "🟠", "Evitar": "🔴"}
COR_CONF = {"Alta": "✅ Alta", "Média": "⚠️ Média", "Baixa": "❌ Baixa"}
NUM = "localized"  # números no formato do seu computador (1.234,56)


def brl(x, casas: int = 2) -> str:
    if x is None or x != x:
        return "—"
    return f"R$ {x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def md(texto: str) -> str:
    """Escapa o $ de "R$" para o Streamlit não interpretar como fórmula matemática."""
    return texto.replace("$", r"\$")


def pct(x, casas: int = 1) -> str:
    return "—" if x is None or x != x else f"{x * 100:.{casas}f}%".replace(".", ",")


def col_rs(titulo: str, ajuda: str | None = None):
    return st.column_config.NumberColumn(f"{titulo} (R$)", format=NUM, help=ajuda)


def col_pct(titulo: str, ajuda: str | None = None):
    return st.column_config.NumberColumn(f"{titulo} (%)", format=NUM, help=ajuda)


@st.cache_data(show_spinner=False, max_entries=2)
def carregar(marca: float) -> dict | None:
    """`marca` = data de modificação do arquivo: muda a cada apuração (inclusive as da Equipe 24h), e o painel recarrega.
    (Sem sublinhado no nome: parâmetro com '_' é ignorado pelo cache do Streamlit e o painel ficava com dados velhos.)"""
    if not ULTIMO.exists():
        return None
    with open(ULTIMO, "rb") as f:
        return pickle.load(f)


@st.cache_resource
def _trava_apuracao() -> threading.Lock:
    return threading.Lock()  # uma só para o painel inteiro (todas as abas do navegador)


def rodar(demo: bool):
    """Roda a apuração mostrando, ao vivo, cada etapa e cada agente trabalhando."""
    trava = _trava_apuracao()
    if not trava.acquire(blocking=False):
        st.warning("⏳ Já tem uma apuração em andamento (em outra aba ou clique). Aguarde ela terminar e atualize a página.")
        return
    try:
        with st.status("🪙 AURUM convocou a equipe. Acompanhe o trabalho ao vivo...", expanded=True) as caixa:
            apurar(universo.tickers(), plano.ler()["aporte_mensal"], usar_demo=demo, enviar=False,
                   progresso=lambda m: caixa.write(md(m)))
            caixa.update(label="✅ Apuração concluída — equipe dispensada.", state="complete")
    finally:
        trava.release()
    st.cache_data.clear()
    st.rerun()


# ======================================================================= topo
pl = plano.ler()
with st.sidebar:
    st.header("Comando")
    nome = st.text_input("Como o AURUM deve te chamar?", pl.get("nome", ""), placeholder="ex.: Ana")
    if nome != pl.get("nome", ""):
        pl["nome"] = nome.strip()
        plano.salvar(pl)
    if st.button("🔄 Apurar agora (dados reais)", width="stretch", type="primary"):
        st.session_state["rodar_demo"] = False
    if st.button("🧪 Testar com dados fictícios", width="stretch"):
        st.session_state["rodar_demo"] = True
    st.divider()
    st.header("Equipe 24h")
    _ok, _txt = segundo_plano.ligada()
    st.markdown(("🟢 **Trabalhando em segundo plano**" if _ok else "⚪ **Parada**") + f"  \n<small>{_txt}</small>", unsafe_allow_html=True)
    if not _ok and st.button("▶️ Ligar equipe 24h", width="stretch"):
        st.success(segundo_plano.ligar())
    if _ok and st.button("⏹️ Desligar equipe", width="stretch"):
        st.info(segundo_plano.desligar())
    st.caption("Ligada, a equipe trabalha mesmo com este painel fechado (com o computador ligado) e inicia junto com o Windows.")
    st.caption("O ideal é apurar todo dia útil depois das 18h (fechamento da B3). "
               "Agende o arquivo *Apurar Acoes.bat* no Windows ou use o GitHub Actions (veja o README).")

if "rodar_demo" in st.session_state:  # roda na área principal, para ver a equipe trabalhando com espaço
    rodar(st.session_state.pop("rodar_demo"))

R = carregar(ULTIMO.stat().st_mtime if ULTIMO.exists() else 0)
if R is None:
    visual.topo("Inteligência de investimentos para renda e patrimônio", [("AGUARDANDO PRIMEIRA APURAÇÃO", "alerta")])
    st.info("Ainda não há apuração. Clique em **🔄 Apurar agora** na barra lateral (precisa de internet).")
    st.stop()

rk: pd.DataFrame = R["ranking"]
mac: dict = R.get("macro") or {"selic": 0.14, "ipca_12m": 0.045, "cdi_liquido": 0.119, "estimado": True}
cart = aporte.ler_carteira()


# barra de "frescor" dos dados: o usuário sempre sabe de quando é cada número
datas = pd.to_datetime(rk["data_cotacao"].dropna()) if "data_cotacao" in rk else pd.Series(dtype="datetime64[ns]")
ult_cot = datas.max() if len(datas) else None
atraso = len(pd.bdate_range(ult_cot, pd.Timestamp.today().normalize())) - 1 if ult_cot is not None else 99
fresco = (f"📅 Apuração de **{R['data']:%d/%m/%Y}** · cotações até **{ult_cot:%d/%m/%Y}** (Yahoo Finance) · "
          if ult_cot is not None else f"📅 Apuração de **{R['data']:%d/%m/%Y}** · ")
fresco += (f"Selic **{pct(mac['selic'], 2)}**, IPCA 12m **{pct(mac['ipca_12m'], 2)}** "
           + ("(⚠️ estimados: Banco Central fora do ar)" if mac.get("estimado") else "(Banco Central)"))
agora_br = datetime.now(ZoneInfo("America/Sao_Paulo"))
pregao = agora_br.weekday() < 5 and (10, 0) <= (agora_br.hour, agora_br.minute) < (17, 55)
chips = [("PREGÃO ABERTO" if pregao else "PREGÃO FECHADO", "on" if pregao else ""),
         (f"COTAÇÕES {ult_cot:%d/%m/%Y}" if ult_cot is not None else "SEM COTAÇÕES", "alerta" if atraso > 3 else ""),
         (f"SELIC {pct(mac['selic'], 2)}", "alerta" if mac.get("estimado") else ""),
         (f"{len(rk)} EMPRESAS", ""),
         (f"IPCA {pct(mac['ipca_12m'], 1)}", ""),
         *([(f"FOCUS: SELIC {datetime.now().year + 1} {pct((mac.get('focus') or {}).get(f'selic_{datetime.now().year + 1}'), 2)}", "")]
           if (mac.get("focus") or {}).get(f"selic_{datetime.now().year + 1}") else []),
         (f"{len(escritorio.EQUIPE)} AGENTES ATIVOS" if R.get("mesa") else "AGENTES AGUARDANDO", "" if R.get("mesa") else "alerta"),
         ("IA + PESQUISA WEB" if aurum.ia_disponivel() else "MODO LOCAL (SEM IA)", "" if aurum.ia_disponivel() else "alerta")]
if R.get("demo"):
    chips.insert(1, ("DADOS FICTÍCIOS", "perigo"))
visual.topo(f"{aurum.saudacao(pl.get('nome', ''))} · inteligência de investimentos para renda e patrimônio", chips)
fita_itens = []
ibov = R.get("ibov")
if ibov is not None and len(ibov) > 1:
    fita_itens.append(("IBOV·BOVA11", float(ibov.iloc[-1]), float(ibov.iloc[-1] / ibov.iloc[-2] - 1)))
fita_itens += [(r_["ticker"], float(r_["preco"]), float(r_["var_dia"])) for _, r_ in rk.head(30).iterrows()]
visual.fita(fita_itens)
if atraso > 3:
    st.warning(fresco + " — **dados com mais de 3 dias úteis: clique em Apurar agora.**")
else:
    st.caption(fresco)
if R.get("demo"):
    st.error("⚠️ **MODO DEMONSTRAÇÃO — NÚMEROS FICTÍCIOS.** Nada aqui vale para investir. "
             "Clique em **🔄 Apurar agora (dados reais)** na barra lateral.")

abas = st.tabs(["🪙 AURUM", "📡 Mercado ao vivo", "🔭 Previsões", "⚡ Trading", "🧠 Sala dos Agentes", "✅ O que fazer hoje", "📅 Agenda de proventos", "🎯 Rumo ao R$ 1 milhão", "🏆 Ranking", "🏢 Empresa", "💼 Minha carteira",
                "🧪 O sistema funciona?", "🔔 Alertas", "❓ Como funciona e limites"])

# carteira-alvo e números da meta, usados em várias abas
esc = aporte.escolher(rk, 10, 2)
cart_esp = R.get("carteira_esperada") or meta.carteira_esperada(esc)
pat_hoje = plano.patrimonio_atual(pl, cart, rk)

# ======================================================================= AURUM
with abas[0]:
    jv = R.get("aurum") or aurum.relatorio(R, pl, usar_ia=False)
    sim0 = meta.simular(pl["meta"], pat_hoje, pl["aporte_mensal"], cart_esp["retorno"], cart_esp["volatilidade"],
                        pl["aumento_aporte_aa"], mac["ipca_12m"] if pl["corrigir_inflacao"] else 0.0)
    progresso = min(1.0, pat_hoje / pl["meta"]) if pl["meta"] else 0.0
    melhor = rk[rk["sinal"] == "Comprar"].head(1)
    visual.cartoes([
        ("Rumo à meta", f"{progresso * 100:.1f}%".replace(".", ","), f"{brl(pat_hoje, 0)} de {brl(pl['meta'], 0)}", ""),
        ("Chegada mais provável", meta.fmt_tempo(sim0["meses_50"]), f"anos ruins: {meta.fmt_tempo(sim0['meses_90'])}", "alerta"),
        ("Melhor oportunidade", melhor["ticker"].iloc[0] if len(melhor) else "nenhuma hoje",
         f"{pct(melhor['margem_bazin'].iloc[0])} abaixo do teto" if len(melhor) else "aguarde preço bom", "ok" if len(melhor) else "alerta"),
        ("Alertas importantes", str(sum(a["nivel"] == 1 for a in R["alertas"])), "veja a aba 🔔", "perigo" if any(a["nivel"] == 1 for a in R["alertas"]) else "ok"),
    ])
    hora = pd.Timestamp(jv["hora"])
    visual.fala(jv["texto"], f"RELATÓRIO DO DIA · {hora:%d/%m %H:%M} · "
                + ("IA + PESQUISA NA WEB" if jv["fonte"] == "IA" else "MODO LOCAL (REGRAS)"))
    b1, b2 = st.columns([1, 3])
    if b1.button("🔁 Gerar novo relatório"):
        with st.spinner("AURUM analisando o mercado..."):
            R["aurum"] = aurum.relatorio(R, pl)
            with open(ULTIMO, "wb") as f:
                pickle.dump(R, f)
        st.cache_data.clear()
        st.rerun()
    if not aurum.ia_disponivel():
        b2.caption("Modo local: o AURUM fala só a partir dos dados da apuração. Para ele pesquisar notícias na internet e "
                   "conversar livremente, coloque sua chave da IA (ANTHROPIC_API_KEY) no config.env — veja o README.")

    st.subheader("Converse com o AURUM")
    hist = st.session_state.setdefault("chat", [])
    sug = st.columns(4)
    for col, q in zip(sug, ["O que comprar este mês?", "Quando chego no milhão?", "Melhores pagadoras de dividendos", "É seguro?"]):
        if col.button(q, width="stretch"):
            st.session_state["pergunta_rapida"] = q
    for m_ in hist:
        with st.chat_message(m_["role"], avatar="🪙" if m_["role"] == "assistant" else "🧑"):
            st.markdown(md(m_["content"]))
    pergunta = st.chat_input("Pergunte ao AURUM (ex.: TAEE11 vale a pena?)") or st.session_state.pop("pergunta_rapida", None)
    if pergunta:
        with st.spinner("AURUM pensando..."):
            resp, _fonte = aurum.perguntar(pergunta, [{"role": x["role"], "content": x["content"]} for x in hist], R, pl)
        hist += [{"role": "user", "content": pergunta}, {"role": "assistant", "content": resp}]
        st.rerun()
    if hist and st.button("🧹 Limpar conversa"):
        st.session_state["chat"] = []
        st.rerun()


# ======================================================================= MERCADO AO VIVO
@st.cache_data(ttl=55, show_spinner=False)
def _cotacoes_ao_vivo(tickers: tuple[str, ...]):
    return aovivo.resumir(*aovivo.baixar(list(tickers)))


with abas[1]:
    st.caption("Todas as ações que a equipe acompanha, no pregão de hoje. **Atualiza sozinho a cada minuto** — "
               f"não precisa apertar nada. Fonte: {aovivo.FONTE}.")
    c_ao, c_fil, c_busca = st.columns([1, 2, 2])
    ligado = c_ao.toggle("🔴 Ao vivo", value=True, key="ao_vivo_ligado", help="Desligue para congelar a tela.")
    filtro = c_fil.segmented_control("Mostrar", ["Todas", "Recomendadas", "Minha carteira"], default="Todas",
                                     key="ao_vivo_filtro", label_visibility="collapsed")
    busca = c_busca.text_input("Buscar", placeholder="🔎 buscar ação (ex.: PETR4)", key="ao_vivo_busca",
                               label_visibility="collapsed").strip().upper()

    @st.fragment(run_every=60 if ligado else None)
    def _mercado_ao_vivo():
        lista = tuple(sorted(set(rk["ticker"]) | set(cart["ticker"])))
        try:
            ao = _cotacoes_ao_vivo(lista)
            if ao.empty:
                raise RuntimeError("o Yahoo Finance não devolveu cotações")
            st.session_state["ao_vivo_ultimo"] = ao
        except Exception as e:  # noqa: BLE001 — sem internet ou Yahoo fora: mostra a última leitura boa
            ao = st.session_state.get("ao_vivo_ultimo")
            if ao is None:
                st.warning(f"Não consegui buscar as cotações agora ({str(e)[:120]}). Tento de novo em 1 minuto.")
                return
            st.warning("Falha ao atualizar agora — mostrando a última leitura. Tento de novo em 1 minuto.")
        ib = ao[ao["ticker"] == aovivo.IBOV]
        acoes_ao = ao[ao["ticker"] != aovivo.IBOV].merge(
            rk[["ticker", "nome", "setor", "sinal", "nota", "preco_teto_bazin"]], on="ticker", how="left")
        hora = pd.to_datetime(acoes_ao["hora"]).max()
        aberto = aovivo.pregao_aberto()
        pc = aovivo.placar(acoes_ao)
        ibv = float(ib["var_dia"].iloc[0]) if not ib.empty else float("nan")
        visual.cartoes([
            ("IBOVESPA", (("+" if ibv > 0 else "−" if ibv < 0 else "") + pct(abs(ibv), 2)) if ibv == ibv else "—", "hoje", "sobe" if ibv > 0 else "cai" if ibv < 0 else ""),
            ("SUBINDO", f"🟢 {pc['sobem']}", "ações em alta", "sobe"),
            ("CAINDO", f"🔴 {pc['caem']}", "ações em queda", "cai"),
            ("ESTÁVEIS", f"⚪ {pc['estaveis']}", "entre −0,1% e +0,1%", ""),
            ("PREGÃO", "🟢 ABERTO" if aberto else "⚫ FECHADO",
             f"cotação das {hora:%H:%M} de {hora:%d/%m}" if pd.notna(hora) else "", ""),
        ])
        if not aberto:
            st.info("Pregão fechado: a tela mostra como as ações terminaram o último pregão. Volta a se mexer às 10h.")

        vis = acoes_ao
        if filtro == "Recomendadas":
            vis = vis[vis["sinal"].isin(["Comprar", "Acumular"])]
        elif filtro == "Minha carteira":
            vis = vis[vis["ticker"].isin(cart["ticker"])]
        if busca:
            vis = vis[vis["ticker"].str.contains(busca, regex=False) | vis["nome"].fillna("").str.upper().str.contains(busca, regex=False)]
        if vis.empty:
            st.info("Nenhuma ação neste filtro.")
            return

        def _lista(df, titulo):
            st.markdown(f"**{titulo}**")
            for _, r in df.iterrows():
                cor = visual.VERDE if r["var_dia"] > 0 else visual.VERMELHO
                seta = "▲" if r["var_dia"] > 0 else "▼"
                st.markdown(f"<div style='display:flex;justify-content:space-between;font-family:IBM Plex Mono,monospace;"
                            f"padding:2px 0;border-bottom:1px solid #22262e'><span><b>{r['ticker']}</b> "
                            f"<small style='color:#7D8590'>{brl(r['preco'])}</small></span>"
                            f"<span style='color:{cor};font-weight:600'>{seta} {pct(abs(r['var_dia']), 2)}</span></div>"
                            .replace("$", "&#36;"), unsafe_allow_html=True)

        com_var = vis.dropna(subset=["var_dia"])
        c1, c2 = st.columns(2)
        with c1:
            _lista(com_var[com_var["var_dia"] > 0.001].head(8), "🟢 Maiores altas agora")
        with c2:
            _lista(com_var[com_var["var_dia"] < -0.001].sort_values("var_dia").head(8), "🔴 Maiores quedas agora")

        oport = com_var[(com_var["sinal"].isin(["Comprar", "Acumular"])) & (com_var["var_dia"] < 0)
                        & (com_var["preco"] <= com_var["preco_teto_bazin"])]
        if not oport.empty:
            st.success("💡 **Boas empresas em queda hoje, abaixo do preço-teto:** " + ", ".join(
                f"**{r['ticker']}** ({pct(r['var_dia'], 1)}, {brl(r['preco'])})" for _, r in oport.head(6).iterrows()).replace("$", "\\$")
                + " — para quem compra para o longo prazo, queda em empresa boa pode ser chance de comprar mais barato.")

        graf = com_var.assign(var_pct=com_var["var_dia"] * 100, lado=np.where(com_var["var_dia"] >= 0, "Sobe", "Cai"))
        st.altair_chart(
            alt.Chart(graf).mark_bar().encode(
                x=alt.X("ticker:N", sort="-y", title=None, axis=alt.Axis(labelAngle=-60)),
                y=alt.Y("var_pct:Q", title="Variação hoje (%)"),
                color=alt.Color("lado:N", scale=alt.Scale(domain=["Sobe", "Cai"], range=[visual.VERDE, visual.VERMELHO]), legend=None),
                tooltip=[alt.Tooltip("ticker:N", title="Ação"), alt.Tooltip("nome:N", title="Empresa"),
                         alt.Tooltip("var_pct:Q", title="Hoje (%)", format="+.2f"), alt.Tooltip("preco:Q", title="Preço (R$)", format=",.2f")],
            ).properties(height=260), width="stretch")

        vis = vis.assign(**{c: vis[c].round(2) for c in ("preco", "minima", "maxima")})
        tab = vis.assign(
            tendencia=np.where(vis["var_dia"] > 0.001, "🟢 ▲", np.where(vis["var_dia"] < -0.001, "🔴 ▼", "⚪ ■")),
            var_pct=vis["var_dia"] * 100,
            sinal_txt=vis["sinal"].map(lambda x: f"{COR_SINAL.get(x, '')} {x}" if isinstance(x, str) else "—"),
            abaixo_teto=np.where(vis["preco"] <= vis["preco_teto_bazin"], "✅ sim", "—"),
        )[["tendencia", "ticker", "nome", "preco", "var_pct", "minima", "maxima", "grafico", "sinal_txt", "nota", "preco_teto_bazin", "abaixo_teto", "setor"]]
        st.dataframe(
            tab.style.map(lambda v: f"color: {visual.VERDE}" if v > 0 else f"color: {visual.VERMELHO}" if v < 0 else "",
                          subset=["var_pct"]),
            hide_index=True, width="stretch", height=min(38 * (len(tab) + 1), 760),
            column_config={
                "tendencia": st.column_config.TextColumn(" ", width="small"),
                "ticker": st.column_config.TextColumn("Ação"),
                "nome": st.column_config.TextColumn("Empresa"),
                "preco": col_rs("Agora"),
                "var_pct": st.column_config.NumberColumn("Hoje (%)", format="%+.2f"),
                "minima": col_rs("Mín. do dia"),
                "maxima": col_rs("Máx. do dia"),
                "grafico": st.column_config.LineChartColumn("Gráfico do dia"),
                "sinal_txt": st.column_config.TextColumn("Sinal da equipe", help="O que a equipe recomenda para o longo prazo (apuração)."),
                "nota": st.column_config.ProgressColumn("Nota", min_value=0, max_value=100, format="%.0f"),
                "preco_teto_bazin": col_rs("Preço-teto", "Até esse preço, os proventos médios rendem 6% ao ano (Bazin)."),
                "abaixo_teto": st.column_config.TextColumn("Abaixo do teto?"),
                "setor": st.column_config.TextColumn("Setor"),
            })
        st.caption(f"Atualizado às {datetime.now(aovivo.FUSO):%H:%M:%S}. Lembrete: o sobe-e-desce de um dia é ruído para quem "
                   "investe no longo prazo — use esta tela para achar bons preços, não para vender no susto.")

    _mercado_ao_vivo()

# ======================================================================= PREVISÕES (equipe de previsibilidade)
with abas[2]:
    po = (R.get("oraculos") or {}).get("otto") or {}
    pb = (R.get("oraculos") or {}).get("bento") or {}
    ps = (R.get("oraculos") or {}).get("sofia") or {}
    pv_iris = R.get("previsor") or {}
    st.markdown("### 🔭 Equipe de previsibilidade")
    st.caption("Quatro especialistas em prever. Cada um é **testado no passado sem colar** (só com os dados que existiam em cada data) "
               "e o placar fica aqui, à vista. Quem não bate o chute no teste **não vota** até provar valor.")
    if "otto_prov_12m" not in rk:
        st.info("A equipe de previsibilidade entra na próxima apuração. Clique em **🔄 Apurar agora** na barra lateral.")
    else:
        val_iris = pv_iris.get("validacao") or {}
        cer = ((R.get("mesa") or {}).get("cerebro") or {}).get("por_agente")
        eq = cer[cer["agente"] == "equipe"] if cer is not None and len(cer) else pd.DataFrame()
        visual.cartoes([
            ("💵 OTTO · PROVENTOS", pct(po.get("acerto"), 0) if po.get("n") else "—",
             f"previsões a ±25% do que pagou ({po.get('n', 0)} anos-ação)", "ok" if (po.get("acerto") or 0) >= 0.6 else ""),
            ("🎯 BENTO · ENTRADA", (f"{pct(pb.get('real_80'), 0)} / {pct(pb.get('real_50'), 0)}") if pb.get("n") else "—",
             "prometeu 80% / 50% de execução", "ok" if pb.get("n") and abs(pb["real_80"] - 0.8) < 0.08 else ""),
            ("🧮 SOFIA · MODELO", pct(ps.get("acerto"), 1) if ps.get("n") else "—",
             ("vota (padrão real, t = " + f"{ps.get('t_stat', 0):.1f})".replace(".", ",")) if ps.get("fator", 0) > 0 else "não vota (não provou vantagem)",
             "ok" if ps.get("fator", 0) > 0 else "alerta"),
            ("🔮 ÍRIS · 1 MÊS", pct(val_iris.get("acerto"), 1) if val_iris.get("n") else "—",
             f"chute 'sempre sobe' = {pct(val_iris.get('chute_alta'), 1)}", "ok" if pv_iris.get("fator", 0) > 0 else "alerta"),
            ("🧠 EQUIPE · PLACAR REAL", pct(float(eq["acerto"].iloc[0]), 0) if len(eq) else "—",
             f"{int(eq['conferidos'].iloc[0])} decisões conferidas 3 meses depois" if len(eq) else "começa a contar 3 meses após a 1ª apuração real", ""),
        ])

        st.markdown("#### 🎯 As ações que estamos para comprar — o que cada previsor diz")
        so_compras = st.toggle("Só as recomendadas e a minha carteira", value=True, key="prev_so_compras")
        base_prev = rk[rk["sinal"].isin(["Comprar", "Acumular"]) | rk["ticker"].isin(cart["ticker"])] if so_compras else rk
        if base_prev.empty:
            st.info("Hoje nenhuma ação está com sinal de compra. Desligue o filtro acima para ver as previsões de todas.")
        else:
            tp = base_prev.copy()
            tp["dy_otto"] = tp["otto_prov_12m"] / tp["preco"]
            tp["faixa"] = [f"{brl(a)} a {brl(b)}" if a == a and b == b else "—" for a, b in zip(tp["otto_prov_p10"], tp["otto_prov_p90"])]
            tp["renda_previsivel"] = (tp["otto_acerto"].fillna(0) * (1 - tp["otto_prob_corte"].fillna(1)) * 100).round(0)
            tp["sinal_txt"] = tp["sinal"].map(lambda x: f"{COR_SINAL.get(x, '')} {x}")
            for c in ("otto_prob_corte", "otto_acerto", "bento_prob_tocar_teto", "sofia_prob", "prob_alta_1m"):
                if c not in tp:
                    tp[c] = np.nan
                tp[c + "_pct"] = tp[c] * 100
            cols = ["ticker", "sinal_txt", "preco", "renda_previsivel", "otto_prov_12m", "faixa", "dy_otto", "otto_prob_corte_pct",
                    "otto_acerto_pct", "bento_preco_80", "bento_preco_50", "bento_prob_tocar_teto_pct", "sofia_prob_pct", "prob_alta_1m_pct"]
            tp["dy_otto"] = tp["dy_otto"] * 100
            st.dataframe(tp[cols].sort_values("renda_previsivel", ascending=False), hide_index=True, width="stretch",
                         column_config={
                             "ticker": st.column_config.TextColumn("Ação"),
                             "sinal_txt": st.column_config.TextColumn("Sinal"),
                             "preco": col_rs("Preço"),
                             "renda_previsivel": st.column_config.ProgressColumn("Renda previsível", min_value=0, max_value=100, format="%.0f",
                                                                                 help="Acerto do Otto no passado × (1 − chance de corte). Quanto maior, mais dá para contar com essa renda."),
                             "otto_prov_12m": col_rs("💵 Proventos 12m", "Previsão do Otto por ação para os próximos 12 meses."),
                             "faixa": st.column_config.TextColumn("Faixa provável", help="De 10% a 90%: pelo tamanho dos erros do método no passado."),
                             "dy_otto": st.column_config.NumberColumn("Rende (%)", format="%.1f", help="Proventos previstos ÷ preço de hoje."),
                             "otto_prob_corte_pct": st.column_config.ProgressColumn("Risco de corte", min_value=0, max_value=100, format="%.0f%%"),
                             "otto_acerto_pct": st.column_config.NumberColumn("Otto acertou (%)", format="%.0f",
                                                                              help="Nos últimos anos, quantas vezes o real ficou a ±25% do que o método previa."),
                             "bento_preco_80": col_rs("🎯 Ordem 80%", "Preço de compra com ~80% de chance de executar em 1 mês."),
                             "bento_preco_50": col_rs("🎯 Ordem 50%", "Mais barato, mas só ~50% de chance de executar em 1 mês."),
                             "bento_prob_tocar_teto_pct": st.column_config.NumberColumn("Chega no teto? (%)", format="%.0f",
                                                                                        help="Chance de o preço chegar ao preço-teto no próximo mês (100 = já está abaixo)."),
                             "sofia_prob_pct": st.column_config.NumberColumn("🧮 Sofia (%)", format="%.0f",
                                                                            help="Chance de render mais que a mediana das ações em 3 meses (já ajustada pelo acerto dela no teste)."),
                             "prob_alta_1m_pct": st.column_config.NumberColumn("🔮 Íris (%)", format="%.0f", help="Chance de subir no próximo mês."),
                         })
            st.caption("Como usar: para **renda**, priorize *Renda previsível* alta e *Risco de corte* baixo. Para **comprar mais barato**, "
                       "ponha a ordem limitada no preço do Bento (80% = quase certo de executar; 50% = mais barato, pode não executar).")

        with st.expander("🧮 O que a Sofia aprendeu com os dados"):
            pesos = ps.get("pesos") or {}
            if pesos:
                dfp = pd.DataFrame({"sinal": list(pesos), "peso": list(pesos.values())})
                st.altair_chart(alt.Chart(dfp).mark_bar().encode(
                    x=alt.X("peso:Q", title="Influência (positivo = ajuda a render mais)"), y=alt.Y("sinal:N", sort="-x", title=None),
                    color=alt.condition("datum.peso > 0", alt.value(visual.VERDE), alt.value(visual.VERMELHO))).properties(height=200), width="stretch")
                st.caption(f"Teste sem colar em {ps.get('meses', 0)} meses: acerto {pct(ps.get('acerto'), 1)} (chute = 50%). "
                           f"As 20% que ela mais gostava renderam, em média, {pct(ps.get('spread_3m'), 1)} a mais em 3 meses que as 20% que menos gostava.")
        with st.expander("❓ Por que nenhum previsor promete 100%"):
            st.markdown("""
- **Proventos são a parte mais previsível** do mercado: boas pagadoras mudam pouco de um ano para o outro. Por isso o Otto tem o maior peso
  da equipe de previsão — ele é o coração do projeto de dividendos.
- **Preço de curto prazo é quase aleatório.** Íris e Sofia procuram pequenas vantagens estatísticas; quando o teste mostra que não há
  vantagem, elas ficam neutras em vez de inventar.
- **O Bento não adivinha o futuro**: ele mede quanto a ação costuma oscilar e diz o preço com 80% ou 50% de chance de execução —
  e o teste mostra se essas chances se confirmam.
- O placar real (🧠 Equipe) compara as decisões com o que aconteceu de verdade 3 meses depois. É ele que diz, com o tempo, o quanto confiar.
""")


# ======================================================================= TRADING (médio prazo)
with abas[3]:
    tr = R.get("trading") or {}
    pad = tr.get("padroes", pd.DataFrame())
    sin = tr.get("sinais", pd.DataFrame())
    ch = tr.get("chute") or {}
    pr = tr.get("placar_real") or {}
    st.markdown("### ⚡ Mesa de Trading — médio prazo (semanas a 3 meses)")
    st.caption("O **Leo** testa 5 padrões clássicos do mercado em todas as ações, com custos, e compara com entrar em dias aleatórios. "
               "Só os padrões que **venceram o chute em dois períodos separados** viram sinal. Cada sinal vem com **entrada, stop e alvo**.")
    st.warning("**Trading é separado do projeto de dividendos.** Use só um dinheiro que você aceita arriscar (ex.: até 10–20% do total), "
               "arrisque no máximo **1% desse capital por operação** e **respeite o stop sempre** — é ele que faz a conta fechar no positivo.")
    if pad is None or len(pad) == 0:
        st.info("A Mesa de Trading entra na próxima apuração. Clique em **🔄 Apurar agora** na barra lateral.")
    else:
        ap = pad[pad["status"] == "✅ Aprovado"]
        visual.cartoes([
            ("PADRÕES APROVADOS", f"{len(ap)} de {len(pad)}", "venceram o chute nos 2 períodos", "ok" if len(ap) else "alerta"),
            ("SINAIS HOJE", str(int((sin["status"] == "✅ Aprovado").sum())) if len(sin) else "0",
             f"+ {int((sin['status'] != '✅ Aprovado').sum()) if len(sin) else 0} em observação", ""),
            ("CHUTE (DIA ALEATÓRIO)", pct(ch.get("acerto"), 0), f"ganha em média {pct(ch.get('expectativa'), 1)} por operação", ""),
            ("PLACAR REAL DOS SINAIS", pct(pr.get("acerto"), 0) if pr.get("n") else "—",
             f"{pr.get('n', 0)} encerrados · {pr.get('abertos', 0)} em andamento" if pr.get("n") or pr.get("abertos") else "começa a contar com os sinais de hoje", ""),
        ])

        st.markdown("#### 🎯 Sinais de hoje")
        so_baratas = st.toggle("Só ações baratas (abaixo do preço-teto, do preço justo ou P/VP < 1)", value=False, key="tr_baratas")
        if sin is None or sin.empty:
            st.info("Nenhum padrão aprovado ou em observação disparou nos últimos 3 pregões. **Não operar também é uma decisão** — "
                    "o Leo avisa quando aparecer oportunidade.")
        else:
            vs = sin[sin["barata"]] if so_baratas else sin
            if vs.empty:
                st.info("Nenhum sinal em ação barata hoje.")
            else:
                tv = vs.assign(
                    status_txt=vs["status"], barata_txt=np.where(vs["barata"], "💲 sim", "—"),
                    ganho_pct=vs["ganho_alvo"] * 100, perda_pct=vs["perda_stop"] * 100,
                    acerto_pad=vs["acerto_padrao"] * 100, expect=vs["expectativa_padrao"] * 100,
                    acerto_acao_txt=[f"{a * 100:.0f}% em {n}" if a == a else f"poucos casos ({n})" for a, n in zip(vs["acerto_acao"], vs["n_acao"])],
                    equipe=[f"{COR_SINAL.get(s_, '')} {s_}" if isinstance(s_, str) else "—" for s_ in vs["sinal_equipe"]],
                )
                for c in ("preco", "stop", "alvo"):
                    tv[c] = tv[c].round(2)
                st.dataframe(tv[["status_txt", "ticker", "padrao_nome", "barata_txt", "preco", "stop", "alvo", "ganho_pct", "perda_pct",
                                 "acerto_pad", "expect", "dias_medio", "acerto_acao_txt", "nota", "equipe"]],
                             hide_index=True, width="stretch",
                             column_config={
                                 "status_txt": st.column_config.TextColumn("Padrão no teste"),
                                 "ticker": st.column_config.TextColumn("Ação"),
                                 "padrao_nome": st.column_config.TextColumn("Padrão"),
                                 "barata_txt": st.column_config.TextColumn("Barata?"),
                                 "preco": col_rs("Entrada"),
                                 "stop": col_rs("Stop", "Se fechar abaixo, venda: limita a perda."),
                                 "alvo": col_rs("Alvo", "Preço de venda com lucro (2× o risco)."),
                                 "ganho_pct": st.column_config.NumberColumn("Ganho no alvo (%)", format="+%.1f"),
                                 "perda_pct": st.column_config.NumberColumn("Perda no stop (%)", format="%.1f"),
                                 "acerto_pad": st.column_config.NumberColumn("Acerto do padrão (%)", format="%.0f",
                                                                             help="Nos últimos 3 anos, % das operações deste padrão que terminaram no lucro (com custos)."),
                                 "expect": st.column_config.NumberColumn("Ganho médio/oper. (%)", format="%+.2f",
                                                                         help="Média de TODAS as operações do padrão (ganhos e perdas). É o que importa: positivo = o padrão paga."),
                                 "dias_medio": st.column_config.NumberColumn("Dura (pregões)", format="%.0f"),
                                 "acerto_acao_txt": st.column_config.TextColumn("Nesta ação"),
                                 "nota": st.column_config.ProgressColumn("Nota da equipe", min_value=0, max_value=100, format="%.0f"),
                                 "equipe": st.column_config.TextColumn("Sinal longo prazo"),
                             })
                st.caption("Acerto de 40–55% é normal em bons padrões: o lucro vem de o alvo (2× o risco) pagar mais do que o stop tira. "
                           "Olhe o **Ganho médio por operação**, não só o acerto.")

                with st.expander("🧮 Calculadora: quantas ações comprar", expanded=True):
                    c1, c2, c3 = st.columns(3)
                    capital = c1.number_input("Capital para trading (R$)", min_value=0.0, value=float(st.session_state.get("tr_cap", 5000.0)), step=500.0, key="tr_cap")
                    risco = c2.slider("Risco por operação (% do capital)", 0.5, 3.0, 1.0, 0.25, key="tr_risco") / 100
                    escolha = c3.selectbox("Sinal", [f"{r['ticker']} · {r['padrao_nome']}" for _, r in vs.iterrows()], key="tr_sel")
                    r_ = vs.iloc[[f"{r['ticker']} · {r['padrao_nome']}" for _, r in vs.iterrows()].index(escolha)]
                    tp_ = trading.tamanho_posicao(capital, risco, float(r_["preco"]), float(r_["stop"]))
                    visual.cartoes([("COMPRAR", f"{tp_['quantidade']} ações", f"{brl(tp_['valor'])} a {brl(r_['preco'])}", ""),
                                    ("SE BATER O STOP", brl(-tp_["perda_maxima"]), f"venda a {brl(r_['stop'])}", "perigo"),
                                    ("SE BATER O ALVO", brl(tp_["quantidade"] * (r_["alvo"] - r_["preco"])), f"venda a {brl(r_['alvo'])}", "ok")])
                    st.caption("Dica: no home broker, compre e já deixe a **ordem de stop** e a **ordem de venda no alvo** programadas (OCO, se a corretora tiver).")

        st.markdown("#### 💼 Minhas operações")
        st.caption("Registre aqui o que você comprou. O Leo acompanha e **avisa no Telegram** (com a Equipe 24h ligada) quando bater o alvo, "
                   "o stop ou quando for hora de subir o stop para proteger o ganho.")
        ops = trading.ler_operacoes()
        ed = st.data_editor(ops, num_rows="dynamic", width="stretch", key="tr_ops", hide_index=True,
                            column_config={
                                "ticker": st.column_config.TextColumn("Ação", required=True),
                                "data_compra": st.column_config.TextColumn("Data compra (AAAA-MM-DD)"),
                                "preco_compra": st.column_config.NumberColumn("Preço compra", format="%.2f", min_value=0.0),
                                "quantidade": st.column_config.NumberColumn("Qtd.", format="%d", min_value=0),
                                "stop": st.column_config.NumberColumn("Stop", format="%.2f"),
                                "alvo": st.column_config.NumberColumn("Alvo", format="%.2f"),
                                "status": st.column_config.SelectboxColumn("Situação", options=["aberta", "fechada"], default="aberta"),
                                "preco_venda": st.column_config.NumberColumn("Preço venda", format="%.2f"),
                                "data_venda": st.column_config.TextColumn("Data venda"),
                                "obs": st.column_config.TextColumn("Obs."),
                            })
        if st.button("💾 Salvar operações", key="tr_salvar"):
            trading.salvar_operacoes(ed)
            st.success("Operações salvas.")
            st.rerun()
        precos_ag = {t: float(p_) for t, p_ in zip(rk["ticker"], rk["preco"]) if p_ == p_}
        ult_ao = st.session_state.get("ao_vivo_ultimo")
        if ult_ao is not None and len(ult_ao):
            precos_ag.update({t: float(p_) for t, p_ in zip(ult_ao["ticker"], ult_ao["preco"])})
        acomp = trading.acompanhar(ops, precos_ag)
        if len(acomp):
            st.dataframe(acomp.assign(resultado=acomp["resultado"] * 100), hide_index=True, width="stretch",
                         column_config={"ticker": "Ação", "preco_compra": col_rs("Compra"), "preco_agora": col_rs("Agora"),
                                        "quantidade": st.column_config.NumberColumn("Qtd.", format="%d"),
                                        "resultado": st.column_config.NumberColumn("Resultado (%)", format="%+.1f"),
                                        "resultado_rs": col_rs("Resultado"), "stop": col_rs("Stop"), "alvo": col_rs("Alvo"),
                                        "dias": st.column_config.NumberColumn("Pregões", format="%d"),
                                        "o_que_fazer": st.column_config.TextColumn("O que fazer", width="large")})
        fechadas = ops[(ops["status"].str.lower() == "fechada") & ops["preco_venda"].notna() & ops["preco_compra"].notna()]
        if len(fechadas):
            res = (fechadas["preco_venda"] - fechadas["preco_compra"]) * fechadas["quantidade"].fillna(0)
            st.caption(f"Operações encerradas: {len(fechadas)} · ganharam {int((res > 0).sum())} · resultado total {brl(float(res.sum()))} (antes de IR).")

        st.markdown("#### 📋 Os padrões e o teste de cada um")
        tp2 = pad.assign(acerto=pad["acerto_conf"] * 100, ganho=pad["ganho_medio_conf"] * 100, perda=pad["perda_media_conf"] * 100,
                         expect=pad["expectativa_conf"] * 100, expect_d=pad["expectativa_desc"] * 100, vant=pad["vantagem_vs_chute"] * 100)
        st.dataframe(tp2[["status", "nome", "n_conf", "acerto", "ganho", "perda", "expect", "vant", "expect_d", "n_desc", "dias_medio_conf"]],
                     hide_index=True, width="stretch",
                     column_config={"status": "Resultado", "nome": "Padrão",
                                    "n_conf": st.column_config.NumberColumn("Operações (3 anos)", format="%d"),
                                    "acerto": st.column_config.NumberColumn("Acerto (%)", format="%.0f"),
                                    "ganho": st.column_config.NumberColumn("Ganho médio (%)", format="+%.1f"),
                                    "perda": st.column_config.NumberColumn("Perda média (%)", format="%.1f"),
                                    "expect": st.column_config.NumberColumn("Por operação (%)", format="%+.2f"),
                                    "vant": st.column_config.NumberColumn("vs. chute (p.p.)", format="%+.2f"),
                                    "expect_d": st.column_config.NumberColumn("Período antigo (%)", format="%+.2f",
                                                                              help="Mesmo teste no período anterior: o padrão também funcionava?"),
                                    "n_desc": st.column_config.NumberColumn("Oper. antigas", format="%d"),
                                    "dias_medio_conf": st.column_config.NumberColumn("Dura (pregões)", format="%.0f")})
        with st.expander("📖 Como cada padrão funciona"):
            for k, (nome_, desc_) in trading.PADROES.items():
                st.markdown(f"**{nome_}** — {desc_}")
            st.markdown(f"""
**Regras de saída (iguais para todos):** stop a ~1 mês de oscilação normal da ação (entre 5% e 18% abaixo da entrada); alvo a **2× o risco**;
quando o ganho chega a 1× o risco, o stop sobe para o preço de compra (não deixa um ganho virar perda); se em **3 meses** não bateu
nem alvo nem stop, sai pelo preço do dia. Custos de {trading.CUSTO * 100:.2f}% por operação já descontados.
""".replace(".", ",", 1))
        with st.expander("🧾 Imposto e regras (Brasil)"):
            st.markdown("""
- **Swing trade (compra e venda em dias diferentes)**: 15% sobre o lucro. **Isento** se o total de **vendas** de ações no mês for até **R$ 20 mil**.
- **Day trade** (compra e venda no mesmo dia): 20%, sem isenção — este sistema **não** é para day trade.
- O imposto é pago por você via **DARF** até o último dia útil do mês seguinte; prejuízos compensam lucros futuros do mesmo tipo.
- Confirme com um contador; regras podem mudar.
""")
        if pr.get("n") or pr.get("abertos"):
            with st.expander("📊 Placar real: todos os sinais aprovados já dados"):
                st.dataframe(pr["tabela"], hide_index=True, width="stretch")


# ======================================================================= SALA DOS AGENTES
with abas[4]:
    @st.fragment(run_every=20)
    def _sala_ao_vivo():
        """Atualiza sozinho a cada 20 s: dá para ver a equipe trabalhando enquanto o agente roda."""
        ok_, txt_ = segundo_plano.ligada()
        stt = escritorio.ler_status()
        c_tit, c_vis = st.columns([4, 1])
        c_tit.subheader("🏢 Escritório — a equipe agora")
        c_vis.segmented_control("Visão", ["3D", "2D"], key="visao_sala", default="3D", label_visibility="collapsed")
        st.caption(("🟢 Equipe ligada em segundo plano — " if ok_ else "⚪ Equipe parada (ligue em 'Equipe 24h' na barra lateral) — ")
                   + txt_ + f" · {escritorio.dias_trabalhados()} dia(s) de trabalho registrados no diário.")
        mesas = []
        for aid, (nome_, ic, cargo) in escritorio.EQUIPE.items():
            e = stt.get(aid, {})
            desde = e.get("desde", "")
            mesas.append({"id": aid, "icone": ic, "nome": nome_, "cargo": cargo, "estado": e.get("estado", "pausa"),
                          "tarefa": e.get("tarefa", ""), "desde": f"desde {pd.Timestamp(desde):%d/%m %H:%M}" if desde else ""})
        agora_sala = datetime.now(ZoneInfo("America/Sao_Paulo"))
        pregao_sala = agora_sala.weekday() < 5 and (10, 0) <= (agora_sala.hour, agora_sala.minute) < (17, 55)
        if st.session_state.get("visao_sala", "3D") == "3D":
            visual.sala_3d(mesas, pregao_sala, agora_sala.hour, fita_itens)
        else:
            visual.sala_ilustrada(mesas, pregao_sala, agora_sala.hour)
        di = escritorio.ler_diario(60)
        if di:
            nomes_ = {k: f"{v[1]} {v[0]}" for k, v in escritorio.EQUIPE.items()}
            visual.console([f"{pd.Timestamp(d['quando']):%d/%m %H:%M}  {nomes_.get(d['agente'], d['agente'])}: {d['texto']}" for d in di])
        else:
            st.caption("O diário começa na primeira apuração com dados reais.")
    _sala_ao_vivo()

    M = R.get("mesa")
    if not M:
        st.info("A equipe ainda não se reuniu nesta apuração. Clique em **🔄 Apurar agora**.")
    else:
        hora_m = pd.Timestamp(M.get("hora") or R["data"])
        st.markdown(md(
            "Dez especialistas analisam **todas** as ações, cada um pelo seu ângulo, e votam de −2 a +2 (o Bento não vota: ele dá o preço de entrada). Depois, "
            "**um confere o trabalho do outro** (verificação cruzada) e o AURUM só recomenda compra quando a nota do sistema "
            "**e** a equipe concordam (dupla checagem)." + (" Hoje os especialistas também foram revisados por IA." if M.get("ia") else "")))
        ops_all = M["opinioes"]
        nota_de = dict(zip(rk["ticker"], rk["nota"]))
        top15 = rk.head(15)["ticker"].tolist()
        cards = []
        for ag in mesa.AGENTES:
            votos = {t: ops_all[t][ag.id] for t in ops_all if ag.id in ops_all[t]}
            fav = sorted([t for t, v in votos.items() if v["voto"] > 0], key=lambda t: (-votos[t]["voto"], -nota_de.get(t, 0)))[:3]
            alvo = next((t for t in top15 if votos.get(t, {}).get("voto", 0) < 0 and votos[t]["argumentos"]), None)
            cards.append({"icone": ag.icone, "nome": ag.apelido, "cargo": ag.nome,
                          "status": f"CONCLUIU ÀS {hora_m:%H:%M}" + (" · REVISADO COM IA" if M.get("ia") and ag.id != "previsor" else ""),
                          "a_favor": sum(v["voto"] > 0 for v in votos.values()), "contra": sum(v["voto"] < 0 for v in votos.values()),
                          "vetos": sum(bool(v.get("veto")) for v in votos.values()), "favoritas": ", ".join(fav),
                          "alerta": f"{alvo}: {votos[alvo]['argumentos'][0]}" if alvo else ""})
        visual.agentes(cards)

        st.subheader("🧠 Cérebro de cada agente — memória e aprendizado")
        cer = M.get("cerebro") or {}
        pa = cer.get("por_agente")
        apr = M.get("aprendizado") or {}
        if pa is None or len(pa) == 0:
            st.info(md(f"Os agentes estão **memorizando**: {cer.get('votos_guardados', 0):,} votos guardados".replace(",", ".")
                       + (f" desde {pd.Timestamp(cer['desde']):%d/%m/%Y}" if cer.get("desde") else "")
                       + ". Cada voto é conferido 3 meses depois contra o que a ação fez de verdade (versus a média do mercado). "
                         "Com amostra suficiente, quem acerta mais ganha mais peso nas decisões e quem erra perde."))
        else:
            mem = pa.copy()
            mem["Agente"] = mem["agente"].map(lambda a: f"{mesa.POR_ID[a].icone} {mesa.POR_ID[a].apelido}" if a in mesa.POR_ID
                                              else "🧠 EQUIPE (decisão final)" if a == "equipe" else a)
            mem["Peso aprendido"] = mem["agente"].map(lambda a: f"×{apr.get(a, 1.0):.2f}".replace(".", ","))
            st.dataframe(pd.DataFrame({
                "Agente": mem["Agente"], "Votos conferidos": mem["conferidos"], "Acerto real": mem["acerto"].map(pct),
                "Ações que apoiou (vs mercado)": mem["ganho_a_favor"].map(pct), "Ações que rejeitou (vs mercado)": mem["ganho_contra"].map(pct),
                "Peso aprendido": mem["Peso aprendido"]}), hide_index=True, width="stretch")
            st.caption(f"Peso só muda após {memoria.AMOSTRA_MINIMA} votos conferidos. "
                       f"{cer.get('pendentes', 0):,} votos ainda aguardando completar 3 meses.".replace(",", "."))

        A = R.get("atlas")
        if A:
            st.subheader("🧭 Atlas — o explorador com livre-arbítrio")
            st.caption("Atlas decide sozinho o que investigar, com ferramentas: consulta o ranking, abre fichas, compara, pesquisa a internet "
                       "(com IA), guarda anotações na memória de longo prazo, propõe novas ações para a equipe vigiar e levanta alertas. "
                       "Ele não compra, não vende e não mexe no seu plano.")
            visual.fala(A["relatorio"], f"ATLAS · {pd.Timestamp(A['hora']):%d/%m %H:%M} · "
                        + ("MODO AUTÔNOMO (IA)" if A["modo"] == "IA" else "MODO LOCAL (REGRAS)"))
            c1, c2 = st.columns(2)
            with c1:
                st.markdown("**O que ele fez hoje**")
                visual.console(A["diario"], "🧭 ")
            with c2:
                st.markdown("**Memória de longo prazo**")
                notas_ = atlas.ler_notas(15)
                if notas_:
                    st.dataframe(pd.DataFrame(notas_)[::-1].rename(columns={"data": "Data", "ticker": "Ação", "texto": "Anotação"}),
                                 hide_index=True, width="stretch", height=230)
                else:
                    st.caption("Vazia por enquanto (as anotações nascem no modo autônomo com IA).")
                desc = atlas.ler_descobertas()
                st.markdown("**Ações que ele colocou no radar:** " + (", ".join(desc) if desc else "nenhuma ainda"))

        st.subheader("📟 Atividade da equipe")
        visual.console(M["log"], f"[{hora_m:%H:%M}] ")

        st.subheader("🔍 Verificação cruzada — um confere o outro")
        ver = pd.DataFrame(M.get("verificacoes") or [])
        if ver.empty:
            st.success("Nenhuma contestação hoje: os pareceres dos agentes são coerentes entre si.")
        else:
            visual.cartoes([("Contestações", str(len(ver)), "achados de um agente sobre outro"),
                            ("Votos corrigidos", str(int((ver["efeito"] != "anotado").sum())), "antes de chegar ao consenso", "alerta"),
                            ("Ações revisadas", str(ver["ticker"].nunique()), "com ao menos uma contestação")])
            par = ver.groupby(["verificador", "verificado"]).size().reset_index(name="vezes")
            st.dataframe(par.rename(columns={"verificador": "Quem conferiu", "verificado": "Trabalho conferido", "vezes": "Contestações"}),
                         hide_index=True, width="stretch")
            with st.expander("Ver cada contestação"):
                st.dataframe(ver.rename(columns={"verificador": "Quem conferiu", "verificado": "Conferido", "ticker": "Ação",
                                                 "achado": "O que encontrou", "efeito": "Efeito"}), hide_index=True, width="stretch")

        st.subheader("🗳️ Placar da mesa")
        pl_m = rk[["posicao", "ticker", "sinal", "consenso", "placar", "a_favor", "contra", "checagem"]].copy()
        pl_m["votos"] = pl_m["ticker"].map(lambda t: mesa.votos_icones(ops_all[t]))
        pl_m["sinal"] = pl_m["sinal"].map(lambda x: f"{COR_SINAL.get(x, '')} {x}")
        st.dataframe(pl_m[["posicao", "ticker", "consenso", "placar", "votos", "a_favor", "contra", "sinal", "checagem"]],
                     hide_index=True, width="stretch", height=420, column_config={
                         "posicao": st.column_config.NumberColumn("#", width="small"), "ticker": "Ação", "consenso": "Consenso da mesa",
                         "placar": st.column_config.NumberColumn("Placar (−2 a +2)", format="%+.2f"),
                         "votos": st.column_config.TextColumn("Votos (💰🏛️🏷️📈📰🔮🛡️)", width="large"),
                         "a_favor": "A favor", "contra": "Contra", "sinal": "Decisão final",
                         "checagem": st.column_config.TextColumn("Dupla checagem")})
        st.caption("🟢🟢 forte a favor · 🟢 a favor · ⚪ neutro · 🔴 contra · 🔴🔴 forte contra · ⛔ veto")

        st.subheader("💬 Debate sobre uma ação")
        t_deb = st.selectbox("Escolha a ação", rk["ticker"], key="debate",
                             format_func=lambda x: f"{x} — {rk.set_index('ticker').at[x, 'consenso']}")
        rotulo = {2: "forte a favor", 1: "a favor", 0: "neutro", -1: "contra", -2: "forte contra"}
        for ag in mesa.AGENTES:
            o = ops_all[t_deb].get(ag.id)
            if not o:
                continue
            with st.chat_message(ag.apelido, avatar=ag.icone):
                st.markdown(md(f"**{ag.apelido}** · {ag.nome} — **{'VETO' if o.get('veto') else rotulo[o['voto']]}**\n\n"
                               + "\n".join(f"- {a}" for a in o["argumentos"])))
        rr = rk.set_index("ticker").loc[t_deb]
        with st.chat_message("AURUM", avatar="🪙"):
            st.markdown(md(f"**AURUM** — consenso: **{rr['consenso']}** (placar {rr['placar']:+.2f}). "
                           f"Decisão final: **{rr['sinal']}**" + (f" — {rr['checagem']}." if rr.get("checagem") not in (None, "ok") else ".")))

        st.subheader("🔮 Íris — quem pode subir ou cair no próximo mês")
        PV = R.get("previsor") or {}
        val = PV.get("validacao") or {}
        real = PV.get("placar_real") or {}
        visual.cartoes([
            ("Acerto no teste de 3 anos", pct(val.get("acerto")), f"{val.get('n', 0)} previsões testadas sem olhar o futuro"),
            ("Acerto de quem chuta 'sobe'", pct(val.get("chute_alta")), "a régua para comparar"),
            ("Placar real (previsões registradas)", pct(real.get("acerto")) if real.get("n_direcionais") else "aguardando",
             f"{real.get('n', 0)} conferidas · {real.get('pendentes', 0)} esperando completar 1 mês"),
            ("Vantagem comprovada?", "SIM" if PV.get("fator", 0) > 0 else "NÃO",
             "previsões valendo" if PV.get("fator", 0) > 0 else "previsões neutralizadas", "ok" if PV.get("fator", 0) > 0 else "alerta"),
        ])
        if "prob_alta_1m" in rk:
            col = "prob_alta_1m" if PV.get("fator", 0) > 0 else "prob_alta_1m_bruta"
            if PV.get("fator", 0) <= 0:
                st.warning("A Íris **não bateu o chute** no teste histórico. As probabilidades abaixo são **brutas, só para estudo**, "
                           "e não influenciam nenhuma recomendação.")
            ok_ = rk.dropna(subset=[col])
            c1, c2 = st.columns(2)
            for colz, titulo, dados_ in ((c1, "📈 Maior chance de ALTA", ok_.nlargest(8, col)), (c2, "📉 Maior chance de QUEDA", ok_.nsmallest(8, col))):
                colz.markdown(f"**{titulo}**")
                colz.dataframe(pd.DataFrame({"Ação": dados_["ticker"], "Chance de alta": dados_[col],
                                             "Variação típica": dados_["ret_mediano_1m"].map(lambda x: pct(x)),
                                             "Faixa (10%–90%)": [f"{pct(a)} a {pct(b)}" for a, b in zip(dados_["ret_p10_1m"], dados_["ret_p90_1m"])]}),
                               hide_index=True, width="stretch",
                               column_config={"Chance de alta": st.column_config.ProgressColumn(min_value=0.0, max_value=1.0, format="percent")})
            st.caption("Como a Íris prevê: procura no passado da própria ação os dias mais parecidos com hoje (tendência de 6 meses, "
                       "distância da média de 200 dias, último mês) e conta quantas vezes subiu no mês seguinte. "
                       "Cada previsão diária é registrada e conferida 1 mês depois — o placar real aparece acima.")

# ======================================================================= HOJE
with abas[5]:
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
            st.markdown(md("\n".join(f"- **{r['Ação']}** — {r['Por que']}" for _, r in tab.iterrows())))
        visual.cartoes([("Total a investir", brl(compras["valor"].sum())),
                        ("Sobra", brl(sobra), "fica para o mês que vem"),
                        ("Renda extra por ano", brl(compras["renda_anual_estimada"].sum()), "com esta compra", "ok")])
        st.caption("Compre no **mercado fracionário** (código com F no final, ex.: TAEE11F) para comprar 1 cota de cada vez. "
                   "Antes de comprar, clique em *Status Invest ↗* e confira o preço e os proventos.")

    st.divider()
    st.subheader("🔭 Um passo à frente — o que vem por aí")
    st.caption("Ninguém prevê o preço de amanhã. O que dá para antecipar é o que já está marcado para acontecer.")
    if mac.get("leitura_juros"):
        st.info(md("**Juros:** " + mac["leitura_juros"]))
    hoje_ts = pd.Timestamp(R["data"])
    carteira_ts = set(cart["ticker"]) if len(cart) else set()
    if "proximo_balanco" in rk:
        bal = rk[rk["proximo_balanco"].notna() & ((rk["posicao"] <= 20) | rk["ticker"].isin(carteira_ts))].copy()
        bal["quando"] = pd.to_datetime(bal["proximo_balanco"])
        bal = bal[(bal["quando"] >= hoje_ts) & (bal["quando"] <= hoje_ts + pd.Timedelta(days=21))].sort_values("quando")
    else:
        bal = pd.DataFrame()
    dcs = agenda.proximas_datas_com(rk, 15, R["data"])
    a1, a2 = st.columns(2)
    with a1:
        st.markdown("**🗓️ Balanços nas próximas 3 semanas**")
        if len(bal):
            st.dataframe(pd.DataFrame({"Ação": bal["ticker"], "Divulga em": bal["quando"].dt.strftime("%d/%m"),
                                       "Sinal hoje": bal["sinal"].map(lambda x: f"{COR_SINAL.get(x, '')} {x}")}),
                         hide_index=True, width="stretch")
            st.caption("Resultado mexe com preço e com proventos: a equipe reavalia no dia seguinte.")
        else:
            st.caption("Nenhuma data de balanço informada pela fonte para as próximas 3 semanas.")
    with a2:
        st.markdown("**💰 Datas-com nos próximos 15 dias**")
        if len(dcs):
            st.dataframe(pd.DataFrame({"Ação": dcs["ticker"], "Data-ex": dcs["data_ex"].dt.strftime("%d/%m"),
                                       "Compre até": dcs["comprar_ate"].dt.strftime("%d/%m")}), hide_index=True, width="stretch")
        else:
            st.caption("Nenhuma data-ex informada para os próximos 15 dias.")

    st.divider()
    st.subheader(f"🎯 Sua meta: {brl(pl['meta'], 0)}")
    sim = meta.simular(pl["meta"], pat_hoje, pl["aporte_mensal"], cart_esp["retorno"], cart_esp["volatilidade"],
                       pl["aumento_aporte_aa"], mac["ipca_12m"] if pl["corrigir_inflacao"] else 0.0)
    visual.cartoes([("Você tem hoje", brl(pat_hoje, 0)),
                    ("Chegada mais provável", meta.fmt_tempo(sim["meses_50"]), "metade das simulações"),
                    ("Com 90% de chance, até", meta.fmt_tempo(sim["meses_90"]), "mesmo com anos ruins", "alerta")])
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
        st.warning(md(f"**{a['tipo']}** — {a['texto']}"))
    if len(imp) > 8:
        st.caption(f"+ {len(imp) - 8} alertas na aba 🔔 Alertas.")

# ======================================================================= AGENDA
with abas[6]:
    st.subheader("📅 Quanto você deve receber nos próximos 12 meses")
    compras_ag, _ = aporte.sugerir(rk, pl["aporte_mensal"], cart)
    atual = dict(zip(cart["ticker"], cart["quantidade"])) if len(cart) else {}
    com_plano = dict(atual)
    for _, r_ in compras_ag.iterrows():
        com_plano[r_["ticker"]] = com_plano.get(r_["ticker"], 0) + r_["comprar_qtd"]
    proj_atual = agenda.projetar(atual, R["proventos"], rk, R["data"])
    proj_plano = agenda.projetar(com_plano, R["proventos"], rk, R["data"])
    if proj_plano.empty:
        st.info("Cadastre sua carteira na aba 💼 Minha carteira para ver a agenda (ou ajuste o aporte para incluir as compras do mês).")
    else:
        renda_atual = float(proj_atual["valor"].sum()) if len(proj_atual) else 0.0
        visual.cartoes([
            ("Carteira atual: renda em 12 meses", brl(renda_atual), "estimativa pelo histórico"),
            ("Com as compras deste mês", brl(proj_plano["valor"].sum()), f"+{brl(proj_plano['valor'].sum() - renda_atual)}", "ok"),
            ("Média por mês", brl(proj_plano["valor"].sum() / 12), "com as compras do mês"),
        ])
        ordem = proj_plano.groupby(["ordem", "mes"])["valor"].sum().reset_index().sort_values("ordem")
        st.altair_chart(alt.Chart(proj_plano).mark_bar().encode(
            x=alt.X("mes:N", sort=ordem["mes"].tolist(), title=None), y=alt.Y("sum(valor):Q", title="R$ no mês"),
            color=alt.Color("ticker:N", title="Ação"), tooltip=["mes", "ticker", alt.Tooltip("valor:Q", format=",.2f")]), width="stretch")
        st.caption("Barras: proventos esperados por mês (carteira atual + compras sugeridas deste mês), pelo padrão dos últimos 3 anos "
                   "de cada empresa e pela previsão de proventos. Datas e valores podem mudar: a empresa anuncia antes de pagar.")
    st.subheader("🗓️ Próximas datas-com (para receber, compre até o pregão anterior)")
    dc = agenda.proximas_datas_com(rk, 45, R["data"])
    if dc.empty:
        st.caption("Nenhuma data-ex informada para os próximos 45 dias.")
    else:
        st.dataframe(pd.DataFrame({"Ação": dc["ticker"], "Sinal": dc["sinal"].map(lambda x: f"{COR_SINAL.get(x, '')} {x}"),
                                   "Data-ex": dc["data_ex"].dt.strftime("%d/%m/%Y"), "Compre até": dc["comprar_ate"].dt.strftime("%d/%m/%Y"),
                                   "Último provento (R$/ação)": dc["ultimo_provento_valor"].map(brl),
                                   "Rende por ano (média 5a)": dc["dy_medio_5a"].map(pct)}), hide_index=True, width="stretch")
        st.caption("Comprar só para pegar um provento não costuma valer a pena (o preço cai no valor do provento na data-ex). "
                   "Use isto para encaixar compras que você já ia fazer.")

# ======================================================================= META
with abas[7]:
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
    st.markdown(md(f"**Patrimônio hoje: {brl(pat_hoje, 0)}** (carteira de ações da aba 💼 pelos preços de hoje + o que você tem fora da bolsa). "
                   f"Tempo até {brl(pl['meta'], 0)}:"))
    visual.cartoes([("🍀 Com anos bons", meta.fmt_tempo(sim["meses_10"]), "só 10% chegam antes", "ok"),
                    ("🎯 Mais provável", meta.fmt_tempo(sim["meses_50"]), "metade das simulações"),
                    ("🌧️ Com anos ruins", meta.fmt_tempo(sim["meses_90"]), "9 em 10 chegam até aqui", "alerta")])

    f = sim["faixas"].copy()
    lim = min(40, max(10, int(((sim["meses_90"] or 480) / 12) + 3)))
    f = f[f["ano"] <= lim]
    rf_ret = mac["cdi_liquido"]
    f["renda fixa"] = [pat_hoje * (1 + rf_ret) ** a + sum(pl["aporte_mensal"] * (1 + pl["aumento_aporte_aa"]) ** (mm // 12)
                       * (1 + rf_ret) ** ((a * 12 - mm - 1) / 12) for mm in range(a * 12)) for a in f["ano"]]
    base = alt.Chart(f).encode(x=alt.X("ano:Q", title="Anos a partir de hoje"))
    faixa = base.mark_area(opacity=0.14, color=visual.DESTAQUE).encode(
        y=alt.Y("pessimista:Q", title="Patrimônio (R$)", axis=alt.Axis(format="~s")), y2="otimista:Q")
    longo = f.melt(id_vars="ano", value_vars=["mediana", "renda fixa", "meta", "investido"], var_name="linha", value_name="valor")
    nomes_l = {"mediana": "Ações — mais provável", "renda fixa": f"Renda fixa líquida ({pct(rf_ret)} a.a.)",
               "meta": "Meta", "investido": "Só o que você aportou"}
    longo["linha"] = longo["linha"].map(nomes_l)
    linhas = alt.Chart(longo).mark_line(strokeWidth=2.5).encode(
        x="ano:Q", y="valor:Q",
        color=alt.Color("linha:N", title=None, legend=alt.Legend(orient="bottom", labelLimit=300),
                        scale=alt.Scale(domain=list(nomes_l.values()), range=[visual.DESTAQUE, visual.AZUL, visual.VERMELHO, visual.CINZA])),
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
with abas[8]:
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
    cols = ["posicao", "ticker", "nome", "sinal", "consenso", "nota", "confianca", "preco", "preco_teto_bazin", "margem_bazin",
            "grau_Valor", "grau_Renda", "grau_Qualidade", "grau_Saúde", "grau_Momento", "seguranca_div", "f_score_9",
            "dy_medio_5a", "dy_previsto", "proventos_previstos_12m", "retorno_total_esperado_aa", "anos_pagou_10",
            "cresc_proventos_5a", "roe", "pl", "pvp", "var_12m", "meses_provaveis", "setor", "conferir"]
    st.dataframe(v[[c for c in cols if c in v]], hide_index=True, width="stretch", height=600, column_config={
        "posicao": st.column_config.NumberColumn("#", width="small"),
        "ticker": "Ação", "nome": "Empresa", "sinal": "Sinal", "setor": "Setor", "consenso": "Mesa de agentes",
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
        "grau_Valor": st.column_config.TextColumn("Valor", help="Nota de F a A+ comparando com as empresas do mesmo setor."),
        "grau_Renda": "Renda", "grau_Qualidade": "Qualidade", "grau_Saúde": "Saúde", "grau_Momento": "Momento",
        "seguranca_div": st.column_config.NumberColumn("Segurança dos dividendos", format="%.0f", help="Checagens aprovadas (0–100)."),
        "f_score_9": st.column_config.NumberColumn("Piotroski (0–9)", format="%.0f", help="Força do balanço em 9 testes."),
        "conferir": st.column_config.LinkColumn("Conferir", display_text="Status Invest ↗"),
    })
    st.caption("🟢 **Comprar**: nota ≥ 65, preço abaixo do teto e dados confiáveis · 🟡 **Acumular**: nota ≥ 55 e até 10% acima do teto · "
               "🟠 **Aguardar**: boa, mas cara ou paga menos de 4% ao ano · 🔴 **Evitar**: nota baixa ou prejuízo.")
    if R.get("sem_dados"):
        st.caption(f"Sem dados nesta apuração (código pode ter mudado na B3): {', '.join(R['sem_dados'])}")

# ======================================================================= EMPRESA
with abas[9]:
    nomes = rk.set_index("ticker")["nome"]
    t = st.selectbox("Escolha a empresa", rk["ticker"], format_func=lambda x: f"{x} — {nomes[x]}")
    r = rk.set_index("ticker").loc[t]
    info = R["info"].get(t, {})
    precos: pd.Series = R["precos"][t]
    prov: pd.Series = R["proventos"][t]
    st.subheader(f"{COR_SINAL.get(r['sinal'], '')} {t} — {r['nome']}")
    st.markdown(md(f"**Veredito: {r['sinal'].upper()}** (nota {r['nota']:.0f}/100, {int(r['posicao'])}º de {len(rk)}). {r['por_que']}"))
    if R.get("mesa") and t in R["mesa"]["opinioes"]:
        st.markdown(md(f"🧠 **Mesa de agentes: {r.get('consenso', '—')}** · {mesa.votos_icones(R['mesa']['opinioes'][t])} "
                       "— veja o debate completo na aba 🧠 Sala dos Agentes."))
    links = [f"[Status Invest ↗]({r['conferir']})"] + ([f"[Site da empresa ↗]({info['website']})"] if info.get("website") else [])
    st.caption(f"{r['setor']} · cotação de {pd.Timestamp(r['data_cotacao']):%d/%m/%Y} · " + " · ".join(links))
    if r.get("avisos_dados"):
        st.warning(md(f"**Confiança dos dados: {r['confianca']}** — {r['avisos_dados']}. Confira no Status Invest antes de comprar."))
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
        camadas = [alt.Chart(p5).mark_line(color=visual.OURO).encode(x=alt.X("data:T", title=None, axis=alt.Axis(format="%m/%Y")), y=alt.Y("preco:Q", title="R$", scale=alt.Scale(zero=False)),
                                                      tooltip=[alt.Tooltip("data:T", format="%d/%m/%Y"), alt.Tooltip("preco:Q", format=".2f")])]
        if r["preco_teto_bazin"] == r["preco_teto_bazin"]:
            camadas.append(alt.Chart(pd.DataFrame({"y": [r["preco_teto_bazin"]]})).mark_rule(color=visual.VERDE, strokeDash=[6, 4]).encode(y="y:Q"))
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
            st.altair_chart(alt.Chart(anual).mark_bar(color=visual.OURO).encode(
                x=alt.X("ano:N", title=None), y=alt.Y("valor:Q", title="R$ por ação"),
                tooltip=["ano", alt.Tooltip("valor:Q", format=".2f", title="R$ por ação")]), width="stretch")
            st.caption(f"Costuma pagar em: **{r.get('meses_provaveis', '—')}**. "
                       f"Próxima data-ex informada: **{pd.Timestamp(r['ex_dividendo']):%d/%m/%Y}**." if isinstance(r['ex_dividendo'], str) else "Próxima data-ex: não informada.")

    st.markdown("**🔮 Previsão (estatística, não é garantia)**")
    pv = pd.DataFrame([{"Daqui a": f"{a} ano{'s' if a > 1 else ''}",
                        "Cenário ruim": brl(r.get(f"preco_{a}a_pessimista")), "Mais provável": brl(r.get(f"preco_{a}a_mediana")),
                        "Cenário bom": brl(r.get(f"preco_{a}a_otimista"))} for a in (1, 3, 5)])
    p1, p2 = st.columns([3, 2])
    p1.dataframe(pv, hide_index=True, width="stretch")
    p2.markdown(md(f"- Proventos esperados: **{pct(r.get('dy_previsto'))} ao ano**\n"
                f"- Valorização esperada: **{pct(r.get('tendencia_preco_aa'))} ao ano**\n"
                f"- Retorno total esperado: **{pct(r.get('retorno_total_esperado_aa'))} ao ano**\n"
                f"- Maior queda nos últimos 5 anos: {pct(r['queda_max_5a'])}\n"
                f"- Analistas: preço-alvo {brl(r['alvo_analistas'])}" + (f" ({pct(r['potencial_analistas'])})" if r['potencial_analistas'] == r['potencial_analistas'] else "")))
    st.caption("80% de chance de o preço ficar entre o cenário ruim e o bom, segundo o comportamento passado da ação.")

    st.markdown("**❄️ Raio-X comparado ao setor**")
    fatores_ = ["Valor", "Renda", "Qualidade", "Saúde", "Momento"]
    rx1, rx2 = st.columns([2, 3])
    with rx1:
        visual.floco({f_: r.get(f"pct_{f_}", float("nan")) for f_ in fatores_}, {f_: r.get(f"grau_{f_}", "—") for f_ in fatores_})
    with rx2:
        visual.cartoes([
            ("Segurança dos dividendos", f"{r['seguranca_div']:.0f}/100" if r.get("seguranca_div") == r.get("seguranca_div") else "—",
             "checagens aprovadas", "ok" if (r.get("seguranca_div") or 0) >= 70 else "alerta"),
            ("Piotroski (força do balanço)", f"{r['f_score_9']:.0f}/9" if r.get("f_score_9") == r.get("f_score_9") else "—",
             f"{int(r.get('f_testes', 0))} testes possíveis com os dados"),
            ("Preço justo (dividendos descontados)", brl(r.get("preco_justo_ddm")),
             (f"{pct(abs(r['margem_ddm']))} {'acima' if r['margem_ddm'] >= 0 else 'abaixo'} do preço" if r.get("margem_ddm") == r.get("margem_ddm") else ""),
             "ok" if (r.get("margem_ddm") or -1) >= 0 else "alerta"),
            ("Caixa livre que vira dividendo", pct(r.get("payout_fcl"), 0) if r.get("payout_fcl") not in (None, float("inf")) else
             ("caixa negativo" if r.get("payout_fcl") == float("inf") else "—"), "abaixo de 100% = dividendo coberto"),
        ])
        with st.expander("Ver cada checagem"):
            st.markdown("**Segurança dos dividendos**\n\n" + "\n".join(f"- {c}" for c in (r.get("seguranca_checks") if isinstance(r.get("seguranca_checks"), list) else ["sem dados"])))
            st.markdown("**Piotroski F-score**\n\n" + "\n".join(f"- {c}" for c in (r.get("f_detalhe") if isinstance(r.get("f_detalhe"), list) else ["sem balanços disponíveis"])))
            st.caption(f"Preço justo por Gordon: proventos médios × (1 + crescimento até 5%) ÷ (taxa exigida − crescimento); "
                       f"taxa exigida hoje = {pct(r.get('taxa_desconto'))}, que sobe quando a Selic sobe.")

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
with abas[10]:
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
with abas[11]:
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
                            scale=alt.Scale(domain=list(nomes_b.values()), range=[visual.DESTAQUE, visual.AZUL, "#B388FF", visual.CINZA])),
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
with abas[12]:
    if not R["alertas"]:
        st.success("Nenhum alerta hoje.")
    icones = {"Oportunidade": "🟢", "Queda forte": "📉", "Provento": "💰", "Data-com": "📅", "Ranking": "🏆",
              "Carteira": "⚠️", "Notícia": "📰"}
    tipos = sorted({a["tipo"] for a in R["alertas"]})
    escolha = st.multiselect("Tipos", tipos, default=tipos)
    for a in R["alertas"]:
        if a["tipo"] in escolha:
            (st.warning if a["nivel"] == 1 else st.info)(md(f"{icones.get(a['tipo'], '•')} **{a['tipo']}** — {a['texto']}"))

# ======================================================================= COMO FUNCIONA
with abas[13]:
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
