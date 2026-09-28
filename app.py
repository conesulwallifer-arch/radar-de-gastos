"""Radar de Gastos — app local para navegar em cada gasto e nos alertas.
Rode:  streamlit run app.py
"""
import duckdb
import pandas as pd
import streamlit as st

from radar.detectores import CATALOGO
from radar.util import DADOS
from radar.publico import PUBLICO, atualizado_em, garantir_banco

st.set_page_config(page_title="Radar de Gastos", page_icon="🔎", layout="wide")
if PUBLICO:
    with st.spinner("Carregando a base de dados (só na primeira abertura)..."):
        garantir_banco()
def CURTO(v):
    v = float(v)
    for lim, suf in ((1e12, "tri"), (1e9, "bi"), (1e6, "mi"), (1e3, "mil")):
        if abs(v) >= lim:
            return f"R$ {v/lim:,.1f} {suf}".replace(",", "X").replace(".", ",").replace("X", ".")
    return BRL(v)


BRL = lambda v: ("R$ {:,.2f}".format(v)).replace(",", "X").replace(".", ",").replace("X", ".")


@st.cache_resource
def conexao():
    return duckdb.connect(str(DADOS / "radar.duckdb"), read_only=True)


con = conexao()
q = lambda sql, *p: con.execute(sql, list(p)).df()


def fmt_doc(d: str) -> str:
    d = str(d or "")
    if d.startswith("***"):  # CPF ocultado na versão pública (LGPD)
        return f"***.{d[3:6]}.{d[6:9]}-**"
    if len(d) == 14: return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    if len(d) == 11: return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    return d or "—"


@st.cache_data(show_spinner=False, ttl=3600)
def baixar_documento(url: str):
    """Busca o documento original (PDF ou página da NF-e) para mostrar dentro do app."""
    import requests
    try:
        r = requests.get(url, timeout=25, headers={"User-Agent": "Mozilla/5.0 RadarGastos"})
        r.raise_for_status()
        return r.headers.get("content-type", ""), r.content
    except Exception as e:  # noqa: BLE001
        return "erro", str(e).encode()


def _exibir_arquivo(url: str, chave: str):
    """Mostra um arquivo (PDF, página HTML ou outro) dentro do app."""
    with st.spinner("Carregando o documento..."):
        tipo, dados = baixar_documento(url)
    if tipo == "erro":
        st.warning("Não consegui carregar o documento aqui dentro. Use o botão para abrir no navegador.")
    elif "pdf" in tipo or dados[:4] == b"%PDF":
        try:
            st.pdf(dados, height=750, key=chave)
        except TypeError:
            st.pdf(dados, height=750)
        except Exception:  # noqa: BLE001  (falta o pacote streamlit-pdf)
            st.download_button("Baixar PDF", dados, file_name="documento.pdf", mime="application/pdf", key=chave)
    elif "html" in tipo:
        import streamlit.components.v1 as components
        html = dados.decode("utf-8", "ignore")
        base = url.rsplit("/", 1)[0] + "/"
        components.html(f'<base href="{base}" target="_blank">' + html, height=750, scrolling=True)
    else:
        st.download_button("Baixar documento", dados, file_name="documento", key=chave)


@st.cache_data(show_spinner=False, ttl=3600)
def arquivos_pncp(cnpj: str, ano: str, seq: str) -> list[dict]:
    """Lista os documentos anexados ao contrato no PNCP (contrato, termos, empenho, notas...)."""
    import requests
    base = f"https://pncp.gov.br/api/pncp/v1/orgaos/{cnpj}/contratos/{ano}/{seq}/arquivos"
    try:
        r = requests.get(base, timeout=30, headers={"User-Agent": "Mozilla/5.0 RadarGastos"})
        itens = r.json() if r.ok else []
    except Exception:  # noqa: BLE001
        itens = []
    saida = []
    for i, it in enumerate(itens if isinstance(itens, list) else []):
        u = it.get("url") or it.get("uri") or f"{base}/{it.get('sequencialDocumento', i + 1)}"
        saida.append({"titulo": it.get("titulo") or it.get("tipoDocumentoNome") or f"Documento {i + 1}",
                      "tipo": it.get("tipoDocumentoNome") or "", "url": u,
                      "data": str(it.get("dataPublicacaoPncp") or "")[:10]})
    return saida


def chave_nfe(*textos) -> str:
    """Procura uma chave de acesso de NF-e (44 dígitos) no nº/descrição."""
    import re
    for t in textos:
        m = re.search(r"(\d[\d .]{42,70})", str(t or ""))
        if m:
            d = re.sub(r"\D", "", m.group(1))
            if len(d) >= 44:
                return d[:44]
    return ""


def pedido_lai(r) -> str:
    orgao = r["politico_nome"] if r["cargo"] == "Órgão municipal" else r.get("fonte", "")
    data = pd.Timestamp(r["data"]).strftime("%d/%m/%Y") if pd.notna(r["data"]) else "—"
    return (f"Com base na Lei 12.527/2011 (Lei de Acesso à Informação), solicito cópia integral da(s) NOTA(S) FISCAL(IS) "
            f"(NF-e/NFS-e, com chave de acesso) e dos comprovantes de liquidação e pagamento referentes à despesa abaixo:\n\n"
            f"- Órgão/responsável: {orgao}\n- Fornecedor: {r['fornecedor']} (CNPJ/CPF {fmt_doc(r['fornecedor_doc'])})\n"
            f"- Nº do documento/empenho/contrato: {r['documento'] or '—'}\n- Data: {data}\n- Valor: {BRL(r['valor'])}\n"
            f"- Objeto: {str(r.get('descricao') or r.get('categoria') or '').strip()}\n\n"
            f"Solicito também a identificação do fiscal do contrato e o atestado de recebimento do bem/serviço.")


def mostrar_documento(url: str, r=None):
    url = str(url or "")
    chave = chave_nfe(r["documento"], r.get("descricao")) if r is not None else ""
    if chave:
        st.success(f"Chave de acesso da NF-e encontrada: `{chave}`")
        st.link_button("Consultar esta NF-e no Portal Nacional da NF-e (SEFAZ)",
                       "https://www.nfe.fazenda.gov.br/portal/consultaRecaptcha.aspx?tipoConsulta=resumo&tipoConteudo=7PhJ+gAVw2g=")
        st.caption("No portal, cole a chave acima e resolva o captcha para ver o DANFE.")
    if "pncp.gov.br/app/contratos/" in url:
        cnpj, ano, seq = url.rstrip("/").split("/")[-3:]
        st.link_button("Abrir o contrato no PNCP", url)
        arqs = arquivos_pncp(cnpj, ano, seq)
        if not arqs:
            st.info("O órgão não anexou arquivos a este contrato no PNCP (ou o PNCP não respondeu agora).")
        else:
            nomes = [f"{a['titulo']} {('· ' + a['tipo']) if a['tipo'] and a['tipo'] not in a['titulo'] else ''} {a['data']}".strip() for a in arqs]
            esc = st.selectbox(f"{len(arqs)} documento(s) anexado(s) ao contrato", range(len(arqs)), format_func=lambda i: nomes[i],
                               key=f"arq_{cnpj}_{ano}_{seq}")
            st.link_button("Abrir este documento no navegador", arqs[esc]["url"])
            _exibir_arquivo(arqs[esc]["url"], f"pdf_{cnpj}_{ano}_{seq}_{esc}")
    elif url:
        st.link_button("Abrir documento original no site", url)
        _exibir_arquivo(url, f"pdf_{abs(hash(url))}")
    elif not chave:
        st.info("A imagem da nota fiscal desta despesa não é publicada pela fonte. O TSE e o Senado divulgam só os dados "
                "(fornecedor, CNPJ, nº, valor, data); a Câmara dos Deputados é a única que publica cada nota. "
                "Para despesas da prefeitura/câmara municipal, a NF fica no processo de pagamento.")
    if r is not None and (not url or "pncp.gov.br" in url) and not chave:
        with st.expander("📨 Pedir a nota fiscal pela Lei de Acesso à Informação (texto pronto)"):
            st.caption("Copie e envie pelo e-SIC do órgão (prefeitura, câmara, TSE/TRE ou Senado). O prazo legal de resposta é de 20 dias.")
            st.code(pedido_lai(r), language=None, wrap_lines=True)


def ficha_nota(gid: str):
    """Tudo sobre uma transação: dados, documento, alertas, empresa e outros pagamentos."""
    r = con.execute("SELECT * FROM gastos WHERE id = ?", [gid]).df()
    if r.empty:
        return
    r = r.iloc[0]
    st.markdown("---")
    st.subheader(f"Nota de {r['fornecedor']}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Valor", BRL(r["valor"]))
    c2.metric("Data", pd.Timestamp(r["data"]).strftime("%d/%m/%Y") if pd.notna(r["data"]) else "—")
    c3.metric("Nº do documento", r["documento"] or "—")
    c4.metric("CNPJ/CPF", fmt_doc(r["fornecedor_doc"]))
    st.caption(f"{r['politico_nome']} · {r['cargo']} · {r['fonte']} · {r['categoria']}")
    if str(r.get("descricao") or "").strip():
        st.write(f"**Descrição / objeto:** {r['descricao']}")

    als = con.execute("SELECT gravidade, titulo, detalhe, codigo FROM alertas WHERE gasto_id = ? OR list_contains(string_split(gastos_ids, ','), ?)",
                      [gid, gid]).df()
    for a in als.itertuples():
        cor = {3: "🔴", 2: "🟠", 1: "🟡"}[a.gravidade]
        st.markdown(f"{cor} **{a.titulo}** — {a.detalhe}  \n<small>{CATALOGO[a.codigo][2]}</small>", unsafe_allow_html=True)

    t_doc, t_emp, t_outros = st.tabs(["📄 Documento", "🏢 Empresa", "🔁 Outros pagamentos a este fornecedor"])
    with t_doc:
        mostrar_documento(str(r["url_doc"] or ""), r)
    with t_emp:
        tabelas = q("SHOW TABLES")["name"].tolist()
        emp = q("SELECT * FROM empresas WHERE cnpj = ?", r["fornecedor_doc"]) if "empresas" in tabelas else pd.DataFrame()
        if emp.empty:
            st.info("Sem dados da Receita para este fornecedor (só os CNPJs de maior valor são consultados).")
        else:
            e = emp.iloc[0]
            v = lambda k: "—" if k not in e or pd.isna(e[k]) or str(e[k]).strip() == "" else e[k]
            ab = pd.Timestamp(e["abertura"]).strftime("%d/%m/%Y") if pd.notna(e.get("abertura")) else "—"
            st.write(f"**Abertura:** {ab} · **Situação:** {v('situacao')} · **Porte:** {v('porte')}")
            st.write(f"**Atividade:** {v('cnae')}")
            cap = BRL(float(e["capital"])) if pd.notna(e.get("capital")) else "—"
            st.write(f"**Local:** {v('municipio_empresa')}/{v('uf_empresa')} · **Capital social:** {cap}")
            st.write(f"**Sócios:** {v('socios')}")
        if "sancoes" in tabelas:
            sc = q("SELECT cadastro, tipo, orgao, inicio, fim FROM sancoes WHERE doc = ?", r["fornecedor_doc"])
            if not sc.empty:
                st.error("Empresa consta no cadastro de punidas da CGU:")
                st.dataframe(sc, hide_index=True, width="stretch")
    with t_outros:
        o = q("""SELECT politico_nome, cargo, uf, count(*) notas, sum(valor) total, min(data) primeira, max(data) ultima
                 FROM gastos WHERE fornecedor_doc = ? GROUP BY ALL ORDER BY total DESC""", r["fornecedor_doc"])
        st.dataframe(o, hide_index=True, width="stretch", column_config={
            "total": st.column_config.NumberColumn("Total (R$)", format="localized"),
            "primeira": st.column_config.DateColumn("Primeira", format="DD/MM/YYYY"),
            "ultima": st.column_config.DateColumn("Última", format="DD/MM/YYYY")})


COLCFG_NOTAS = {
    "url_doc": st.column_config.LinkColumn("Documento", display_text="Abrir"),
    "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
    "valor": st.column_config.NumberColumn("Valor (R$)", format="localized"),
    "fornecedor_doc": "CNPJ/CPF", "documento": "Nº da nota", "fonte": "Fonte", "categoria": "Categoria",
    "fornecedor": "Fornecedor", "alerta": "⚠️", "descricao": "Descrição / objeto", "documento_status": "Imagem da nota"}


def tabela_notas(g: pd.DataFrame, key: str):
    """Tabela de notas: clique numa linha para abrir a ficha completa com o documento."""
    st.caption("Clique numa linha para ver o documento e a ficha completa da transação.")
    cols = [c for c in ["alerta", "data", "fonte", "categoria", "fornecedor", "fornecedor_doc", "documento", "valor", "descricao", "url_doc"] if c in g]
    g = g.reset_index(drop=True)
    if "fornecedor_doc" in g:
        g["fornecedor_doc"] = g["fornecedor_doc"].map(lambda d: fmt_doc(d) if d else "")
    link = g["url_doc"].fillna("").astype(str)
    g["url_doc"] = link.where(link.str.startswith("http"), None)
    g["documento_status"] = link.map(lambda u: "📄 tem imagem" if u.startswith("http") else "sem imagem (fonte não publica)")
    cols = cols + ["documento_status"]
    ev = st.dataframe(g[cols], width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row",
                      key=key, column_config=COLCFG_NOTAS)
    if ev.selection.rows:
        ficha_nota(g.iloc[ev.selection.rows[0]]["id"])


def notas_do_alerta(ids: str, key: str = "al"):
    """Todas as notas por trás de um alerta, cada uma abrindo a ficha com o documento."""
    lista = [i for i in str(ids or "").split(",") if i and i != "None"]
    if not lista:
        st.caption("Alerta sobre o conjunto dos gastos do político (não aponta uma nota específica).")
        return
    g = con.execute("SELECT id, data, fonte, categoria, fornecedor, fornecedor_doc, documento, valor, descricao, url_doc FROM gastos "
                    "WHERE id IN (SELECT unnest(?)) ORDER BY data", [lista]).df()
    tabela_notas(g, key)

st.title("🔎 Radar de Gastos")
st.caption("Cota parlamentar (Câmara e Senado) e gastos de campanha (TSE) de deputados, senadores, prefeitos e vereadores. "
           "Alertas são indícios automáticos para verificação — não são prova de irregularidade.")
if PUBLICO:
    st.info("**Fiscalização cidadã com dados 100% oficiais e públicos** (Câmara, Senado, TSE, PNCP, Receita, CGU e Tesouro). "
            "Escolha seu estado e sua cidade na barra lateral (no celular, toque em » no canto de cima), clique num político para ver a ficha e cobrar. "
            "Os alertas são **indícios automáticos**, não acusação: confira o documento original e peça explicação antes de "
            "concluir qualquer coisa. CPFs de pessoas físicas aparecem ocultos (LGPD)."
            + (f"  \nDados atualizados em **{atualizado_em()}**." if atualizado_em() else ""), icon="ℹ️")

pol = q("SELECT * FROM politicos")
with st.sidebar:
    st.header("Filtros")
    cargos = st.multiselect("Cargo", sorted(pol["cargo"].dropna().unique()))
    ufs = st.multiselect("UF", sorted(pol["uf"].dropna().unique()))
    muns = st.multiselect("Município", sorted(pol[pol["uf"].isin(ufs) if ufs else pol.index == pol.index]["municipio"].dropna().replace("", pd.NA).dropna().unique()))
    busca = st.text_input("Nome do político")
    st.subheader("Período")
    # ignora datas digitadas erradas na origem (ex.: ano 0023 ou 2049)
    import datetime as _dt
    ano_max = _dt.date.today().year
    anos = [int(a) for (a,) in con.execute(
        "SELECT DISTINCT year(data) a FROM gastos WHERE year(data) BETWEEN 2018 AND ? ORDER BY a", [ano_max]).fetchall()]
    dmin, dmax = con.execute("SELECT min(data), max(data) FROM gastos WHERE year(data) BETWEEN 2018 AND ?", [ano_max]).fetchone()
    dmin, dmax = pd.Timestamp(dmin).date(), pd.Timestamp(dmax).date()
    atalho = st.radio("Atalho", ["Tudo"] + [str(a) for a in anos] + ["Escolher datas"], horizontal=True, label_visibility="collapsed")
    if atalho == "Tudo":
        de, ate = dmin, dmax
    elif atalho == "Escolher datas":
        faixa = st.date_input("De / até", value=(dmin, dmax), min_value=dmin, max_value=dmax, format="DD/MM/YYYY")
        de, ate = (faixa if isinstance(faixa, tuple) and len(faixa) == 2 else (dmin, dmax))
    else:
        de, ate = _dt.date(int(atalho), 1, 1), _dt.date(int(atalho), 12, 31)
    com_periodo = atalho != "Tudo"
de_s, ate_s = str(de), str(ate)

# totais e alertas recalculados dentro do período
if com_periodo:
    tot_p = q("""SELECT politico_id, sum(valor) total, count(*) n_gastos FROM gastos
                 WHERE data BETWEEN ? AND ? GROUP BY 1""", de_s, ate_s)
    al_p = q("""SELECT a.politico_id, count(*) n_alertas FROM alertas a JOIN gastos g ON g.id = a.gasto_id
                WHERE g.data BETWEEN ? AND ? GROUP BY 1""", de_s, ate_s)
    pol = pol.drop(columns=["total", "n_gastos", "n_alertas"]).merge(tot_p, on="politico_id", how="inner").merge(al_p, on="politico_id", how="left")
    pol["n_alertas"] = pol["n_alertas"].fillna(0).astype(int)
f = pol.copy()
if cargos: f = f[f["cargo"].isin(cargos)]
if ufs: f = f[f["uf"].isin(ufs)]
if muns: f = f[f["municipio"].isin(muns)]
if busca: f = f[f["nome"].str.contains(busca, case=False, na=False)]

aba_rank, aba_imp, aba1, aba2, aba3 = st.tabs(["🏆 Ranking de gastos", "🧾 Impostômetro", "Políticos", "Todos os alertas", "Fornecedor (CNPJ/CPF)"])

AZUL, VERMELHO = "#3987e5", "#e34948"


def grafico_barras(df, rotulo_col, valor_col, cor_col=None, altura_linha=30, formato_valor=CURTO, tooltip_extra=()):
    """Barras horizontais ordenadas, com o valor escrito na ponta de cada barra."""
    import altair as alt
    df = df.sort_values(valor_col, ascending=False).drop_duplicates(rotulo_col).copy()
    df["_txt"] = df[valor_col].map(formato_valor)
    ordem = df[rotulo_col].tolist()
    base = alt.Chart(df).encode(
        y=alt.Y(f"{rotulo_col}:N", sort=ordem, title=None, axis=alt.Axis(labelLimit=320, labelFontSize=12)),
        x=alt.X(f"{valor_col}:Q", title=None, axis=alt.Axis(labels=False, ticks=False, grid=False, domain=False)),
        tooltip=[alt.Tooltip(f"{rotulo_col}:N", title="Nome"), alt.Tooltip("_txt:N", title="Valor"), *tooltip_extra])
    if cor_col:
        cor = alt.Color(f"{cor_col}:N", title=None, legend=alt.Legend(orient="top"),
                        scale=alt.Scale(domain=["Com alerta grave", "Sem alerta grave"], range=[VERMELHO, AZUL]))
    else:
        cor = alt.value(AZUL)
    barras = base.mark_bar(cornerRadiusEnd=4, height=altura_linha * 0.62).encode(color=cor)
    textos = base.mark_text(align="left", dx=6, fontSize=12, fontWeight="bold", color="#8a8a86").encode(text="_txt:N")
    ch = (barras + textos).properties(height=max(160, altura_linha * len(df)))
    ch = ch.configure_view(strokeWidth=0).configure_axis(labelColor="#8a8a86")
    st.altair_chart(ch, width="stretch")


with aba_rank:
    c1, c2, c3 = st.columns(3)
    quem = c1.radio("Mostrar", ["Políticos", "Órgãos municipais", "Todos"], horizontal=True, key="rk_quem")
    n_top = c2.select_slider("Quantos no ranking", options=[10, 15, 20, 30, 50], value=20, key="rk_n")
    medida = c3.radio("Ordenar por", ["Total gasto", "Nº de alertas"], horizontal=True, key="rk_med")
    base_r = f.copy()
    if quem == "Políticos":
        base_r = base_r[base_r["cargo"] != "Órgão municipal"]
    elif quem == "Órgãos municipais":
        base_r = base_r[base_r["cargo"] == "Órgão municipal"]
    graves = q("SELECT politico_id, count(*) graves FROM alertas WHERE gravidade = 3 GROUP BY 1")
    base_r = base_r.merge(graves, on="politico_id", how="left").fillna({"graves": 0})
    base_r["situacao"] = base_r["graves"].map(lambda x: "Com alerta grave" if x > 0 else "Sem alerta grave")
    base_r["rotulo"] = base_r["nome"].str.slice(0, 40) + "  ·  " + base_r["cargo"].fillna("") + " " + base_r["uf"].fillna("")
    col_val = "total" if medida == "Total gasto" else "n_alertas"
    top = base_r.nlargest(n_top, col_val)
    k1, k2, k3 = st.columns(3)
    k1.metric("Gasto somado no ranking", CURTO(top["total"].sum()))
    k2.metric("Participação no total filtrado", f"{100 * top['total'].sum() / max(base_r['total'].sum(), 1):.0f}%".replace(".", ","))
    k3.metric("Com alerta grave", f"{int((top['graves'] > 0).sum())} de {len(top)}")
    st.subheader(f"Top {n_top} — {'maiores gastos' if col_val == 'total' else 'mais alertas'}"
                 + (" no período" if com_periodo else ""))
    if top.empty:
        st.info("Nada para mostrar com esses filtros.")
    else:
        import altair as alt
        grafico_barras(top, "rotulo", col_val, "situacao",
                       formato_valor=CURTO if col_val == "total" else (lambda v: f"{int(v)} alertas"),
                       tooltip_extra=(alt.Tooltip("partido:N", title="Partido"), alt.Tooltip("municipio:N", title="Município"),
                                      alt.Tooltip("n_gastos:Q", title="Notas", format=",d"),
                                      alt.Tooltip("n_alertas:Q", title="Alertas"), alt.Tooltip("graves:Q", title="Alertas graves")))
        st.caption("Vermelho = tem pelo menos um alerta grave (empresa punida, nota duplicada, doador contratado etc.). "
                   "Clique no nome na aba Políticos para ver cada nota.")

    ids = base_r["politico_id"].tolist()
    if ids:
        g_r = con.execute("""SELECT fornecedor, fornecedor_doc, sum(valor) total, count(*) notas, count(DISTINCT politico_id) pagadores
                             FROM gastos WHERE politico_id IN (SELECT unnest(?)) AND data BETWEEN ? AND ?
                             GROUP BY 1, 2 ORDER BY total DESC LIMIT ?""", [ids, de_s, ate_s, n_top]).df()
        mes = con.execute("""SELECT date_trunc('month', data) mes, sum(valor) total FROM gastos
                             WHERE politico_id IN (SELECT unnest(?)) AND data BETWEEN ? AND ? GROUP BY 1 ORDER BY 1""",
                          [ids, de_s, ate_s]).df()
        part = base_r[base_r["partido"].fillna("") != ""].groupby("partido", as_index=False)["total"].sum().nlargest(15, "total")
        l, r_ = st.columns(2)
        with l:
            st.subheader("Quem mais recebeu (fornecedores)")
            if not g_r.empty:
                import altair as alt
                g_r["rotulo"] = g_r["fornecedor"].fillna("").str.slice(0, 38)
                grafico_barras(g_r, "rotulo", "total", altura_linha=26,
                               tooltip_extra=(alt.Tooltip("fornecedor_doc:N", title="CNPJ/CPF"), alt.Tooltip("notas:Q", title="Notas"),
                                              alt.Tooltip("pagadores:Q", title="Nº de pagadores")))
        with r_:
            st.subheader("Gasto por partido")
            if not part.empty:
                grafico_barras(part, "partido", "total", altura_linha=26)
        st.subheader("Evolução mês a mês")
        if not mes.empty:
            import altair as alt
            mes["txt"] = mes["total"].map(CURTO)
            MESES = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
            mes["rot"] = pd.to_datetime(mes["mes"]).map(lambda d: f"{MESES[d.month - 1]}/{str(d.year)[2:]}")
            ch = alt.Chart(mes).mark_bar(color=AZUL, cornerRadiusTopLeft=4, cornerRadiusTopRight=4).encode(
                x=alt.X("rot:N", sort=mes["rot"].tolist(), title=None, axis=alt.Axis(labelAngle=0, labelOverlap=True)),
                y=alt.Y("total:Q", title=None, axis=alt.Axis(labels=False, grid=True, gridOpacity=0.15, ticks=False, domain=False)),
                tooltip=[alt.Tooltip("rot:N", title="Mês"), alt.Tooltip("txt:N", title="Gasto")]
            ).properties(height=260).configure_view(strokeWidth=0).configure_axis(labelColor="#8a8a86")
            st.altair_chart(ch, width="stretch")

with aba_imp:
    from impostometro_ui import render as _render_impostometro
    _render_impostometro(CURTO)


def detalhe_politico(p, eh_orgao: bool):
    st.divider()
    g = q("SELECT * FROM gastos WHERE politico_id = ? AND data BETWEEN ? AND ? ORDER BY data DESC", p["politico_id"], de_s, ate_s)
    a = q("""SELECT a.* FROM alertas a LEFT JOIN gastos g ON g.id = a.gasto_id WHERE a.politico_id = ?
             AND (g.data BETWEEN ? AND ? OR (a.gasto_id IS NULL AND NOT ?))
             ORDER BY a.gravidade DESC, a.valor DESC""", p["politico_id"], de_s, ate_s, com_periodo)
    if eh_orgao:
        st.header(f"🏛️ {p['nome']}")
        cnpj = str(p["politico_id"]).replace("ORGP-", "").replace("ORG-", "")
        st.caption(f"{str(p['municipio']).title() if pd.notna(p['municipio']) else ''} / {p['uf']} · CNPJ {fmt_doc(cnpj) if cnpj.isdigit() else '—'} · "
                   "gastos vindos dos contratos publicados no PNCP e das planilhas dos portais de transparência.")
        if cnpj.isdigit():
            st.link_button("📑 Contratos deste órgão no PNCP", f"https://pncp.gov.br/app/contratos?q={cnpj}")
    else:
        st.header(f"{p['nome']} — {p['cargo']} ({p['partido']}/{p['uf']})")
        g_todo = q("SELECT data, valor FROM gastos WHERE politico_id = ?", p["politico_id"])
        from perfil_ui import ficha
        ficha(p, con, g_todo, a, BRL, CURTO)
        st.divider()
        st.subheader("💸 Gastos")
    c1, c2, c3 = st.columns(3)
    c1.metric("Total gasto", CURTO(g["valor"].sum())); c2.metric("Notas", len(g)); c3.metric("Índice de atenção", int(p["indice"]))
    if not a.empty:
        st.subheader("Alertas")
        for r in a.itertuples():
            cor = {3: "🔴", 2: "🟠", 1: "🟡"}[r.gravidade]
            with st.expander(f"{cor} {r.titulo} — {r.detalhe} · {BRL(r.valor)}"):
                st.caption(CATALOGO[r.codigo][2])
                notas_do_alerta(r.gastos_ids, key=f"alp_{p['politico_id']}_{r.Index}")
    t_forn, t_cat = st.tabs(["🏢 Maiores fornecedores", "📊 Por categoria"])
    with t_forn:
        tot_pol = float(g["valor"].sum()) or 1.0
        fz = (g.groupby(["fornecedor_doc"], dropna=False)
              .agg(fornecedor=("fornecedor", "first"), total=("valor", "sum"), notas=("valor", "size"),
                   primeira=("data", "min"), ultima=("data", "max"))
              .reset_index().sort_values("total", ascending=False).head(30))
        fz["pct"] = (100 * fz["total"] / tot_pol).round(1)
        fz["doc_fmt"] = fz["fornecedor_doc"].map(fmt_doc)
        fz["alerta"] = fz["fornecedor_doc"].isin(g.loc[g["id"].isin(a["gasto_id"]), "fornecedor_doc"])
        st.caption("Clique num fornecedor para ver só as notas dele.")
        evf = st.dataframe(
            fz[["alerta", "fornecedor", "doc_fmt", "total", "pct", "notas", "primeira", "ultima"]],
            width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row",
            key=f"forn_{p['politico_id']}",
            column_config={
                "alerta": st.column_config.CheckboxColumn("⚠️", help="Tem nota com alerta", width="small"),
                "fornecedor": st.column_config.TextColumn("Fornecedor", width="large"),
                "doc_fmt": st.column_config.TextColumn("CNPJ/CPF", width="medium"),
                "total": st.column_config.NumberColumn("Total recebido (R$)", format="localized"),
                "pct": st.column_config.ProgressColumn("% do gasto", min_value=0, max_value=100, format="%.1f%%"),
                "notas": st.column_config.NumberColumn("Notas", width="small"),
                "primeira": st.column_config.DateColumn("Primeira", format="DD/MM/YYYY"),
                "ultima": st.column_config.DateColumn("Última", format="DD/MM/YYYY")})
        if evf.selection.rows:
            doc_sel = fz.iloc[evf.selection.rows[0]]["fornecedor_doc"]
            st.markdown(f"**Notas de {fz.iloc[evf.selection.rows[0]]['fornecedor']}**")
            tabela_notas(g[g["fornecedor_doc"] == doc_sel], key=f"fornotas_{p['politico_id']}")
    with t_cat:
        cz = g.groupby("categoria")["valor"].agg(["sum", "size"]).sort_values("sum", ascending=False).reset_index()
        cz["pct"] = (100 * cz["sum"] / (float(g["valor"].sum()) or 1)).round(1)
        st.dataframe(cz, width="stretch", hide_index=True, column_config={
            "categoria": st.column_config.TextColumn("Categoria", width="large"),
            "sum": st.column_config.NumberColumn("Total (R$)", format="localized"),
            "size": st.column_config.NumberColumn("Notas"),
            "pct": st.column_config.ProgressColumn("% do gasto", min_value=0, max_value=100, format="%.1f%%")})
    st.subheader("Todos os gastos")
    g["alerta"] = g["id"].isin(a["gasto_id"])
    tabela_notas(g, key=f"gastos_{p['politico_id']}")



def tabela_ranking(df, key):
    tab = df[["nome", "cargo", "partido", "uf", "municipio", "total", "n_gastos", "n_alertas", "indice", "politico_id"]].reset_index(drop=True)
    ev = st.dataframe(tab.drop(columns="politico_id"), width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row", key=key,
                      column_config={"nome": "Nome", "cargo": "Cargo", "partido": "Partido", "uf": "UF", "municipio": "Município",
                                     "total": st.column_config.NumberColumn("Total gasto (R$)", format="localized"),
                                     "n_gastos": st.column_config.NumberColumn("Notas", format="localized"),
                                     "n_alertas": st.column_config.NumberColumn("Alertas", format="localized"),
                                     "indice": st.column_config.ProgressColumn("Índice de atenção", min_value=0, max_value=100, format="%d")})
    return tab.iloc[ev.selection.rows[0]] if ev.selection.rows else None


with aba1:
    eh_org = f["cargo"].eq("Órgão municipal")
    fp, fo = f[~eh_org], f[eh_org]
    t_pol, t_org = st.tabs([f"👤 Políticos ({len(fp)})", f"🏛️ Prefeitura, Câmara e órgãos municipais ({len(fo)})"])
    with t_pol:
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Políticos", f"{len(fp):,}".replace(",", "."))
        c2.metric("Gasto no período" if com_periodo else "Gasto total", CURTO(fp["total"].sum()))
        c3.metric("Com alerta", f"{(fp['n_alertas'] > 0).sum():,}".replace(",", "."))
        c4.metric("Alertas", f"{fp['n_alertas'].sum():,}".replace(",", "."))
        st.subheader("Ranking por índice de atenção")
        st.caption("Clique num político para ver a ficha: foto, contatos, redes sociais, mandato e onde cobrar.")
        sel = tabela_ranking(fp, "rk_pol")
        if sel is not None:
            detalhe_politico(sel, eh_orgao=False)
    with t_org:
        if fo.empty:
            st.info("Nenhum órgão municipal no recorte. Rode o Atualizar Radar com --municipio para trazer prefeitura e câmara.")
        else:
            c1, c2, c3 = st.columns(3)
            c1.metric("Órgãos", len(fo)); c2.metric("Gasto no período" if com_periodo else "Gasto total", CURTO(fo["total"].sum()))
            c3.metric("Alertas", f"{fo['n_alertas'].sum():,}".replace(",", "."))
            sel = tabela_ranking(fo, "rk_org")
            if sel is not None:
                detalhe_politico(sel, eh_orgao=True)

with aba2:
    a = q("""SELECT a.gravidade, a.titulo, p.nome, p.cargo, p.uf, p.municipio, a.detalhe, a.valor, g.data, g.url_doc, a.gastos_ids
             FROM alertas a JOIN politicos p USING (politico_id) LEFT JOIN gastos g ON g.id = a.gasto_id
             WHERE g.data BETWEEN ? AND ? OR (a.gasto_id IS NULL AND NOT ?)""", de_s, ate_s, com_periodo)
    a = a[a["nome"].isin(f["nome"])]
    tipos = st.multiselect("Tipo de alerta", sorted(a["titulo"].unique()))
    if tipos: a = a[a["titulo"].isin(tipos)]
    a = a.sort_values(["gravidade", "valor"], ascending=False).reset_index(drop=True)
    _l = a["url_doc"].fillna("").astype(str)
    a["url_doc"] = _l.where(_l.str.startswith("http"), None)
    st.caption("Clique numa linha para ver todas as notas do alerta, com o link de cada documento.")
    ev2 = st.dataframe(a.drop(columns="gastos_ids"), width="stretch", hide_index=True, on_select="rerun", selection_mode="single-row",
                       column_order=["gravidade", "titulo", "nome", "cargo", "uf", "detalhe", "valor", "data", "url_doc", "municipio"],
                       column_config={"url_doc": st.column_config.LinkColumn("1ª nota", display_text="Abrir"),
                                      "gravidade": "Grav.", "titulo": "Alerta", "nome": "Político", "cargo": "Cargo", "uf": "UF",
                                      "municipio": "Município", "detalhe": "Detalhe",
                                      "valor": st.column_config.NumberColumn("Valor (R$)", format="localized"),
                                      "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY")})
    if ev2.selection.rows:
        r = a.iloc[ev2.selection.rows[0]]
        st.subheader(f"{r['titulo']} — {r['nome']}")
        st.write(r["detalhe"])
        notas_do_alerta(r["gastos_ids"], key="al_sel")
    with st.expander("O que cada alerta significa"):
        for k, (gv, t, d) in CATALOGO.items():
            st.markdown(f"**{t}** (gravidade {gv}) — {d}")

with aba3:
    doc = st.text_input("CNPJ, CPF ou nome do fornecedor")
    if doc:
        dig = "".join(ch for ch in doc if ch.isdigit())
        if len(dig) >= 8:
            g = q("""SELECT * FROM gastos WHERE fornecedor_doc = ? AND data BETWEEN ? AND ? ORDER BY data DESC""", dig, de_s, ate_s)
        else:
            g = q("""SELECT * FROM gastos WHERE fornecedor ILIKE ? AND data BETWEEN ? AND ? ORDER BY data DESC LIMIT 5000""", f"%{doc}%", de_s, ate_s)
        if g.empty:
            st.info("Nenhuma nota encontrada para esse fornecedor no período.")
        else:
            st.metric("Recebeu no total", CURTO(g["valor"].sum()))
            st.dataframe(g.groupby(["fornecedor", "politico_nome", "cargo", "uf"])["valor"].agg(["sum", "count"])
                         .sort_values("sum", ascending=False).rename(columns={"sum": "Total (R$)", "count": "Notas"}), width="stretch")
            tabela_notas(g.rename(columns={}), key="forn")
