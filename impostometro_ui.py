"""Aba 🧾 Impostômetro do app (federal + estadual + municipal + FGTS)."""
from __future__ import annotations

import datetime as _dt
import json

import altair as alt
import pandas as pd
import streamlit as st

from radar.fontes import estados, impostos

MES_NOME = ["jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez"]
CORES = {"Federal": "#3987e5", "Estadual": "#e8a33d", "Municipal": "#3fae7a", "FGTS": "#9b72d0"}
# se o SICONFI estiver fora do ar: base anual oficial (Carga Tributária 2024, Tesouro Nacional)
ESTADUAIS_RESERVA = {"ICMS": (2024, 805_172e6), "IPVA": (2024, 84_321e6), "ITCD (herança e doação)": (2024, 17_524e6)}

HTML = """
<div style="font-family:system-ui,Segoe UI,sans-serif;background:#12141a;border-radius:14px;padding:16px 20px;color:#f2f2ee">
  <div style="font-size:13px;color:#9aa0a6;letter-spacing:.04em">__TITULO__</div>
  <div id="od" style="display:flex;flex-wrap:wrap;gap:4px;align-items:flex-end;margin:10px 0 12px"></div>
  <div style="display:flex;flex-wrap:wrap;gap:20px;font-size:13px;color:#c9ccd1;margin-bottom:12px">
    <div>Por segundo<br><b id="ps" style="font-size:17px;color:#fff"></b></div>
    <div>Por minuto<br><b id="pm" style="font-size:17px;color:#fff"></b></div>
    <div>Por dia<br><b id="pd" style="font-size:17px;color:#fff"></b></div>
    <div>Desde que você abriu esta tela<br><b id="ab" style="font-size:17px;color:#4fd18b"></b></div>
  </div>
  <div id="comp" style="display:flex;flex-wrap:wrap;gap:8px"></div>
</div>
<script>
const C=__COMP__, T0=Date.now()/1000;
const fmt=(v,d=0)=>v.toLocaleString('pt-BR',{minimumFractionDigits:d,maximumFractionDigits:d});
const val=(c,t)=>c.o+Math.max(0,t-c.b)*c.p;
const PS=C.reduce((a,c)=>a+c.p,0);
const od=document.getElementById('od'), cp=document.getElementById('comp');
const F='font:700 clamp(20px,4vw,44px) ui-monospace,Consolas,monospace;';
function tile(ch){const e=document.createElement('span');
  e.style.cssText=/[0-9]/.test(ch)?F+'display:inline-block;min-width:.62em;text-align:center;background:#1f232c;border:1px solid #2c313c;border-radius:6px;padding:2px 3px;color:#ffd24a':F+'color:#9aa0a6;padding:0 1px';
  e.textContent=ch;return e}
C.forEach((c,i)=>{const d=document.createElement('div');
  d.style.cssText='background:#1b1e26;border-radius:8px;padding:6px 10px;border-left:4px solid '+c.c;
  d.innerHTML='<div style="font-size:12px;color:#c9ccd1">'+c.n+'</div><b id="c'+i+'" style="font-size:15px;color:#fff;font-variant-numeric:tabular-nums"></b><div style="font-size:11px;color:#8a8f98">'+c.s+'</div>';
  cp.appendChild(d)});
let ultimo='';
function tick(){const t=Date.now()/1000;let v=0;
  C.forEach((c,i)=>{const x=val(c,t);v+=x;document.getElementById('c'+i).textContent='R$ '+fmt(x,0)});
  const s='R$ '+fmt(v,2);
  if(s.length!==ultimo.length){od.innerHTML='';for(const ch of s)od.appendChild(tile(ch))}
  else{[...s].forEach((ch,i)=>{if(ch!==ultimo[i])od.children[i].textContent=ch})}
  ultimo=s;document.getElementById('ab').textContent='R$ '+fmt((t-T0)*PS,2)}
document.getElementById('ps').textContent='R$ '+fmt(PS,2);
document.getElementById('pm').textContent='R$ '+fmt(PS*60,0);
document.getElementById('pd').textContent='R$ '+fmt(PS*86400,0);
tick();setInterval(tick,70);
</script>
"""


def _epoch(ts) -> float:
    return pd.Timestamp(ts).tz_localize("-03:00").timestamp()


def _seg_ano(ano: int) -> float:
    return (pd.Timestamp(ano + 1, 1, 1) - pd.Timestamp(ano, 1, 1)).total_seconds()


@st.cache_data(ttl=6 * 3600, show_spinner="Baixando arrecadação federal (Receita)...")
def dados_receita():
    if not impostos.baixar():
        return None
    return impostos.carregar()


@st.cache_data(ttl=1800, show_spinner="Buscando os recolhimentos federais mais recentes (Tesouro)...")
def dados_diarios(_marca: str):
    ano = _dt.date.today().year
    for a in (ano, ano - 1):
        impostos.baixar_diario(a, max_horas=2)
    return impostos.ritmo_diario(impostos.carregar_diario([ano - 1, ano]))


@st.cache_data(ttl=6 * 3600, show_spinner="Buscando ICMS, IPVA e ITCD dos 27 estados (Tesouro/SICONFI)... na 1ª vez leva ~1 min")
def dados_estados(anos: tuple[int, ...]):
    return estados.coletar(list(anos))


def _crescimento(arr) -> float:
    try:
        return impostos.ritmo(arr)["crescimento"]
    except Exception:  # noqa: BLE001
        return 1.07


def _componentes(onde: str, arr: pd.DataFrame, est: pd.DataFrame | None, CURTO) -> tuple[list, list]:
    """Monta as parcelas do contador. Retorna (componentes p/ o JS, linhas de explicação)."""
    agora = pd.Timestamp.now()
    ano = agora.year
    ini = _epoch(pd.Timestamp(ano, 1, 1))
    g = _crescimento(arr)
    comp, notas = [], []

    # Federal
    rd = None
    if onde == "Brasil":
        try:
            rd = dados_diarios(agora.strftime("%Y-%m-%d %H:") + str(agora.minute // 30))
        except Exception as e:  # noqa: BLE001
            notas.append(f"Recolhimento diário federal indisponível agora ({e}).")
    d_fed = arr if onde == "Brasil" else arr[arr["uf"] == onde]
    # CONFERÊNCIA AUTOMÁTICA: o total diário do Tesouro no último ano fechado tem que bater
    # (±30%) com o total oficial da Receita no mesmo ano; se não bater, usa só a Receita.
    if rd:
        y = ano - 1
        pdia = rd["por_dia"]
        pdia_y = pdia[pdia.index.year == y]
        rec_y = arr[arr["data"].dt.year == y]
        if pdia_y.index.nunique() >= 200 and rec_y["data"].dt.month.nunique() == 12:
            razao = pdia_y.sum() / max(rec_y["valor"].sum(), 1)
            if not 0.7 <= razao <= 1.35:
                notas.append(f"⚠️ Conferência: o recolhimento diário de {y} ({CURTO(pdia_y.sum())}) não bateu com o total "
                             f"oficial da Receita ({CURTO(rec_y['valor'].sum())}); usando só o dado da Receita.")
                rd = None
            else:
                notas.append(f"✔️ Conferido: diário do Tesouro em {y} = {razao*100:.0f}% do total oficial da Receita.")
    if rd:
        comp.append({"n": "Federal (União, com INSS)", "o": rd["oficial_ano"], "b": _epoch(rd["base_ts"]),
                     "p": rd["por_segundo"], "c": CORES["Federal"], "s": f"real até {rd['ultimo_dia']:%d/%m} (diário)"})
        notas.append(f"🟢 **Federal:** recolhimento real do Tesouro até {rd['ultimo_dia']:%d/%m/%Y}, publicado todo dia (2 a 4 dias de atraso).")
    else:
        rt = impostos.ritmo(d_fed)
        um = rt["ultimo_mes"]
        comp.append({"n": "Federal (União, com INSS)", "o": rt["oficial_ano"], "b": _epoch(rt["base_ts"]),
                     "p": rt["por_segundo"], "c": CORES["Federal"], "s": f"real até {MES_NOME[um.month-1]}/{um.year}"})
        notas.append(f"🟡 **Federal:** dado mensal da Receita até {MES_NOME[um.month-1]}/{um.year}.")

    # Estadual
    e_uf = est if (est is not None and onde == "Brasil") else (est[est["uf"] == onde] if est is not None else None)
    re_ = estados.ritmo(e_uf) if e_uf is not None and len(e_uf) else None
    if re_ and onde == "Brasil":
        # CONFERÊNCIA: ICMS+IPVA+ITCD dos estados (12 meses) vs base oficial da Carga Tributária
        esperado = sum(v * g ** (ano - a) for a, v in ESTADUAIS_RESERVA.values())
        razao = re_["ult12"] / esperado
        if not 0.6 <= razao <= 1.6:
            notas.append(f"⚠️ Conferência: estados somaram {CURTO(re_['ult12'])} em 12 meses, fora do esperado "
                         f"(~{CURTO(esperado)}); usando a base oficial.")
            re_ = None
        else:
            notas.append(f"✔️ Conferido: estados em 12 meses = {razao*100:.0f}% do esperado pela Carga Tributária oficial.")
    if re_:
        um = re_["ultimo_mes"]
        comp.append({"n": "Estadual (ICMS, IPVA, ITCD)", "o": re_["oficial_ano"], "b": _epoch(re_["base_ts"]),
                     "p": re_["por_segundo"], "c": CORES["Estadual"], "s": f"real até {MES_NOME[um.month-1]}/{um.year}"})
        notas.append(f"🟢 **Estadual:** ICMS, IPVA e ITCD {'dos 27 estados' if onde == 'Brasil' else 'de ' + onde} "
                     f"real até {MES_NOME[um.month-1]}/{um.year} (relatórios bimestrais dos estados ao Tesouro).")
    elif onde == "Brasil":
        ps = sum(v * g ** (ano - a) for a, v in ESTADUAIS_RESERVA.values()) / _seg_ano(ano)
        comp.append({"n": "Estadual (ICMS, IPVA, ITCD)", "o": 0.0, "b": ini, "p": ps, "c": CORES["Estadual"], "s": "estimativa"})
        notas.append("🟠 **Estadual:** SICONFI fora do ar agora; usando estimativa pela base oficial de 2024.")

    # Municipal e FGTS (só no Brasil: não há série aberta por estado)
    if onde == "Brasil":
        for esfera, rot in (("Municipal", "Municipal (ISS, IPTU, ITBI, taxas)"), ("FGTS", "FGTS")):
            anual = sum(impostos.estimado_anual(n, ano, g) for n, (_, _, e) in impostos.ESTIMADOS.items() if e == esfera)
            comp.append({"n": rot, "o": 0.0, "b": ini, "p": anual / _seg_ano(ano), "c": CORES[esfera],
                         "s": f"estimativa ({CURTO(anual)}/ano)"})
        notas.append(f"🟠 **Municipal e FGTS:** não existe dado aberto mensal nacional; estimativa pela base anual oficial "
                     f"corrigida pelo crescimento da arrecadação federal ({(g-1)*100:+.1f}% a.a.). {impostos.FONTE_ESTIMADOS}")
    else:
        notas.append("Por estado não há dado aberto de ISS/IPTU e FGTS; o contador soma federal pago no estado + tributos estaduais.")
    return comp, notas


@st.fragment(run_every="10m")
def contador(onde: str, arr: pd.DataFrame, est: pd.DataFrame | None, CURTO):
    """Reexecuta sozinho a cada 10 min e se corrige quando sai dado novo."""
    comp, notas = _componentes(onde, arr, est, CURTO)
    ano = pd.Timestamp.now().year
    titulo = f"TRIBUTOS PAGOS NO BRASIL EM {ano} · AO VIVO" if onde == "Brasil" else f"TRIBUTOS PAGOS EM {onde} EM {ano} · AO VIVO"
    html = HTML.replace("__TITULO__", titulo).replace("__COMP__", json.dumps(comp))
    altura = 300 if len(comp) > 2 else 280
    if hasattr(st, "iframe"):
        st.iframe(html, height=altura)
    else:
        import streamlit.components.v1 as components
        components.html(html, height=altura)
    st.caption(("  \n".join(notas) + f"  \nÚltima checagem: {pd.Timestamp.now():%H:%M} (o app confere sozinho a cada 10 min).").replace("$", "\\$"))


def _barras(df: pd.DataFrame, CURTO, altura_linha=28):
    df = df.sort_values("valor", ascending=False).copy()
    df["_txt"] = df["valor"].map(CURTO)
    ordem = df["nome"].tolist()
    base = alt.Chart(df).encode(
        y=alt.Y("nome:N", sort=ordem, title=None, axis=alt.Axis(labelLimit=320, labelFontSize=12)),
        x=alt.X("valor:Q", title=None, axis=alt.Axis(labels=False, ticks=False, grid=False, domain=False)),
        tooltip=[alt.Tooltip("nome:N", title="Tributo"), alt.Tooltip("esfera:N", title="Esfera"),
                 alt.Tooltip("_txt:N", title="Valor"), alt.Tooltip("origem:N", title="Dado")])
    cor = alt.Color("esfera:N", title=None, legend=alt.Legend(orient="top"),
                    scale=alt.Scale(domain=list(CORES), range=list(CORES.values())))
    barras = base.mark_bar(cornerRadiusEnd=4, height=altura_linha * 0.62).encode(
        color=cor, opacity=alt.condition("datum.origem == 'Estimativa'", alt.value(0.55), alt.value(1)))
    txt = base.mark_text(align="left", dx=6, fontSize=12, fontWeight="bold", color="#8a8a86").encode(text="_txt:N")
    st.altair_chart((barras + txt).properties(height=max(160, altura_linha * len(df)))
                    .configure_view(strokeWidth=0).configure_axis(labelColor="#8a8a86"), width="stretch")


def render(CURTO):
    try:
        arr = dados_receita()
    except Exception as e:  # noqa: BLE001
        arr = None
        st.error(f"Não consegui ler o arquivo da Receita: {e}")
    if arr is None or arr.empty:
        st.warning("Sem dados de arrecadação. Conecte à internet e clique em baixar.")
        if st.button("🔄 Baixar dados", key="imp_baixar"):
            dados_receita.clear(); st.rerun()
        return
    hoje = pd.Timestamp.now()
    try:
        est = dados_estados((hoje.year - 1, hoje.year))
    except Exception as e:  # noqa: BLE001
        est = None
        st.caption(f"Estados indisponíveis agora ({e}).")

    c1, _ = st.columns([1, 2])
    onde = c1.selectbox("Onde", ["Brasil"] + sorted(arr["uf"].dropna().unique()), key="imp_uf")
    contador(onde, arr, est, CURTO)

    # ------------------------------------------------------------------ ranking
    st.subheader("Ranking dos tributos")
    d = arr if onde == "Brasil" else arr[arr["uf"] == onde]
    anos_arr = sorted(d["data"].dt.year.unique(), reverse=True)
    per = st.radio("Período", ["Últimos 12 meses"] + [str(a) for a in anos_arr[:8]], horizontal=True, key="imp_per")
    g = _crescimento(arr)
    if per == "Últimos 12 meses":
        fed = d[d["data"] > d["data"].max() - pd.DateOffset(months=12)]
        ano_ref, frac = hoje.year, 1.0
    else:
        ano_ref = int(per)
        fed = d[d["data"].dt.year == ano_ref]
        frac = fed["data"].dt.month.nunique() / 12 if ano_ref == hoje.year else 1.0

    linhas = [(t, "Federal", v, "Real") for t, v in fed.groupby("tributo")["valor"].sum().items()]

    e_per = None
    if est is not None or per != "Últimos 12 meses":
        try:
            e_all = est if (est is not None and (per == "Últimos 12 meses" or ano_ref >= hoje.year - 1)) \
                else dados_estados((ano_ref,))
            e_all = e_all if onde == "Brasil" else e_all[e_all["uf"] == onde]
            if len(e_all):
                if per == "Últimos 12 meses":
                    e_per = e_all[e_all["data"] > e_all["data"].max() - pd.DateOffset(months=12)]
                else:
                    e_per = e_all[e_all["data"].dt.year == ano_ref]
        except Exception:  # noqa: BLE001
            e_per = None
    if e_per is not None and len(e_per):
        linhas += [(t, "Estadual", v, "Real") for t, v in e_per.groupby("tributo")["valor"].sum().items()]
    elif onde == "Brasil":
        linhas += [(t, "Estadual", v * g ** (ano_ref - a) * frac, "Estimativa") for t, (a, v) in ESTADUAIS_RESERVA.items()]
    if onde == "Brasil":
        for n, (a, v, esf) in impostos.ESTIMADOS.items():
            real_anual = ano_ref == a and frac == 1.0
            linhas.append((n, esf, impostos.estimado_anual(n, ano_ref, g) * frac, "Real (anual)" if real_anual else "Estimativa"))

    rk = pd.DataFrame(linhas, columns=["nome", "esfera", "valor", "origem"])
    rk = rk[rk["valor"] > 0]
    tot = rk["valor"].sum()
    rk["nome"] = rk.apply(lambda r: f"{r.nome}{' *' if r.origem == 'Estimativa' else ''}  ({r.valor / tot * 100:.1f}%)", axis=1)

    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Total no período", CURTO(tot))
    por_esf = rk.groupby("esfera")["valor"].sum()
    for k, esf in zip((k2, k3, k4), ("Federal", "Estadual", "Municipal")):
        if esf in por_esf:
            k.metric(esf, CURTO(por_esf[esf]), f"{por_esf[esf] / tot * 100:.0f}% do total", delta_color="off")
    _barras(rk, CURTO)
    st.caption(("Barras claras com * são estimativas (sem dado mensal aberto). "
                + ("Período dos estados: últimos 12 meses publicados. " if per == "Últimos 12 meses" else "")
                + ("No ano corrente, as estimativas são proporcionais aos meses já fechados. " if ano_ref == hoje.year and per != "Últimos 12 meses" else ""))
               .replace("$", "\\$"))

    cA, cB = st.columns(2)
    with cA:
        st.subheader("Arrecadação federal por ano")
        an = d.groupby(d["data"].dt.year.rename("ano"), as_index=False)["valor"].sum()
        an = an[an["ano"] >= an["ano"].max() - 14]
        um = d["data"].max()
        ult_ano = int(an["ano"].max())
        an["rot"] = an["ano"].astype(str)
        an["tipo"] = an["ano"].map(lambda a: f"Parcial (até {MES_NOME[um.month-1]})" if a == ult_ano and um.month < 12 else "Ano fechado")
        an["_txt"] = an["valor"].map(CURTO)
        an["_curto"] = an["valor"].map(lambda v: CURTO(v).replace("R$ ", "").replace(" tri", "").replace(" bi", "b"))
        dom = ["Ano fechado"] + ([an["tipo"].iloc[-1]] if an["tipo"].iloc[-1] != "Ano fechado" else [])
        base = alt.Chart(an).encode(
            x=alt.X("rot:N", sort=an["rot"].tolist(), title=None, axis=alt.Axis(labelAngle=0, labelOverlap=False, labelFontSize=10)),
            y=alt.Y("valor:Q", title=None, axis=alt.Axis(labels=False, ticks=False, grid=False, domain=False)),
            tooltip=[alt.Tooltip("rot:N", title="Ano"), alt.Tooltip("_txt:N", title="Arrecadado")])
        st.altair_chart((base.mark_bar(cornerRadiusEnd=4).encode(color=alt.Color(
            "tipo:N", title=None, legend=alt.Legend(orient="top"),
            scale=alt.Scale(domain=dom, range=[CORES["Federal"], "#9ec5f4"][:len(dom)]))) +
            base.mark_text(dy=-7, fontSize=10, color="#8a8a86").encode(text="_curto:N"))
            .properties(height=320).configure_view(strokeWidth=0), width="stretch")
    with cB:
        if onde == "Brasil":
            st.subheader("Ranking por estado")
            ue = fed.groupby("uf")["valor"].sum().rename("Federal").to_frame()
            if e_per is not None and len(e_per):
                ue = ue.join(e_per.groupby("uf")["valor"].sum().rename("Estadual"), how="outer")
            ue = ue.fillna(0).reset_index().melt("uf", var_name="esfera", value_name="valor")
            tot_uf = ue.groupby("uf")["valor"].sum()
            ordem = tot_uf.sort_values(ascending=False).index.tolist()
            ue["_txt"] = ue["valor"].map(CURTO)
            st.altair_chart(alt.Chart(ue).mark_bar(cornerRadiusEnd=3).encode(
                y=alt.Y("uf:N", sort=ordem, title=None, axis=alt.Axis(labelOverlap=False, labelFontSize=11)),
                x=alt.X("valor:Q", title=None, stack=True, axis=alt.Axis(labels=False, ticks=False, grid=False, domain=False)),
                color=alt.Color("esfera:N", title=None, legend=alt.Legend(orient="top"),
                                scale=alt.Scale(domain=["Federal", "Estadual"], range=[CORES["Federal"], CORES["Estadual"]])),
                tooltip=[alt.Tooltip("uf:N", title="UF"), alt.Tooltip("esfera:N", title="Esfera"), alt.Tooltip("_txt:N", title="Valor")])
                .properties(height=max(200, 22 * len(ordem))).configure_view(strokeWidth=0), width="stretch")
            st.caption("Federal: onde o tributo foi pago (sede da empresa), não onde foi gerado.")
        else:
            st.subheader(f"{onde}: mês a mês (federal)")
            mm = d[d["data"] > d["data"].max() - pd.DateOffset(months=24)].groupby("data", as_index=False)["valor"].sum()
            mm["rot"] = mm["data"].map(lambda x: f"{MES_NOME[x.month-1]}/{str(x.year)[2:]}")
            mm["_txt"] = mm["valor"].map(CURTO)
            st.altair_chart(alt.Chart(mm).mark_bar(cornerRadiusEnd=4, color=CORES["Federal"]).encode(
                x=alt.X("rot:N", sort=mm["rot"].tolist(), title=None), y=alt.Y("valor:Q", title=None, axis=None),
                tooltip=[alt.Tooltip("rot:N", title="Mês"), alt.Tooltip("_txt:N", title="Arrecadado")])
                .properties(height=320).configure_view(strokeWidth=0), width="stretch")

    from radar.publico import PUBLICO
    if not PUBLICO and st.button("🔄 Atualizar todos os dados agora", key="imp_atual"):
        impostos.baixar(forcar=True)
        impostos.baixar_diario(hoje.year, forcar=True)
        for c in (dados_receita, dados_diarios, dados_estados):
            c.clear()
        st.rerun()
    st.caption("Fontes: Receita Federal (arrecadação por estado, mensal) · Tesouro Nacional via Portal da Transparência "
               "(recolhimentos federais, diário) · Tesouro Nacional/SICONFI, RREO dos estados (ICMS, IPVA, ITCD, bimestral) · "
               "Carga Tributária do Governo Geral 2024 (municipais) · Conselho Curador do FGTS.")
