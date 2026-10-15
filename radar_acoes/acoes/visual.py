"""Identidade visual do painel: interface de HUD no estilo J.A.R.V.I.S. (escura, ciano, brilho suave)."""
from __future__ import annotations

import html

import streamlit as st

CIANO, AMBAR, VERMELHO, VERDE, CINZA = "#00E5FF", "#FFB547", "#FF4D6D", "#39FF88", "#7C8BA1"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@500;700;900&family=Rajdhani:wght@500;600;700&display=swap');
:root { --ciano:#00E5FF; --ciano2:#0AA3C2; --fundo:#030B16; --painel:rgba(8,26,44,.72); --borda:rgba(0,229,255,.28);
        --texto:#D9F7FF; --apagado:#7FA9BC; --ambar:#FFB547; --vermelho:#FF4D6D; --verde:#39FF88; }
.stApp {
  background:
    radial-gradient(1200px 600px at 15% -10%, rgba(0,229,255,.10), transparent 60%),
    radial-gradient(900px 500px at 110% 10%, rgba(0,120,255,.10), transparent 60%),
    linear-gradient(rgba(0,229,255,.035) 1px, transparent 1px) 0 0/ 42px 42px,
    linear-gradient(90deg, rgba(0,229,255,.035) 1px, transparent 1px) 0 0/ 42px 42px,
    var(--fundo) !important;
}
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: linear-gradient(180deg, #06182A, #030B16); border-right: 1px solid var(--borda); }
h1, h2, h3, h4 { font-family: 'Orbitron', sans-serif !important; letter-spacing: .04em; color: var(--texto); }
h2, h3 { font-size: 1.15rem !important; text-transform: uppercase; color: var(--ciano) !important;
         text-shadow: 0 0 12px rgba(0,229,255,.35); }
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--borda); flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] { font-family: 'Rajdhani', sans-serif; font-weight: 700; font-size: 1rem; letter-spacing: .04em;
  background: rgba(0,229,255,.04); border: 1px solid rgba(0,229,255,.15); border-bottom: none; border-radius: 10px 10px 0 0; padding: 6px 14px; }
.stTabs [aria-selected="true"] { background: rgba(0,229,255,.14) !important; box-shadow: 0 0 18px rgba(0,229,255,.25) inset; }
[data-testid="stMetric"], [data-testid="stExpander"], [data-testid="stDataFrame"], [data-testid="stChatMessage"] {
  background: var(--painel); border: 1px solid var(--borda); border-radius: 14px; }
[data-testid="stMetric"] { padding: 12px 16px; box-shadow: 0 0 22px rgba(0,229,255,.06); }
[data-testid="stMetricValue"] { font-family: 'Orbitron', sans-serif; color: var(--ciano); text-shadow: 0 0 14px rgba(0,229,255,.35); }
.stButton > button { font-family: 'Rajdhani', sans-serif; font-weight: 700; letter-spacing: .05em; border: 1px solid var(--borda);
  background: rgba(0,229,255,.06); transition: all .2s; }
.stButton > button:hover { box-shadow: 0 0 16px rgba(0,229,255,.45); border-color: var(--ciano); color: var(--ciano); }

/* ---------- cabeçalho ---------- */
.jv-topo { display:flex; align-items:center; gap:22px; padding:18px 22px; margin:-10px 0 14px; border:1px solid var(--borda);
  border-radius:18px; background: linear-gradient(120deg, rgba(0,229,255,.10), rgba(3,11,22,.6) 45%, rgba(0,120,255,.08));
  box-shadow: 0 0 40px rgba(0,229,255,.10), inset 0 0 30px rgba(0,229,255,.05); position:relative; overflow:hidden; }
.jv-topo::after { content:""; position:absolute; inset:0; background: linear-gradient(90deg, transparent, rgba(0,229,255,.10), transparent);
  transform: translateX(-100%); animation: varre 6s linear infinite; pointer-events:none; }
@keyframes varre { to { transform: translateX(100%); } }
.jv-reator { flex: 0 0 86px; height:86px; }
.jv-reator .anel1 { transform-origin: 50px 50px; animation: gira 14s linear infinite; }
.jv-reator .anel2 { transform-origin: 50px 50px; animation: gira 9s linear infinite reverse; }
.jv-reator .nucleo { animation: pulsa 2.6s ease-in-out infinite; transform-origin: 50px 50px; }
@keyframes gira { to { transform: rotate(360deg); } }
@keyframes pulsa { 0%,100% { opacity:.75; transform: scale(.96); } 50% { opacity:1; transform: scale(1.04); } }
.jv-titulo { font-family:'Orbitron',sans-serif; font-weight:900; font-size:2.1rem; letter-spacing:.32em; color:#E8FCFF;
  text-shadow: 0 0 18px rgba(0,229,255,.75), 0 0 2px #fff; line-height:1.1; }
.jv-sub { font-family:'Rajdhani',sans-serif; font-size:1.05rem; color:var(--apagado); letter-spacing:.08em; margin-top:2px; }
.jv-chips { display:flex; flex-wrap:wrap; gap:8px; margin-top:10px; }
.jv-chip { font-family:'Rajdhani',sans-serif; font-weight:700; font-size:.85rem; letter-spacing:.06em; padding:3px 10px;
  border-radius:999px; border:1px solid var(--borda); color:var(--texto); background:rgba(0,229,255,.06); }
.jv-chip.on { color:var(--verde); border-color:rgba(57,255,136,.5); }
.jv-chip.on::before { content:"●"; margin-right:6px; animation: pulsa 1.6s infinite; display:inline-block; }
.jv-chip.alerta { color:var(--ambar); border-color:rgba(255,181,71,.5); }
.jv-chip.perigo { color:var(--vermelho); border-color:rgba(255,77,109,.6); }

/* ---------- cartões HUD ---------- */
.jv-grade { display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin: 6px 0 14px; }
.jv-cartao { position:relative; padding:14px 16px 12px; border-radius:14px; border:1px solid var(--borda);
  background: linear-gradient(160deg, rgba(0,229,255,.08), rgba(8,26,44,.75)); box-shadow: 0 0 24px rgba(0,229,255,.07); }
.jv-cartao::before, .jv-cartao::after { content:""; position:absolute; width:14px; height:14px; border-color:var(--ciano); border-style:solid; opacity:.8; }
.jv-cartao::before { top:-1px; left:-1px; border-width:2px 0 0 2px; border-radius:14px 0 0 0; }
.jv-cartao::after { bottom:-1px; right:-1px; border-width:0 2px 2px 0; border-radius:0 0 14px 0; }
.jv-rotulo { font-family:'Rajdhani',sans-serif; font-weight:700; font-size:.82rem; letter-spacing:.12em; text-transform:uppercase; color:var(--apagado); }
.jv-valor { font-family:'Orbitron',sans-serif; font-weight:700; font-size:1.45rem; color:#E8FCFF; margin-top:4px;
  text-shadow: 0 0 14px rgba(0,229,255,.45); line-height:1.25; word-break: break-word; }
.jv-nota { font-family:'Rajdhani',sans-serif; font-size:.95rem; margin-top:4px; color:var(--apagado); }
.jv-nota.ok { color:var(--verde); } .jv-nota.alerta { color:var(--ambar); } .jv-nota.perigo { color:var(--vermelho); }

/* ---------- caixa de fala do JARVIS ---------- */
.jv-fala { border:1px solid var(--borda); border-left:3px solid var(--ciano); border-radius:14px; padding:16px 20px;
  background: linear-gradient(135deg, rgba(0,229,255,.09), rgba(8,26,44,.85)); box-shadow: 0 0 30px rgba(0,229,255,.08);
  font-size:1.03rem; line-height:1.6; }
.jv-fala .jv-cab { font-family:'Orbitron',sans-serif; font-size:.8rem; letter-spacing:.2em; color:var(--ciano); margin-bottom:8px; }
@media (prefers-reduced-motion: reduce) { .jv-topo::after, .jv-reator *, .jv-chip.on::before { animation: none !important; } }
@media (max-width: 640px) { .jv-titulo { font-size:1.4rem; letter-spacing:.18em; } .jv-reator { flex-basis:60px; height:60px; } }
</style>
"""

REATOR = """
<svg class="jv-reator" viewBox="0 0 100 100" aria-hidden="true">
  <defs><radialGradient id="g" cx="50%" cy="50%" r="50%">
    <stop offset="0%" stop-color="#E8FCFF"/><stop offset="35%" stop-color="#00E5FF"/><stop offset="100%" stop-color="#00E5FF" stop-opacity="0"/>
  </radialGradient></defs>
  <circle cx="50" cy="50" r="46" fill="none" stroke="#00E5FF" stroke-opacity=".25" stroke-width="1"/>
  <g class="anel1"><circle cx="50" cy="50" r="40" fill="none" stroke="#00E5FF" stroke-width="2.5" stroke-dasharray="18 8" stroke-opacity=".9"/></g>
  <g class="anel2"><circle cx="50" cy="50" r="31" fill="none" stroke="#7FF3FF" stroke-width="1.5" stroke-dasharray="4 6"/></g>
  <circle class="nucleo" cx="50" cy="50" r="20" fill="url(#g)"/>
  <circle cx="50" cy="50" r="9" fill="#E8FCFF" opacity=".9"/>
</svg>
"""


def aplicar() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def topo(subtitulo: str, chips: list[tuple[str, str]]) -> None:
    """chips: [(texto, classe)] com classe em '', 'on', 'alerta', 'perigo'."""
    c = "".join(f'<span class="jv-chip {cls}">{html.escape(t)}</span>' for t, cls in chips)
    st.markdown(f'<div class="jv-topo">{REATOR}<div><div class="jv-titulo">J.A.R.V.I.S.</div>'
                f'<div class="jv-sub">{html.escape(subtitulo)}</div><div class="jv-chips">{c}</div></div></div>',
                unsafe_allow_html=True)


def cartoes(itens: list[tuple]) -> None:
    """itens: [(rótulo, valor, nota, classe_da_nota)] — nota e classe opcionais."""
    blocos = []
    for it in itens:
        rot, val = it[0], it[1]
        nota = it[2] if len(it) > 2 else ""
        cls = it[3] if len(it) > 3 else ""
        blocos.append(f'<div class="jv-cartao"><div class="jv-rotulo">{html.escape(str(rot))}</div>'
                      f'<div class="jv-valor">{html.escape(str(val))}</div>'
                      + (f'<div class="jv-nota {cls}">{html.escape(str(nota))}</div>' if nota else "") + "</div>")
    st.markdown(f'<div class="jv-grade">{"".join(blocos)}</div>', unsafe_allow_html=True)


def _md_simples(texto: str) -> str:
    """Markdown simples (negrito, itálico, links, listas, parágrafos) → HTML, escapando todo o resto."""
    import re
    blocos = []
    for par in re.split(r"\n\s*\n", texto.strip()):
        linhas = []
        for ln in par.splitlines():
            e = html.escape(ln.strip())
            e = re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', e)
            e = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", e)
            e = re.sub(r"(?<!\*)\*(?!\s)(.+?)(?<!\s)\*(?!\*)", r"<i>\1</i>", e)
            e = re.sub(r"^#{1,6}\s*(.+)$", r"<b>\1</b>", e)
            e = re.sub(r"^[-•]\s+", "• ", e)
            linhas.append(e)
        blocos.append("<p style='margin:0 0 .7em'>" + "<br>".join(linhas) + "</p>")
    return "".join(blocos)


def fala(texto_md: str, cabecalho: str) -> None:
    """Caixa de fala do JARVIS."""
    st.markdown(f'<div class="jv-fala"><div class="jv-cab">{html.escape(cabecalho)}</div>{_md_simples(texto_md)}</div>',
                unsafe_allow_html=True)
