"""Ficha do político: foto, contatos, redes sociais, mandato e o botão de cobrar."""
from __future__ import annotations

import datetime as dt
import json
import re
import time
import unicodedata
import urllib.parse as up

import pandas as pd
import requests
import streamlit as st

from radar.util import DADOS, UA

PASTA = DADOS / "bruto" / "perfis"
CAMARA = "https://dadosabertos.camara.leg.br/api/v2"
SENADO = "https://legis.senado.leg.br/dadosabertos"
HEAD = {**UA, "Accept": "application/json"}


def _n(s) -> str:
    return re.sub(r"\s+", " ", "".join(c for c in unicodedata.normalize("NFKD", str(s or ""))
                                       if not unicodedata.combining(c))).strip().upper()


def _get_json(url: str, chave: str, dias: float = 7):
    """GET com cache em disco (dados/bruto/perfis)."""
    arq = PASTA / (re.sub(r"[^\w.-]", "_", chave) + ".json")
    if arq.exists() and time.time() - arq.stat().st_mtime < dias * 86400:
        return json.loads(arq.read_text(encoding="utf-8"))
    try:
        r = requests.get(url, headers=HEAD, timeout=25)
        if r.status_code != 200:
            return None
        js = r.json()
    except Exception:  # noqa: BLE001
        return json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
    PASTA.mkdir(parents=True, exist_ok=True)
    arq.write_text(json.dumps(js, ensure_ascii=False), encoding="utf-8")
    return js


def _achar(obj, chave):
    """Procura uma chave em qualquer nível do JSON (a API do Senado muda a estrutura às vezes)."""
    if isinstance(obj, dict):
        if chave in obj:
            return obj[chave]
        for v in obj.values():
            r = _achar(v, chave)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _achar(v, chave)
            if r is not None:
                return r
    return None


def _lista(x):
    return x if isinstance(x, list) else ([] if x is None else [x])


def _data(s):
    try:
        return pd.Timestamp(str(s)[:10]).date()
    except Exception:  # noqa: BLE001
        return None


def mesmo_nome(nome: str, *candidatos) -> bool:
    """Confere se a ficha encontrada é mesmo da pessoa (evita puxar homônimo ou código errado)."""
    alvo = {t for t in _n(nome).split() if len(t) > 2}
    if not alvo:
        return False
    for c in candidatos:
        tok = {t for t in _n(c).split() if len(t) > 2}
        if tok and (len(alvo & tok) >= 2 or alvo <= tok or tok <= alvo):
            return True
    return False


# --------------------------------------------------------------------- fontes
@st.cache_data(ttl=86400, show_spinner=False)
def perfil_camara(dep_id: str, nome: str = "", uf: str = "") -> dict | None:
    js = _get_json(f"{CAMARA}/deputados/{dep_id}", f"cd_{dep_id}") if dep_id else None
    def ok(j):
        if not j:
            return False
        us = j["dados"].get("ultimoStatus") or {}
        if uf and us.get("siglaUf") and us["siglaUf"].upper() != uf.upper():
            return False
        return mesmo_nome(nome, us.get("nomeEleitoral"), us.get("nome"), j["dados"].get("nomeCivil"))
    if not ok(js) and nome:
        # código não bate com o nome: procura pelo nome (e UF) entre os deputados
        js = None
        toks = nome.split()
        termos = list(dict.fromkeys([nome] + ([f"{toks[0]} {toks[-1]}", f"{toks[0]} {toks[1]}"] if len(toks) > 2 else [])))
        for q_uf, termo in [(u, t) for t in termos for u in ([uf] if uf else [""])]:
            busca = _get_json(f"{CAMARA}/deputados?nome={up.quote(termo)}&siglaUf={q_uf}&itens=10",
                              f"cd_busca_{termo}_{q_uf}", 30)
            for d in (busca or {}).get("dados") or []:
                cand = _get_json(f"{CAMARA}/deputados/{d['id']}", f"cd_{d['id']}")
                if ok(cand):
                    js, dep_id = cand, str(d["id"])
                    break
            if js:
                break
    if not js:
        return None
    d = js["dados"]
    us = d.get("ultimoStatus") or {}
    gab = us.get("gabinete") or {}
    hist = (_get_json(f"{CAMARA}/deputados/{dep_id}/historico", f"cd_hist_{dep_id}") or {}).get("dados") or []
    legs = sorted({h.get("idLegislatura") for h in hist if h.get("idLegislatura")})
    ext = (_get_json(f"{CAMARA}/deputados/{dep_id}/mandatosExternos", f"cd_ext_{dep_id}") or {}).get("dados") or []
    leg = us.get("idLegislatura") or (legs[-1] if legs else None)
    ini = dt.date(1795 + 4 * int(leg), 2, 1) if leg else None
    return {
        "fonte": "Câmara dos Deputados",
        "foto": us.get("urlFoto"),
        "nome_civil": d.get("nomeCivil"),
        "nome": us.get("nomeEleitoral") or us.get("nome"),
        "partido": us.get("siglaPartido"), "uf": us.get("siglaUf"),
        "situacao": us.get("situacao"), "condicao": us.get("condicaoEleitoral"),
        "email": us.get("email") or gab.get("email"),
        "telefone": ("(61) " + gab["telefone"]) if gab.get("telefone") else None,
        "gabinete": ", ".join(x for x in [f"Gabinete {gab.get('nome')}" if gab.get("nome") else "",
                                          f"Anexo {gab.get('predio')}" if gab.get("predio") else "",
                                          f"{gab.get('andar')}º andar" if gab.get("andar") else ""] if x) or None,
        "nascimento": _data(d.get("dataNascimento")),
        "naturalidade": " / ".join(x for x in [d.get("municipioNascimento"), d.get("ufNascimento")] if x),
        "escolaridade": d.get("escolaridade"),
        "redes": [u for u in (d.get("redeSocial") or []) if u] + ([d["urlWebsite"]] if d.get("urlWebsite") else []),
        "pagina": f"https://www.camara.leg.br/deputados/{dep_id}",
        "mandato_ini": ini, "mandato_fim": dt.date(ini.year + 4, 1, 31) if ini else None,
        "n_mandatos": len(legs),
        "outros_mandatos": [f"{m.get('cargo')} {('de ' + m['municipio']) if m.get('municipio') else ''}/{m.get('siglaUf')} "
                            f"({m.get('anoInicio')}–{m.get('anoFim')})" for m in ext],
        "fala": "https://www.camara.leg.br/participacao/fale-conosco",
        "lai": "https://falabr.cgu.gov.br",
    }


@st.cache_data(ttl=86400, show_spinner=False)
def perfil_senado(cod: str, nome: str = "") -> dict | None:
    if not cod.isdigit():
        lista = _get_json(f"{SENADO}/senador/lista/atual.json", "sf_lista_atual", 7)
        alvo = _n(nome or cod)
        for p in _lista(_achar(lista, "Parlamentar")):
            idp = p.get("IdentificacaoParlamentar", {})
            if alvo in (_n(idp.get("NomeParlamentar")), _n(idp.get("NomeCompletoParlamentar"))):
                cod = str(idp.get("CodigoParlamentar"))
                break
        else:
            return None
    js = _get_json(f"{SENADO}/senador/{cod}.json", f"sf_{cod}")
    if not js:
        return None
    idp = _achar(js, "IdentificacaoParlamentar") or {}
    if nome and not mesmo_nome(nome, idp.get("NomeParlamentar"), idp.get("NomeCompletoParlamentar")):
        return None
    bas = _achar(js, "DadosBasicosParlamentar") or {}
    tels = [t.get("NumeroTelefone") for t in _lista(_achar(js, "Telefone")) if isinstance(t, dict) and t.get("NumeroTelefone")]
    mand = _get_json(f"{SENADO}/senador/{cod}/mandatos.json", f"sf_mand_{cod}")
    mandatos = []
    for m in _lista(_achar(mand, "Mandato")):
        ini = _data((m.get("PrimeiraLegislaturaDoMandato") or {}).get("DataInicio"))
        fim = _data((m.get("SegundaLegislaturaDoMandato") or {}).get("DataFim"))
        if ini:
            mandatos.append((ini, fim, m.get("DescricaoParticipacao") or ""))
    mandatos.sort()
    hoje = dt.date.today()
    atual = next((m for m in reversed(mandatos) if m[0] <= hoje), mandatos[-1] if mandatos else (None, None, ""))
    return {
        "fonte": "Senado Federal",
        "foto": idp.get("UrlFotoParlamentar"),
        "nome_civil": idp.get("NomeCompletoParlamentar"), "nome": idp.get("NomeParlamentar"),
        "partido": idp.get("SiglaPartidoParlamentar"), "uf": idp.get("UfParlamentar"),
        "email": idp.get("EmailParlamentar"),
        "telefone": ", ".join(f"(61) {t}" for t in tels[:3]) or None,
        "gabinete": bas.get("EnderecoParlamentar"),
        "nascimento": _data(bas.get("DataNascimento")),
        "naturalidade": " / ".join(x for x in [bas.get("Naturalidade"), bas.get("UfNaturalidade")] if x),
        "redes": [],
        "pagina": idp.get("UrlPaginaParlamentar") or f"https://www25.senado.leg.br/web/senadores/senador/-/perfil/{cod}",
        "mandato_ini": atual[0], "mandato_fim": atual[1],
        "condicao": atual[2], "n_mandatos": len(mandatos), "outros_mandatos": [],
        "fala": "https://www12.senado.leg.br/institucional/falecomosenado",
        "lai": "https://www12.senado.leg.br/transparencia/sic",
    }


def perfil_tse(con, politico_id: str) -> dict | None:
    """Prefeitos, vereadores e quem só aparece no TSE."""
    pessoa = politico_id[2:] if politico_id.startswith("P-") else None
    if not pessoa:
        return None
    try:
        c = con.execute("SELECT * FROM candidatos WHERE pessoa = ? ORDER BY eleito DESC, ano DESC", [pessoa]).df()
    except Exception:  # noqa: BLE001
        return None
    if c.empty:
        return None
    r = c.iloc[0]
    g = lambda k: (r[k] if k in r and pd.notna(r[k]) and str(r[k]).strip() not in ("", "#NULO#", "#NE#") else None)
    ano, cargo = int(r["ano"]), str(r["cargo"])
    if re.search("prefeit|vereador", cargo, re.I):
        ini, fim = dt.date(ano + 1, 1, 1), dt.date(ano + 4, 12, 31)
    elif re.search("senador", cargo, re.I):
        ini, fim = dt.date(ano + 1, 2, 1), dt.date(ano + 9, 1, 31)
    elif re.search("governador", cargo, re.I):
        # EC 111/2021: eleitos em 2022 tomaram posse em 1º/jan/2023 e ficam até 6/jan/2027; a partir de 2026, posse em 6/jan
        ini = dt.date(ano + 1, 1, 6) if ano >= 2026 else dt.date(ano + 1, 1, 1)
        fim = dt.date(ano + 5, 1, 6) if ano >= 2022 else dt.date(ano + 4, 12, 31)
    elif re.search("presidente", cargo, re.I):
        ini = dt.date(ano + 1, 1, 5) if ano >= 2026 else dt.date(ano + 1, 1, 1)
        fim = dt.date(ano + 5, 1, 5) if ano >= 2022 else dt.date(ano + 4, 12, 31)
    else:
        ini, fim = dt.date(ano + 1, 2, 1), dt.date(ano + 5, 1, 31)
    try:
        redes = con.execute("SELECT DISTINCT url FROM redes WHERE sq = ? AND ano = ?", [str(r["sq"]), ano]).df()["url"].tolist()
    except Exception:  # noqa: BLE001
        redes = []
    foto = None
    if g("cd_eleicao") and g("sg_ue"):
        foto = f"https://divulgacandcontas.tse.jus.br/divulga/rest/arquivo/img/{g('cd_eleicao')}/{r['sq']}/{g('sg_ue')}"
    local = (f"{str(r['municipio']).title()} / {r['uf']}" if re.search("prefeit|vereador", cargo, re.I) else r["uf"])
    anteriores = [f"{x.cargo} {x.ano} — {x.situacao}" for x in c.iloc[1:].itertuples()]
    busca = up.quote(f"{'Câmara Municipal' if 'ereador' in cargo else 'Prefeitura'} de {str(r['municipio']).title()} {r['uf']} {r['nome_urna']} contato")
    return {
        "fonte": "TSE (candidatura)",
        "foto": foto, "nome_civil": r["nome"], "nome": r["nome_urna"], "partido": r["partido"],
        "uf": r["uf"], "local": local, "numero": g("numero"),
        "situacao": f"{r['situacao']} em {ano}", "condicao": None,
        "email": None, "telefone": None, "gabinete": None,
        "nascimento": _data(pd.to_datetime(g("nascimento"), dayfirst=True, errors="coerce")) if g("nascimento") else None,
        "naturalidade": None, "escolaridade": g("instrucao"), "ocupacao": g("ocupacao"),
        "redes": redes, "pagina": None,
        "mandato_ini": ini, "mandato_fim": fim, "n_mandatos": int(c["eleito"].sum()),
        "outros_mandatos": anteriores,
        "fala": f"https://www.google.com/search?q={busca}",
        "lai": f"https://www.google.com/search?q={up.quote('e-SIC ' + ('Câmara Municipal' if 'ereador' in cargo else 'Prefeitura') + ' de ' + str(r['municipio']).title())}",
    }


def _foto_ok(url: str | None) -> bytes | None:
    if not url:
        return None
    arq = PASTA / ("foto_" + re.sub(r"\W", "_", url)[-80:] + ".img")
    if arq.exists():
        return arq.read_bytes() or None
    try:
        r = requests.get(url, headers=UA, timeout=15)
        ok = r.status_code == 200 and r.headers.get("content-type", "").startswith("image")
        PASTA.mkdir(parents=True, exist_ok=True)
        arq.write_bytes(r.content if ok else b"")
        return r.content if ok else None
    except Exception:  # noqa: BLE001
        return None


def _tempo(d1: dt.date, d2: dt.date) -> str:
    dias = max(0, (d2 - d1).days)
    a, m = dias // 365, (dias % 365) // 30
    partes = ([f"{a} ano{'s' if a != 1 else ''}"] if a else []) + ([f"{m} {'meses' if m != 1 else 'mês'}"] if m else [])
    return " e ".join(partes) or f"{dias} dias"


REDE_ICONE = [("instagram", "📸 Instagram"), ("facebook", "📘 Facebook"), ("twitter", "🐦 X/Twitter"), ("x.com", "🐦 X/Twitter"),
              ("youtube", "▶️ YouTube"), ("tiktok", "🎵 TikTok"), ("threads", "🧵 Threads"), ("linkedin", "💼 LinkedIn"),
              ("wa.me", "💬 WhatsApp"), ("whatsapp", "💬 WhatsApp"), ("t.me", "✈️ Telegram")]


def _rotulo_rede(u: str) -> str:
    low = u.lower()
    return next((r for k, r in REDE_ICONE if k in low), "🌐 Site")


def _link(u: str) -> str:
    return u if u.startswith("http") else "https://" + u


# ------------------------------------------------------------------------ UI
def ficha(p, con, g: pd.DataFrame, a: pd.DataFrame, BRL, CURTO):
    """p: linha do político (nome, cargo, partido, uf, municipio, politico_id, total, indice)."""
    pid, cargo = p["politico_id"], str(p["cargo"])
    try:
        ids = con.execute("SELECT id_origem FROM ids_externos WHERE politico_id = ?", [pid]).df()["id_origem"].tolist()
    except Exception:  # noqa: BLE001
        ids = []
    ids += [pid]
    info = None
    with st.spinner("Buscando a ficha oficial..."):
        if "Deputado Federal" in cargo:
            cd = next((i[3:] for i in ids if i.startswith("CD-") and i[3:].isdigit()), "")
            info = perfil_camara(cd, str(p["nome"]), str(p["uf"] or ""))
        elif "Senador" in cargo:
            sf = next((i[3:] for i in ids if i.startswith("SF-")), str(p["nome"]))
            info = perfil_senado(sf, str(p["nome"]))
        info = info or perfil_tse(con, pid)
    if not info:
        info = {"nome": p["nome"], "partido": p["partido"], "uf": p["uf"], "redes": [], "outros_mandatos": []}

    hoje = dt.date.today()
    c_foto, c_dados = st.columns([1, 4])
    with c_foto:
        img = _foto_ok(info.get("foto"))
        if img:
            st.image(img, width=150)
        else:
            st.markdown("<div style='font-size:90px;text-align:center'>👤</div>", unsafe_allow_html=True)
    with c_dados:
        st.markdown(f"### {info.get('nome') or p['nome']}")
        linhas = []
        if info.get("nome_civil") and _n(info["nome_civil"]) != _n(info.get("nome")):
            linhas.append(f"**Nome civil:** {info['nome_civil']}")
        mun = str(p.get("municipio") or "")
        if info.get("local"):
            rep = info["local"]
        elif re.search("prefeit|vereador", cargo, re.I) and len(mun) > 2:
            rep = f"{mun.title()} / {p['uf']}"
        else:
            rep = f"Estado de {info.get('uf') or p['uf']}"
        linhas.append(f"**Cargo:** {cargo} · **Partido:** {info.get('partido') or p['partido'] or '—'} · **Representa:** {rep}")
        if info.get("numero"):
            linhas.append(f"**Número na urna:** {info['numero']}")
        if info.get("nascimento"):
            idade = hoje.year - info["nascimento"].year - ((hoje.month, hoje.day) < (info["nascimento"].month, info["nascimento"].day))
            linhas.append(f"**Nascimento:** {info['nascimento']:%d/%m/%Y} ({idade} anos)" +
                          (f" · {info['naturalidade']}" if info.get("naturalidade") else ""))
        extras = [x for x in [info.get("escolaridade"), info.get("ocupacao")] if x]
        if extras:
            linhas.append("**Escolaridade / ocupação:** " + " · ".join(str(x).title() for x in extras))
        if info.get("situacao") or info.get("condicao"):
            linhas.append("**Situação:** " + " · ".join(str(x) for x in [info.get("situacao"), info.get("condicao")] if x))
        st.markdown("  \n".join(linhas))
        st.caption(f"Fonte da ficha: {info.get('fonte', 'dados do radar')}")

    # ---- mandato
    ini, fim = info.get("mandato_ini"), info.get("mandato_fim")
    if ini and fim:
        total_d = max(1, (fim - ini).days)
        feito = min(max(0, (hoje - ini).days), total_d)
        st.markdown(f"#### 🗓️ Mandato: {ini:%d/%m/%Y} a {fim:%d/%m/%Y}")
        st.progress(feito / total_d, text=(f"Cumpriu {_tempo(ini, min(hoje, fim))} ({feito / total_d * 100:.0f}%)"
                                            + (f" · faltam {_tempo(hoje, fim)}" if hoje < fim else " · mandato encerrado")))
        gm = g[(pd.to_datetime(g["data"]) >= pd.Timestamp(ini)) & (pd.to_datetime(g["data"]) <= pd.Timestamp(min(hoje, fim)))]
        m1, m2, m3 = st.columns(3)
        # a média usa só os meses que o radar cobre (a cota é coletada a partir de 2023, por padrão)
        if len(gm):
            d0 = max(pd.Timestamp(ini), pd.to_datetime(gm["data"]).min().replace(day=1))
            d1 = pd.Timestamp(min(hoje, fim))
            meses = max(1, (d1.year - d0.year) * 12 + d1.month - d0.month + 1)
        else:
            d0, meses = pd.Timestamp(ini), 1
        m1.metric(f"Gasto no mandato (desde {d0:%m/%Y})", CURTO(gm["valor"].sum()),
                  help="Soma de todas as notas do radar dentro do mandato, sem o filtro de período da barra lateral.")
        m2.metric("Média por mês", CURTO(gm["valor"].sum() / meses), help=f"Total ÷ {meses} meses com dados no radar.")
        m3.metric("Mandatos nesta função", info.get("n_mandatos") or "—",
                  help="Deputado: legislaturas na Câmara · Senador: mandatos no Senado · Prefeito/vereador: eleições vencidas registradas no TSE.")
        if len(gm) and d0 > pd.Timestamp(ini) + pd.Timedelta(days=60):
            st.caption(f"O radar tem os gastos deste político a partir de {d0:%m/%Y}; o que foi gasto antes disso no mandato não está nesta soma.")
        if gm.empty and len(g):
            st.caption("Os gastos que o radar tem desta pessoa são da campanha (antes do mandato). Para ver os gastos do mandato "
                       "(diárias, verba de gabinete), exporte as planilhas do portal da Câmara/Prefeitura para dados\\importar.")
    # ---- salário: SEPARADO dos gastos
    from radar.textos import SUBSIDIO_DESDE, SUBSIDIO_FEDERAL
    st.markdown("#### 💼 Salário (não entra nos gastos)")
    if re.search("deputado federal|senador", cargo, re.I):
        s1, s2 = st.columns(2)
        s1.metric("Salário bruto mensal (subsídio)", BRL(SUBSIDIO_FEDERAL),
                  help=f"Valor desde {SUBSIDIO_DESDE} (Decreto Legislativo 172/2022), igual para deputados federais e senadores. "
                       "Há também 13º salário. Antes de 2025 o valor era menor.")
        s2.metric("Por ano (13 salários)", CURTO(SUBSIDIO_FEDERAL * 13))
        st.caption("Além do salário, o gabinete recebe verba para pagar assessores, e há auxílio-moradia ou apartamento funcional. "
                   "Nada disso está somado nos gastos do radar, que mostram só a cota parlamentar (reembolso de despesas).")
    elif re.search("prefeit|vereador", cargo, re.I):
        mun = str(p.get("municipio") or "").title()
        st.caption(f"O salário de {cargo.lower()} é fixado por lei municipal e não existe em base nacional aberta. "
                   f"Consulte a folha de pagamento no portal da transparência de {mun or 'seu município'}. "
                   "Os valores de gastos do radar para esta pessoa são de campanha (TSE) e, se importados, diárias e pagamentos do portal.")
        if mun:
            st.link_button("🔎 Ver salário no portal da transparência",
                           f"https://www.google.com/search?q={up.quote(f'portal da transparência {mun} folha de pagamento {cargo}')}")
    else:
        st.caption("Salário não disponível nas bases usadas pelo radar.")

    if info.get("outros_mandatos"):
        with st.expander("Histórico de mandatos e candidaturas"):
            st.markdown("\n".join(f"- {x}" for x in info["outros_mandatos"]))

    # ---- contatos e redes
    st.markdown("#### 📣 Onde cobrar")
    cols = st.columns(3)
    cols[0].markdown("**E-mail:** " + (f"[{info['email']}](mailto:{info['email']})" if info.get("email") else "—") +
                     "  \n**Telefone:** " + (info.get("telefone") or "—") +
                     ("  \n**Gabinete:** " + info["gabinete"] if info.get("gabinete") else ""))
    redes = list(dict.fromkeys(info.get("redes") or []))
    with cols[1]:
        if redes:
            for u in redes[:8]:
                st.link_button(_rotulo_rede(u), _link(u), width="stretch")
        else:
            st.caption("Nenhuma rede social declarada ao TSE / Casa legislativa.")
    with cols[2]:
        if info.get("pagina"):
            st.link_button("🏛️ Página oficial", info["pagina"], width="stretch")
        if info.get("fala"):
            st.link_button("✉️ Fale com / ouvidoria", info["fala"], width="stretch")
        if info.get("lai"):
            st.link_button("📄 Pedido de informação (LAI)", info["lai"], width="stretch")

    # ---- mensagem pronta
    with st.expander("✍️ Mensagem pronta para cobrar", expanded=False):
        pontos = []
        for r in a.head(6).itertuples():
            pontos.append(f"- {r.titulo}: {r.detalhe} ({BRL(r.valor)})")
        texto = (f"Prezado(a) {info.get('nome') or p['nome']},\n\n"
                 f"Sou cidadão e contribuinte. Acompanhando os dados públicos dos seus gastos "
                 f"({CURTO(g['valor'].sum())} em {len(g)} lançamentos registrados nas fontes oficiais), identifiquei pontos que "
                 f"gostaria que fossem esclarecidos:\n\n" + ("\n".join(pontos) if pontos else "- (sem alertas no período; peço a prestação de contas detalhada)")
                 + "\n\nSolicito, com base na Lei de Acesso à Informação (Lei 12.527/2011), as notas fiscais, contratos e a "
                   "justificativa de cada despesa acima, e a indicação do resultado obtido para a população.\n\n"
                   "Aguardo retorno.\nAtenciosamente,\n")
        st.code(texto, language=None, wrap_lines=True)
        b1, b2 = st.columns(2)
        if info.get("email"):
            b1.link_button("📧 Abrir no e-mail", f"mailto:{info['email']}?subject={up.quote('Pedido de esclarecimento sobre gastos')}&body={up.quote(texto)}", width="stretch")
        b2.link_button("💬 Compartilhar no WhatsApp", f"https://wa.me/?text={up.quote(texto)}", width="stretch")
        st.caption("Alertas são indícios, não prova. Peça explicação antes de acusar publicamente.")
