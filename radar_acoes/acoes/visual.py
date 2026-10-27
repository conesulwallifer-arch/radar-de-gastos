"""Identidade visual do AURUM: terminal de mercado financeiro (fundo grafite, dourado, verde/vermelho, números monoespaçados)."""
from __future__ import annotations

import html
import math
import re

import streamlit as st

# Paleta de mesa de operações
OURO, DESTAQUE, AZUL = "#D4AF37", "#F5A623", "#4DA3FF"
VERDE, VERMELHO, CINZA = "#00C176", "#FF4D4F", "#7D8590"

CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800&display=swap');
:root { --fundo:#0A0B0D; --painel:#111317; --painel2:#161920; --borda:#262A33; --texto:#E8E6E1; --apagado:#8B919C;
        --ouro:#D4AF37; --ambar:#F5A623; --verde:#00C176; --vermelho:#FF4D4F; --azul:#4DA3FF;
        --mono:'IBM Plex Mono', ui-monospace, Consolas, monospace; }
.stApp { background: radial-gradient(1100px 500px at 0% -10%, rgba(212,175,55,.07), transparent 60%), var(--fundo) !important;
         font-family: 'Inter', sans-serif; }
[data-testid="stHeader"] { background: transparent; }
[data-testid="stSidebar"] { background: #0D0F12; border-right: 1px solid var(--borda); }
h1, h2, h3, h4 { font-family: 'Inter', sans-serif !important; color: var(--texto); }
h2, h3 { font-size: .95rem !important; font-weight: 800 !important; text-transform: uppercase; letter-spacing: .14em;
         color: var(--ambar) !important; border-left: 3px solid var(--ambar); padding-left: 10px !important; }
.stTabs [data-baseweb="tab-list"] { gap: 0; border-bottom: 1px solid var(--borda); flex-wrap: wrap; }
.stTabs [data-baseweb="tab"] { font-family: var(--mono); font-weight: 600; font-size: .86rem; letter-spacing: .04em; text-transform: uppercase;
  padding: 8px 14px; border-right: 1px solid var(--borda); background: transparent; }
.stTabs [aria-selected="true"] { background: rgba(245,166,35,.10) !important; color: var(--ambar) !important; }
[data-testid="stMetric"], [data-testid="stExpander"], [data-testid="stDataFrame"], [data-testid="stChatMessage"] {
  background: var(--painel); border: 1px solid var(--borda); border-radius: 6px; }
[data-testid="stMetric"] { padding: 10px 14px; }
[data-testid="stMetricValue"] { font-family: var(--mono); color: var(--texto); }
.stButton > button { font-family: var(--mono); font-weight: 600; letter-spacing: .04em; text-transform: uppercase; font-size: .82rem;
  border: 1px solid var(--borda); border-radius: 4px; background: var(--painel2); }
.stButton > button:hover { border-color: var(--ambar); color: var(--ambar); }
.stButton > button[kind="primary"] { background: var(--ambar); color: #111; border-color: var(--ambar); }
.stButton > button[kind="primary"]:hover { background: #FFB84D; color: #111; }

/* ---------- fita de cotações ---------- */
.au-fita { overflow: hidden; white-space: nowrap; border-top: 1px solid var(--borda); border-bottom: 1px solid var(--borda);
  background: #07080A; margin: -6px 0 14px; position: relative; }
.au-fita-trilho { display: inline-block; padding: 7px 0; animation: corre 70s linear infinite; }
.au-fita:hover .au-fita-trilho { animation-play-state: paused; }
@keyframes corre { from { transform: translateX(0); } to { transform: translateX(-50%); } }
.au-cot { font-family: var(--mono); font-size: .86rem; margin-right: 28px; }
.au-cot b { color: var(--texto); margin-right: 6px; }
.au-cot .p { color: var(--apagado); margin-right: 6px; }
.sobe { color: var(--verde); } .cai { color: var(--vermelho); } .neutro { color: var(--apagado); }

/* ---------- cabeçalho ---------- */
.au-topo { display:flex; align-items:center; justify-content:space-between; gap:18px; flex-wrap:wrap; padding:14px 18px; margin:-8px 0 10px;
  border:1px solid var(--borda); border-radius:6px; background: linear-gradient(90deg, #13151A, #0D0F12); }
.au-marca { display:flex; align-items:center; gap:14px; }
.au-logo { width:46px; height:46px; flex:0 0 46px; }
.au-nome { font-family:'Inter',sans-serif; font-weight:800; font-size:1.9rem; letter-spacing:.32em; line-height:1;
  background: linear-gradient(180deg, #F7E7A6 0%, #D4AF37 45%, #9C7A1C 100%); -webkit-background-clip:text; background-clip:text; color:transparent; }
.au-sub { font-family: var(--mono); font-size:.78rem; color: var(--apagado); letter-spacing:.12em; text-transform: uppercase; margin-top:6px; }
.au-chips { display:flex; flex-wrap:wrap; gap:6px; justify-content:flex-end; }
.au-chip { font-family: var(--mono); font-size:.76rem; font-weight:600; letter-spacing:.06em; padding:4px 9px; border-radius:3px;
  border:1px solid var(--borda); color: var(--texto); background: var(--painel2); text-transform: uppercase; }
.au-chip.on { color: var(--verde); border-color: rgba(0,193,118,.45); }
.au-chip.on::before { content:"●"; margin-right:5px; animation: pisca 1.6s infinite; }
.au-chip.alerta { color: var(--ambar); border-color: rgba(245,166,35,.45); }
.au-chip.perigo { color: var(--vermelho); border-color: rgba(255,77,79,.5); }
@keyframes pisca { 50% { opacity: .35; } }

/* ---------- cartões ---------- */
.au-grade { display:grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap:10px; margin: 6px 0 14px; }
.au-cartao { padding:12px 14px; border:1px solid var(--borda); border-top:2px solid var(--ambar); border-radius:4px; background: var(--painel); }
.au-rotulo { font-family: var(--mono); font-size:.72rem; letter-spacing:.12em; text-transform:uppercase; color: var(--apagado); }
.au-valor { font-family: var(--mono); font-weight:600; font-size:1.4rem; color: var(--texto); margin-top:4px; line-height:1.25; word-break: break-word; }
.au-nota { font-family: var(--mono); font-size:.82rem; margin-top:4px; color: var(--apagado); }
.au-nota.ok { color: var(--verde); } .au-nota.alerta { color: var(--ambar); } .au-nota.perigo { color: var(--vermelho); }

/* ---------- boletim do AURUM ---------- */
.au-fala { border:1px solid var(--borda); border-left:3px solid var(--ouro); border-radius:4px; padding:14px 18px;
  background: var(--painel); font-size:1rem; line-height:1.6; }
.au-fala .au-cab { font-family: var(--mono); font-size:.74rem; letter-spacing:.16em; color: var(--ouro); margin-bottom:10px;
  padding-bottom:8px; border-bottom:1px dashed var(--borda); text-transform: uppercase; }
.au-fala a { color: var(--azul); }

/* ---------- sala dos agentes ---------- */
.ag-grade { display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap:10px; margin:6px 0 14px; }
.ag-card { border:1px solid var(--borda); border-radius:4px; padding:14px; background: var(--painel); }
.ag-topo { display:flex; align-items:center; gap:12px; }
.ag-avatar { width:46px; height:46px; border-radius:4px; display:flex; align-items:center; justify-content:center; font-size:1.5rem;
  border:1px solid var(--borda); background: var(--painel2); }
.ag-nome { font-weight:800; font-size:1rem; color: var(--texto); letter-spacing:.02em; }
.ag-cargo { font-size:.86rem; color: var(--apagado); }
.ag-status { font-family: var(--mono); font-size:.72rem; letter-spacing:.08em; color: var(--verde); margin-top:2px; }
.ag-status::before { content:"●"; margin-right:5px; }
.ag-placar { display:flex; flex-wrap:wrap; gap:6px; margin:10px 0 6px; font-family: var(--mono); font-size:.8rem; }
.ag-placar span { padding:2px 7px; border-radius:3px; border:1px solid var(--borda); }
.ag-placar .a { color: var(--verde); } .ag-placar .c { color: var(--vermelho); } .ag-placar .v { color: var(--ambar); }
.ag-linha { font-size:.88rem; line-height:1.45; margin-top:6px; color: var(--texto); }
.ag-linha b { color: var(--ambar); font-family: var(--mono); font-size:.76rem; letter-spacing:.08em; }
.ag-console { font-family: var(--mono); font-size:.82rem; line-height:1.6; color:#C9D1D9; background:#07080A;
  border:1px solid var(--borda); border-radius:4px; padding:10px 12px; max-height:340px; overflow:auto; }
.ag-console .h { color: var(--ambar); margin-right:8px; }
@media (prefers-reduced-motion: reduce) { .au-fita-trilho, .au-chip.on::before { animation: none !important; } }
@media (max-width: 640px) { .au-nome { font-size:1.4rem; letter-spacing:.2em; } .au-chips { justify-content:flex-start; } }
</style>
"""

LOGO = """
<svg class="au-logo" viewBox="0 0 48 48" aria-hidden="true">
  <defs><linearGradient id="au-g" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="#F7E7A6"/><stop offset=".5" stop-color="#D4AF37"/><stop offset="1" stop-color="#9C7A1C"/>
  </linearGradient></defs>
  <rect x="1" y="1" width="46" height="46" rx="6" fill="#0D0F12" stroke="url(#au-g)" stroke-width="2"/>
  <line x1="12" y1="12" x2="12" y2="36" stroke="#FF4D4F" stroke-width="1.5"/><rect x="9" y="18" width="6" height="12" fill="#FF4D4F"/>
  <line x1="24" y1="9" x2="24" y2="33" stroke="#00C176" stroke-width="1.5"/><rect x="21" y="14" width="6" height="13" fill="#00C176"/>
  <line x1="36" y1="6" x2="36" y2="28" stroke="url(#au-g)" stroke-width="1.5"/><rect x="33" y="9" width="6" height="14" fill="url(#au-g)"/>
  <polyline points="8,40 20,34 28,37 40,26" fill="none" stroke="url(#au-g)" stroke-width="2"/>
</svg>
"""


def aplicar() -> None:
    st.markdown(CSS, unsafe_allow_html=True)


def topo(subtitulo: str, chips: list[tuple[str, str]]) -> None:
    """chips: [(texto, classe)] com classe em '', 'on', 'alerta', 'perigo'."""
    c = "".join(f'<span class="au-chip {cls}">{html.escape(t)}</span>' for t, cls in chips)
    st.markdown(f'<div class="au-topo"><div class="au-marca">{LOGO}<div><div class="au-nome">AURUM</div>'
                f'<div class="au-sub">{html.escape(subtitulo)}</div></div></div><div class="au-chips">{c}</div></div>',
                unsafe_allow_html=True)


def fita(itens: list[tuple[str, float, float]]) -> None:
    """Fita de cotações correndo: [(ticker, preço, variação do dia)]."""
    if not itens:
        return
    def um(t, p, v):
        cls = "sobe" if v == v and v > 0 else "cai" if v == v and v < 0 else "neutro"
        seta = "▲" if cls == "sobe" else "▼" if cls == "cai" else "■"
        var = f"{v * 100:+.2f}%".replace(".", ",") if v == v else "—"
        preco = f"{p:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".") if p == p else "—"
        return f'<span class="au-cot"><b>{html.escape(t)}</b><span class="p">{preco}</span><span class="{cls}">{seta} {var}</span></span>'
    corpo = "".join(um(*i) for i in itens)
    st.markdown(f'<div class="au-fita" aria-label="Cotações"><div class="au-fita-trilho">{corpo}{corpo}</div></div>',
                unsafe_allow_html=True)


def cartoes(itens: list[tuple]) -> None:
    """itens: [(rótulo, valor, nota, classe_da_nota)] — nota e classe opcionais."""
    blocos = []
    for it in itens:
        rot, val = it[0], it[1]
        nota = it[2] if len(it) > 2 else ""
        cls = it[3] if len(it) > 3 else ""
        blocos.append(f'<div class="au-cartao"><div class="au-rotulo">{html.escape(str(rot))}</div>'
                      f'<div class="au-valor">{html.escape(str(val))}</div>'
                      + (f'<div class="au-nota {cls}">{html.escape(str(nota))}</div>' if nota else "") + "</div>")
    st.markdown(f'<div class="au-grade">{"".join(blocos)}</div>', unsafe_allow_html=True)


def _md_simples(texto: str) -> str:
    """Markdown simples (negrito, itálico, links, listas, parágrafos) → HTML, escapando todo o resto."""
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
    """Boletim do AURUM (ou de um agente)."""
    st.markdown(f'<div class="au-fala"><div class="au-cab">{html.escape(cabecalho)}</div>{_md_simples(texto_md)}</div>',
                unsafe_allow_html=True)


def agentes(cards: list[dict]) -> None:
    """cards: [{'icone','nome','cargo','status','a_favor','contra','vetos','favoritas','alerta'}]."""
    blocos = []
    for c in cards:
        vet = f'<span class="v">⛔ {c["vetos"]} veto(s)</span>' if c.get("vetos") else ""
        blocos.append(
            f'<div class="ag-card"><div class="ag-topo"><div class="ag-avatar">{c["icone"]}</div><div>'
            f'<div class="ag-nome">{html.escape(c["nome"])}</div><div class="ag-cargo">{html.escape(c["cargo"])}</div>'
            f'<div class="ag-status">{html.escape(c["status"])}</div></div></div>'
            f'<div class="ag-placar"><span class="a">▲ {c["a_favor"]} a favor</span><span class="c">▼ {c["contra"]} contra</span>{vet}</div>'
            f'<div class="ag-linha"><b>FAVORITAS</b> {html.escape(c["favoritas"] or "nenhuma hoje")}</div>'
            + (f'<div class="ag-linha"><b>DE OLHO</b> {html.escape(c["alerta"])}</div>' if c.get("alerta") else "")
            + "</div>")
    st.markdown(f'<div class="ag-grade">{"".join(blocos)}</div>', unsafe_allow_html=True)


def console(linhas: list[str], hora: str = "") -> None:
    corpo = "".join(f'<div><span class="h">{html.escape(hora)}</span>{html.escape(l)}</div>' for l in linhas)
    st.markdown(f'<div class="ag-console">{corpo}</div>', unsafe_allow_html=True)


def floco(pcts: dict[str, float], graus: dict[str, str], tamanho: int = 300) -> None:
    """Radar com as 5 notas por fator, comparadas ao setor (0–100). Quanto maior e mais verde, melhor."""
    nomes = list(pcts)
    n = len(nomes)
    cx = cy = tamanho / 2
    raio = tamanho * 0.34
    vals = [max(0.0, min(100.0, 0.0 if v != v else v)) / 100 for v in pcts.values()]
    media = sum(vals) / n if n else 0
    cor = VERDE if media >= 0.65 else DESTAQUE if media >= 0.45 else VERMELHO

    def ponto(i, r):
        ang = -math.pi / 2 + 2 * math.pi * i / n
        return cx + r * math.cos(ang), cy + r * math.sin(ang)
    aneis = "".join(
        f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in (ponto(i, raio * k / 4) for i in range(n)))}" '
        f'fill="none" stroke="#262A33" stroke-width="1"/>' for k in range(1, 5))
    eixos = "".join(f'<line x1="{cx}" y1="{cy}" x2="{ponto(i, raio)[0]:.1f}" y2="{ponto(i, raio)[1]:.1f}" stroke="#262A33"/>' for i in range(n))
    forma = " ".join(f"{x:.1f},{y:.1f}" for x, y in (ponto(i, raio * max(v, 0.04)) for i, v in enumerate(vals)))
    rotulos = ""
    for i, nome in enumerate(nomes):
        x, y = ponto(i, raio + 30)
        rotulos += (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="middle" font-family="Inter,sans-serif" font-size="13" '
                    f'font-weight="700" fill="#E8E6E1">{html.escape(nome)}</text>'
                    f'<text x="{x:.1f}" y="{y + 16:.1f}" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="13" '
                    f'font-weight="600" fill="{OURO}">{html.escape(graus.get(nome, "—"))}</text>')
    svg = (f'<svg viewBox="0 0 {tamanho} {tamanho}" width="100%" style="max-width:{tamanho}px" role="img" '
           f'aria-label="Notas por fator comparadas ao setor">{aneis}{eixos}'
           f'<polygon points="{forma}" fill="{cor}" fill-opacity=".22" stroke="{cor}" stroke-width="2"/>{rotulos}</svg>')
    st.markdown(f'<div style="display:flex;justify-content:center">{svg}</div>', unsafe_allow_html=True)




# ------------------------------------------------------------------ sala ilustrada (bonecos em mesas com computador)
# Aparência de cada agente: pele, cabelo, estilo do cabelo, roupa e acessório
APARENCIA = {
    "aurum":       {"pele": "#E0AC69", "cabelo": "#2B1B10", "estilo": "curto", "roupa": "#1F2430", "acessorio": "gravata"},
    "renda":       {"pele": "#F1C27D", "cabelo": "#8B4513", "estilo": "longo", "roupa": "#2E7D5B", "acessorio": ""},
    "fundamentos": {"pele": "#C68642", "cabelo": "#9E9E9E", "estilo": "curto", "roupa": "#3B4A6B", "acessorio": "oculos"},
    "valuation":   {"pele": "#FFDBAC", "cabelo": "#C9A227", "estilo": "longo", "roupa": "#7A2E4A", "acessorio": ""},
    "tendencia":   {"pele": "#8D5524", "cabelo": "#111111", "estilo": "curto", "roupa": "#1E5F8C", "acessorio": ""},
    "noticias":    {"pele": "#E0AC69", "cabelo": "#B5452B", "estilo": "longo", "roupa": "#5E4B8B", "acessorio": "oculos"},
    "previsor":    {"pele": "#F1C27D", "cabelo": "#3A2A5C", "estilo": "longo", "roupa": "#4B3A7A", "acessorio": "tiara"},
    "risco":       {"pele": "#C68642", "cabelo": "#1A1A1A", "estilo": "curto", "roupa": "#2F3B2F", "acessorio": "bone"},
    "atlas":       {"pele": "#FFDBAC", "cabelo": "#6B4423", "estilo": "curto", "roupa": "#6B5B3E", "acessorio": "chapeu"},
    "proventos":   {"pele": "#E0AC69", "cabelo": "#4A3728", "estilo": "curto", "roupa": "#1F5E3A", "acessorio": "oculos"},
    "entrada":     {"pele": "#8D5524", "cabelo": "#2B1B10", "estilo": "curto", "roupa": "#7A4B1E", "acessorio": "bone"},
    "conjunto":    {"pele": "#FFDBAC", "cabelo": "#1A1A1A", "estilo": "longo", "roupa": "#234A6B", "acessorio": "oculos"},
}


def _tela(aid: str) -> str:
    """Conteúdo do monitor (caixa 96×54) mostrando a especialidade de cada agente — com animação quando trabalha."""
    if aid == "aurum":
        barras = "".join(f'<rect class="sa-barra" style="animation-delay:{k * .25}s" x="{10 + k * 16}" y="{46 - h}" width="12" height="{h}" fill="{c}"/>'
                         for k, (h, c) in enumerate([(14, "#00C176"), (18, "#D4AF37"), (11, "#FF4D4F"), (21, "#00C176"), (16, "#4DA3FF")]))
        return ('<text x="48" y="20" text-anchor="middle" font-family="Inter,sans-serif" font-weight="800" font-size="14" fill="#D4AF37">AURUM</text>'
                + barras)
    if aid == "renda":  # proventos crescendo
        barras = "".join(f'<rect class="sa-cresce" style="animation-delay:{k * .3}s" x="{8 + k * 15}" y="{46 - h}" width="10" height="{h}" fill="#D4AF37"/>'
                         for k, h in enumerate([10, 14, 17, 22, 27, 34]))
        return barras + '<text x="10" y="11" font-family="IBM Plex Mono,monospace" font-size="8" fill="#00C176">R&#36; ↑ proventos</text>'
    if aid == "fundamentos":  # balanço com checagens aparecendo uma a uma
        linhas = "".join(f'<rect x="8" y="{8 + k * 9}" width="52" height="4" fill="#3B4A6B"/>'
                         f'<text class="sa-check" style="animation-delay:{k * .5}s" x="68" y="{13 + k * 9}" font-size="8" '
                         f'fill="{"#00C176" if k != 3 else "#FF4D4F"}">{"✓" if k != 3 else "✗"}</text>' for k in range(5))
        return linhas + '<text x="80" y="13" font-family="IBM Plex Mono,monospace" font-size="7" fill="#8B919C">F7</text>'
    if aid == "valuation":  # preço sendo desenhado abaixo do preço-teto
        return ('<line x1="4" y1="18" x2="92" y2="18" stroke="#00C176" stroke-width="1.5" stroke-dasharray="4 3"/>'
                '<text x="70" y="14" font-family="IBM Plex Mono,monospace" font-size="7" fill="#00C176">TETO</text>'
                '<polyline class="sa-desenha" points="4,30 18,26 30,36 44,32 58,42 72,38 90,44" fill="none" stroke="#F5A623" stroke-width="2"/>'
                '<text x="8" y="52" font-family="IBM Plex Mono,monospace" font-size="7" fill="#8B919C">margem +23%</text>')
    if aid == "tendencia":  # candles piscando + média
        velas = ""
        for k, (o, c, hi, lo) in enumerate([(30, 22, 18, 34), (22, 28, 19, 32), (28, 18, 14, 31), (18, 24, 15, 27), (24, 14, 10, 26), (14, 20, 11, 24)]):
            cor = "#00C176" if c < o else "#FF4D4F"
            x = 10 + k * 14
            velas += (f'<g class="sa-vela" style="animation-delay:{k * .2}s"><line x1="{x + 3}" y1="{hi}" x2="{x + 3}" y2="{lo}" stroke="{cor}"/>'
                      f'<rect x="{x}" y="{min(o, c)}" width="6" height="{abs(o - c) or 1}" fill="{cor}"/></g>')
        return velas + '<polyline points="6,30 30,26 54,22 78,18 92,16" fill="none" stroke="#4DA3FF" stroke-width="1.2"/>'
    if aid == "noticias":  # página de jornal rolando
        corpo = "".join(f'<rect x="44" y="{17 + k * 6}" width="{46 - (k % 3) * 8}" height="3" fill="#8B919C"/>' for k in range(12))
        return ('<defs><clipPath id="sa-clip-nina"><rect x="0" y="15" width="96" height="39"/></clipPath></defs>'
                '<rect x="6" y="5" width="84" height="7" fill="#E8E6E1"/>'
                f'<g clip-path="url(#sa-clip-nina)"><g class="sa-rola"><rect x="6" y="17" width="34" height="24" fill="#5E4B8B"/>{corpo}'
                '<rect x="6" y="47" width="34" height="20" fill="#2E7D5B"/></g></g>')
    if aid == "previsor":  # curva de probabilidade com o marcador andando
        return ('<path d="M4,48 C24,48 30,10 48,10 C66,10 72,48 92,48" fill="rgba(179,136,255,.25)" stroke="#B388FF" stroke-width="1.5"/>'
                '<g class="sa-marcador"><line x1="56" y1="8" x2="56" y2="48" stroke="#F5A623" stroke-dasharray="2 2"/>'
                '<text x="60" y="18" font-family="IBM Plex Mono,monospace" font-size="8" fill="#F5A623">58%</text></g>')
    if aid == "risco":  # escudo + radar girando com alvos piscando
        return ('<circle cx="66" cy="28" r="20" fill="none" stroke="#00C176" stroke-opacity=".5"/>'
                '<circle cx="66" cy="28" r="11" fill="none" stroke="#00C176" stroke-opacity=".5"/>'
                '<g class="sa-radar"><line x1="66" y1="28" x2="66" y2="8" stroke="#00C176" stroke-width="2"/></g>'
                '<circle class="sa-alvo" cx="74" cy="18" r="2" fill="#FF4D4F"/><circle class="sa-alvo" style="animation-delay:.8s" cx="58" cy="38" r="2" fill="#F5A623"/>'
                '<path d="M18,10 L34,15 L34,28 C34,38 26,44 18,47 C10,44 2,38 2,28 L2,15 Z" fill="#2F3B2F" stroke="#00C176" stroke-width="1.5"/>'
                '<text x="18" y="32" text-anchor="middle" font-size="12" fill="#00C176">✓</text>')
    if aid == "proventos":  # moedas empilhando mês a mês + faixa prevista
        moedas = "".join(f'<rect class="sa-barra" style="animation-delay:{k * .2}s" x="{8 + k * 14}" y="{48 - h}" width="10" height="{h}" rx="2" fill="#D4AF37"/>'
                         for k, h in enumerate([12, 14, 13, 16, 18, 17]))
        return (moedas + '<rect x="6" y="14" width="86" height="12" fill="rgba(0,193,118,.15)" stroke="#00C176" stroke-dasharray="2 2"/>'
                '<text x="50" y="11" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="7" fill="#00C176">R$ 12m</text>')
    if aid == "entrada":  # preço oscilando e a linha da ordem de compra
        return ('<polyline points="4,20 16,26 26,18 38,32 50,28 60,40 72,34 84,42 92,36" fill="none" stroke="#4DA3FF" stroke-width="1.5"/>'
                '<line x1="4" y1="40" x2="92" y2="40" stroke="#00C176" stroke-dasharray="3 2"/>'
                '<circle class="sa-alvo" cx="60" cy="40" r="3" fill="#00C176"/>'
                '<text x="6" y="50" font-family="IBM Plex Mono,monospace" font-size="7" fill="#00C176">ORDEM 80%</text>')
    if aid == "conjunto":  # vários sinais virando uma probabilidade
        linhas = "".join(f'<line x1="6" y1="{10 + k * 9}" x2="56" y2="28" stroke="{c}" stroke-opacity=".7"/>'
                         for k, c in enumerate(["#00C176", "#4DA3FF", "#F5A623", "#B388FF", "#FF4D4F"]))
        return (linhas + '<circle cx="66" cy="28" r="12" fill="#234A6B" stroke="#4DA3FF"/>'
                '<g class="sa-marcador"><text x="66" y="31" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="8" fill="#E8E6E1">p</text></g>'
                '<text x="84" y="31" font-family="IBM Plex Mono,monospace" font-size="7" fill="#00C176">52%</text>')
    if aid == "atlas":  # globo + lupa explorando
        return ('<circle cx="40" cy="28" r="20" fill="#1E3A5F" stroke="#4DA3FF"/>'
                '<ellipse class="sa-meridiano" cx="40" cy="28" rx="8" ry="20" fill="none" stroke="#4DA3FF"/>'
                '<line x1="20" y1="28" x2="60" y2="28" stroke="#4DA3FF"/><path d="M26,16 Q40,22 54,16 M26,40 Q40,34 54,40" fill="none" stroke="#4DA3FF"/>'
                '<g class="sa-lupa"><circle cx="74" cy="34" r="9" fill="rgba(245,166,35,.12)" stroke="#F5A623" stroke-width="2.5"/>'
                '<line x1="80" y1="41" x2="88" y2="50" stroke="#F5A623" stroke-width="3"/></g>')
    return ""


def _cabelo(estilo: str, cor: str) -> str:
    if estilo == "longo":
        return (f'<path d="M62,64 C60,46 72,38 82,40 C94,42 98,52 96,62 L98,92 C92,88 88,80 88,70 L74,70 C72,80 68,88 62,92 Z" fill="{cor}"/>')
    return f'<path d="M64,60 C64,44 76,38 84,40 C94,42 98,50 96,58 C90,52 80,50 70,54 Z" fill="{cor}"/>'


def _acessorio(tipo: str) -> str:
    return {
        "gravata": '<path d="M80,86 L86,86 L84,92 L88,112 L83,118 L78,112 L82,92 Z" fill="#D4AF37"/>',
        "oculos": '<g fill="none" stroke="#111" stroke-width="1.6"><circle cx="86" cy="62" r="4.5"/><circle cx="96" cy="62" r="4.5"/>'
                  '<line x1="90.5" y1="62" x2="91.5" y2="62"/></g>',
        "tiara": '<path d="M66,50 Q80,36 96,48" fill="none" stroke="#B388FF" stroke-width="3"/><circle cx="81" cy="41" r="2.5" fill="#F5A623"/>',
        "bone": '<path d="M64,52 C66,38 92,36 96,50 Z" fill="#2F3B2F"/><path d="M92,50 L108,52 L94,55 Z" fill="#2F3B2F"/>',
        "chapeu": '<ellipse cx="81" cy="46" rx="24" ry="5" fill="#8B6B3E"/><path d="M68,46 C68,32 94,32 94,46 Z" fill="#8B6B3E"/>'
                  '<rect x="68" y="42" width="26" height="3" fill="#5A4426"/>',
    }.get(tipo, "")


def boneco(aid: str, estado: str) -> str:
    """SVG animado de um agente na mesa com computador. A cena muda com o estado:
    trabalhando (digita, cabeça acompanha a tela), vigiando (olha de um lado a outro, mexe o mouse),
    pausa (recosta, toma café de tempos em tempos)."""
    ap = APARENCIA.get(aid, APARENCIA["aurum"])
    ativo = estado in ("trabalhando", "vigiando")
    pausa = not ativo and estado != "erro"
    tela_op = "1" if ativo else ".22"
    tela_brilho = {"trabalhando": "#122018", "vigiando": "#0E1A2A", "erro": "#2A1010"}.get(estado, "#0B0C0F")
    cls_cabeca = {"trabalhando": "sa-acena", "vigiando": "sa-olha", "pausa": "sa-relaxa"}.get(estado, "")
    balao = {
        "trabalhando": '<g class="sa-pontos"><circle cx="40" cy="22" r="2.6"/><circle cx="49" cy="22" r="2.6"/><circle cx="58" cy="22" r="2.6"/></g>',
        "vigiando": '<text x="49" y="27" text-anchor="middle" font-size="13">👀</text>',
        "erro": '<text x="49" y="27" text-anchor="middle" font-size="14" fill="#FF4D4F" font-weight="800">!</text>',
    }.get(estado, '<text x="49" y="27" text-anchor="middle" font-family="Inter,sans-serif" font-size="12" font-weight="700" fill="#8B919C" class="sa-zz">zZ</text>')
    pele, roupa = ap["pele"], ap["roupa"]
    # braço de trás (mais escuro) e braço da frente — o que cada um faz depende do estado
    if estado == "trabalhando":
        braco_tras = (f'<g class="sa-tecla2"><path d="M78,94 Q98,108 116,122" fill="none" stroke="{roupa}" stroke-width="8" '
                      f'stroke-linecap="round" opacity=".75"/><circle cx="117" cy="122" r="4" fill="{pele}" opacity=".85"/></g>')
        braco_frente = (f'<g class="sa-tecla1"><path d="M84,92 Q106,104 128,120" fill="none" stroke="{roupa}" stroke-width="9" stroke-linecap="round"/>'
                        f'<circle cx="130" cy="121" r="4.5" fill="{pele}"/></g>')
    elif estado == "vigiando":
        braco_tras = (f'<path d="M78,94 Q96,108 112,122" fill="none" stroke="{roupa}" stroke-width="8" stroke-linecap="round" opacity=".75"/>'
                      f'<circle cx="113" cy="122" r="4" fill="{pele}" opacity=".85"/>')
        braco_frente = (f'<g class="sa-mouse"><path d="M84,92 Q118,110 150,124" fill="none" stroke="{roupa}" stroke-width="9" stroke-linecap="round"/>'
                        f'<circle cx="152" cy="125" r="4.5" fill="{pele}"/><ellipse cx="156" cy="129" rx="5" ry="3" fill="#30353F"/></g>')
    else:  # pausa: segura o café e de tempos em tempos toma um gole
        braco_tras = (f'<path d="M78,96 Q88,112 100,118" fill="none" stroke="{roupa}" stroke-width="8" stroke-linecap="round" opacity=".75"/>'
                      f'<circle cx="101" cy="118" r="4" fill="{pele}" opacity=".85"/>')
        braco_frente = (f'<g class="sa-gole"><path d="M84,92 Q104,108 118,118" fill="none" stroke="{roupa}" stroke-width="9" stroke-linecap="round"/>'
                        f'<circle cx="120" cy="118" r="4.5" fill="{pele}"/>'
                        '<rect x="117" y="104" width="11" height="13" rx="2" fill="#E8E6E1"/>'
                        '<path d="M128,107 q5,2 0,7" fill="none" stroke="#E8E6E1" stroke-width="2"/>'
                        '<path class="sa-vapor" d="M120,100 q-3,-5 0,-10 M125,100 q-3,-5 0,-10" fill="none" stroke="#8B919C" stroke-width="1.4"/></g>')
    gravata = _acessorio("gravata") if ap["acessorio"] == "gravata" else ""
    outros = _acessorio(ap["acessorio"]) if ap["acessorio"] != "gravata" else ""
    olho = '<g class="sa-olhos"><circle cx="92" cy="60" r="1.8" fill="#1A1A1A"/></g>' if not pausa else \
           '<path d="M89,61 q3,2 6,0" fill="none" stroke="#1A1A1A" stroke-width="1.6" stroke-linecap="round"/>'
    return f"""<svg viewBox="0 0 280 200" width="100%" role="img" aria-label="{html.escape(EQUIPE_NOME.get(aid, aid))} {estado}">
  <rect width="280" height="132" fill="#15171C"/><rect y="132" width="280" height="68" fill="#0E1013"/>
  <line x1="0" y1="132" x2="280" y2="132" stroke="#262A33"/>
  <rect x="196" y="14" width="64" height="38" rx="2" fill="#0F1114" stroke="#262A33"/>
  <polyline points="200,44 212,36 222,40 234,26 246,30 256,20" fill="none" stroke="#2C3340" stroke-width="2"/>
  <g transform="translate(14,4)"><rect x="12" y="8" width="74" height="30" rx="15" fill="#20242C" stroke="#30353F"/>
    <path d="M30,37 L26,46 L38,37 Z" fill="#20242C"/><g fill="#E8E6E1">{balao}</g></g>
  <g class="{"sa-cadeira" if pausa else ""}"><rect x="30" y="96" width="38" height="8" rx="3" fill="#2A2E36"/>
    <rect x="32" y="{"88" if pausa else "104"}" width="6" height="{"56" if pausa else "40"}" fill="#2A2E36"/></g>
  <rect x="24" y="144" width="54" height="5" rx="2" fill="#2A2E36"/><rect x="48" y="149" width="4" height="30" fill="#2A2E36"/>
  <rect x="34" y="179" width="34" height="4" rx="2" fill="#2A2E36"/>
  {braco_tras}
  <g class="sa-respira {"sa-recosta" if pausa else ""}">
    <rect x="66" y="80" width="30" height="44" rx="10" fill="{roupa}"/>{gravata}
    <g class="{cls_cabeca}"><rect x="76" y="70" width="10" height="12" fill="{pele}"/>
      <circle cx="83" cy="60" r="15" fill="{pele}"/>{_cabelo(ap["estilo"], ap["cabelo"])}{olho}{outros}</g>
  </g>
  <rect x="70" y="122" width="40" height="10" rx="5" fill="#2B2F38"/><rect x="104" y="122" width="8" height="34" rx="3" fill="#2B2F38"/>
  <rect x="100" y="156" width="16" height="5" rx="2" fill="#1A1C21"/>
  <rect x="100" y="132" width="172" height="10" rx="2" fill="#5C4326"/><rect x="104" y="142" width="6" height="50" fill="#4A361F"/>
  <rect x="262" y="142" width="6" height="50" fill="#4A361F"/>
  <rect x="116" y="126" width="40" height="6" rx="1.5" fill="#30353F"/>
  {braco_frente}
  <rect x="182" y="116" width="8" height="16" fill="#30353F"/><rect x="170" y="129" width="32" height="4" rx="1" fill="#30353F"/>
  <rect x="136" y="56" width="104" height="62" rx="4" fill="{tela_brilho}" stroke="#3A404C" stroke-width="2"/>
  <g transform="translate(140,60)" opacity="{tela_op}" class="{"sa-tela sa-anima" if ativo else ""}">{_tela(aid)}</g>
  {"" if ativo else '<text x="188" y="94" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="9" fill="#3A404C">em pausa</text>'}
  <rect x="210" y="133" width="58" height="9" rx="1" fill="#D4AF37"/>
  <text x="239" y="140.5" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="7" font-weight="700" fill="#111">{html.escape(EQUIPE_NOME.get(aid, aid).upper())}</text>
</svg>"""


EQUIPE_NOME = {"aurum": "AURUM", "renda": "Dora", "fundamentos": "Fausto", "valuation": "Vitória", "tendencia": "Téo",
               "noticias": "Nina", "previsor": "Íris", "risco": "Rex", "atlas": "Atlas",
               "proventos": "Otto", "entrada": "Bento", "conjunto": "Sofia"}

CSS_SALA = """
<style>
.sa-parede { position:relative; border:1px solid var(--borda); border-radius:6px 6px 0 0; overflow:hidden; background:#121419; }
.sa-chao { display:grid; grid-template-columns: repeat(auto-fit, minmax(250px, 1fr)); gap:0; border:1px solid var(--borda);
  border-top:none; border-radius:0 0 6px 6px; background:#0E1013; margin-bottom:14px; }
.sa-baia { border-right:1px solid #1C1F26; border-bottom:1px solid #1C1F26; padding:8px 10px 12px; }
.sa-baia.trabalhando { background: linear-gradient(180deg, rgba(0,193,118,.06), transparent 60%); }
.sa-baia.vigiando { background: linear-gradient(180deg, rgba(77,163,255,.07), transparent 60%); }
.sa-info { display:flex; justify-content:space-between; align-items:baseline; gap:8px; margin-top:2px; }
.sa-nome { font-weight:800; } .sa-cargo { font-size:.78rem; color: var(--apagado); }
.sa-tarefa { font-size:.84rem; margin-top:4px; min-height:2.5em; line-height:1.35; }
.sa-hora { font-family: var(--mono); font-size:.7rem; color: var(--apagado); }
.sa-baia svg * { transform-box: fill-box; }
/* corpo: todos respiram */
.sa-respira { animation: respira 3.2s ease-in-out infinite; transform-origin: 50% 100%; }
@keyframes respira { 50% { transform: translateY(-1.2px) scaleY(1.01); } }
.sa-recosta { transform: rotate(-6deg); transform-origin: 30% 100%; animation: recosta 3.6s ease-in-out infinite; }
@keyframes recosta { 0%, 100% { transform: rotate(-6deg); } 50% { transform: rotate(-7.5deg) translateY(-1px); } }
/* trabalhando: digita com as duas mãos e acompanha a tela */
.sa-tecla1 { animation: tecla .32s ease-in-out infinite alternate; transform-origin: 0% 0%; }
.sa-tecla2 { animation: tecla .32s ease-in-out infinite alternate-reverse; transform-origin: 0% 0%; }
@keyframes tecla { from { transform: translateY(-1.5px) rotate(-1.5deg); } to { transform: translateY(1.2px) rotate(1.5deg); } }
.sa-acena { animation: acena 1.8s ease-in-out infinite; transform-origin: 40% 100%; }
@keyframes acena { 0%, 100% { transform: rotate(0deg); } 30% { transform: rotate(4deg); } 60% { transform: rotate(-1deg); } }
/* vigiando: olha de um lado a outro e mexe o mouse */
.sa-olha { animation: olha 4s ease-in-out infinite; transform-origin: 40% 100%; }
@keyframes olha { 0%, 100% { transform: rotate(0); } 25% { transform: rotate(6deg); } 50% { transform: rotate(-4deg); } 75% { transform: rotate(3deg); } }
.sa-olhos { animation: olhos 4s ease-in-out infinite; }
@keyframes olhos { 25% { transform: translateX(2px); } 50% { transform: translateX(-2px); } }
.sa-mouse { animation: mouse 2.2s ease-in-out infinite; }
@keyframes mouse { 25% { transform: translate(3px, -1px); } 50% { transform: translate(-2px, 1px); } 75% { transform: translate(2px, 1px); } }
/* pausa: toma café de tempos em tempos */
.sa-gole { animation: gole 7s ease-in-out infinite; transform-origin: 0% 0%; }
@keyframes gole { 0%, 55%, 100% { transform: rotate(0); } 68%, 82% { transform: rotate(-62deg) translate(-6px, -4px); } }
.sa-relaxa { animation: relaxa 7s ease-in-out infinite; transform-origin: 40% 100%; }
@keyframes relaxa { 0%, 55%, 100% { transform: rotate(-4deg); } 68%, 82% { transform: rotate(-12deg); } }
/* balões e telas */
.sa-pontos circle { animation: ponto 1.2s infinite; } .sa-pontos circle:nth-child(2) { animation-delay: .2s; } .sa-pontos circle:nth-child(3) { animation-delay: .4s; }
@keyframes ponto { 0%, 60%, 100% { opacity: .25; } 30% { opacity: 1; } }
.sa-zz { animation: flutua 2.6s ease-in-out infinite; } @keyframes flutua { 50% { transform: translateY(-3px); opacity:.6; } }
.sa-vapor { animation: vapor 2s ease-in-out infinite; } @keyframes vapor { 0% { opacity:0; transform: translateY(2px); } 50% { opacity:1; } 100% { opacity:0; transform: translateY(-4px); } }
.sa-tela { animation: brilho 3s ease-in-out infinite; } @keyframes brilho { 50% { opacity: .85; } }
.sa-anima .sa-barra { animation: barra 1.6s ease-in-out infinite; transform-origin: 50% 100%; }
@keyframes barra { 50% { transform: scaleY(.55); } }
.sa-anima .sa-cresce { animation: cresce 2.4s ease-out infinite; transform-origin: 50% 100%; }
@keyframes cresce { 0% { transform: scaleY(.15); } 60%, 100% { transform: scaleY(1); } }
.sa-anima .sa-check { animation: check 2.5s steps(1) infinite; } @keyframes check { 0% { opacity: 0; } 20%, 100% { opacity: 1; } }
.sa-anima .sa-desenha { stroke-dasharray: 130; animation: desenha 2.8s ease-in-out infinite; }
@keyframes desenha { 0% { stroke-dashoffset: 130; } 70%, 100% { stroke-dashoffset: 0; } }
.sa-anima .sa-vela { animation: vela 1.4s ease-in-out infinite; } @keyframes vela { 50% { transform: translateY(-2px); opacity: .6; } }
.sa-anima .sa-rola { animation: rola 5s linear infinite; } @keyframes rola { from { transform: translateY(0); } to { transform: translateY(-30px); } }
.sa-anima .sa-marcador { animation: marcador 3s ease-in-out infinite; } @keyframes marcador { 50% { transform: translateX(-18px); } }
.sa-anima .sa-radar { transform-origin: 50% 100%; animation: gira 2.4s linear infinite; } @keyframes gira { to { transform: rotate(360deg); } }
.sa-anima .sa-alvo { animation: alvo 1.6s ease-in-out infinite; } @keyframes alvo { 50% { opacity: .1; } }
.sa-anima .sa-meridiano { transform-origin: 50% 50%; animation: meridiano 3s ease-in-out infinite; } @keyframes meridiano { 50% { transform: scaleX(.2); } }
.sa-anima .sa-lupa { animation: lupa 4s ease-in-out infinite; }
@keyframes lupa { 25% { transform: translate(-30px, -10px); } 50% { transform: translate(-44px, 4px); } 75% { transform: translate(-18px, 8px); } }
@media (prefers-reduced-motion: reduce) { .sa-baia svg * { animation: none !important; } }
</style>
"""


def _parede(pregao: bool, hora: int) -> str:
    noite = hora >= 18 or hora < 6
    ceu = "#0B1426" if noite else "#5B8DB8"
    predios = "".join(f'<rect x="{x}" y="{y}" width="{w}" height="{90 - y}" fill="{"#0A0F1A" if noite else "#3E5F7E"}"/>'
                      for x, y, w in [(6, 40, 18), (26, 28, 14), (42, 46, 20), (64, 22, 12), (78, 36, 18)])
    luzes = "".join(f'<rect x="{x}" y="{y}" width="2" height="2" fill="#F5D76E"/>' for x, y in
                    [(10, 48), (16, 60), (30, 34), (46, 54), (52, 66), (68, 30), (82, 44), (88, 58)]) if noite else ""
    janela = f'<g><rect width="100" height="90" fill="{ceu}"/>{predios}{luzes}<rect width="100" height="90" fill="none" stroke="#2A2E36" stroke-width="4"/><line x1="50" y1="0" x2="50" y2="90" stroke="#2A2E36" stroke-width="3"/></g>'
    placa = ("PREGÃO ABERTO" if pregao else "PREGÃO FECHADO")
    cor = "#00C176" if pregao else "#8B919C"
    return f'''<svg viewBox="0 0 1000 120" width="100%" role="img" aria-label="Sala da equipe AURUM">
  <rect width="1000" height="120" fill="#15171C"/>
  <g transform="translate(40,14)">{janela}</g><g transform="translate(860,14)">{janela}</g>
  <rect x="300" y="18" width="400" height="74" rx="6" fill="#0A0B0D" stroke="#D4AF37" stroke-width="2"/>
  <text x="500" y="52" text-anchor="middle" font-family="Inter,sans-serif" font-weight="800" font-size="26" letter-spacing="8" fill="#D4AF37">AURUM</text>
  <text x="500" y="76" text-anchor="middle" font-family="IBM Plex Mono,monospace" font-size="12" letter-spacing="3" fill="#8B919C">MESA DE OPERAÇÕES · <tspan fill="{cor}">● {placa}</tspan></text>
  <g transform="translate(176,30)"><circle r="22" fill="#0F1114" stroke="#30353F" stroke-width="3"/>
    <line x1="0" y1="0" x2="0" y2="-14" stroke="#E8E6E1" stroke-width="2.5" transform="rotate({(hora % 12) * 30})"/>
    <line x1="0" y1="0" x2="0" y2="-18" stroke="#F5A623" stroke-width="1.5" transform="rotate(0)"/></g>
  <rect x="740" y="40" width="70" height="52" rx="4" fill="#1E5A3A"/><circle cx="775" cy="38" r="16" fill="#2E7D5B"/><circle cx="762" cy="46" r="12" fill="#2E7D5B"/><circle cx="788" cy="46" r="12" fill="#2E7D5B"/>
  <line x1="0" y1="118" x2="1000" y2="118" stroke="#262A33" stroke-width="2"/>
</svg>'''


def _uma_linha(svg: str) -> str:
    """O Streamlit trata o HTML como markdown: linha em branco encerra o bloco e '$' vira fórmula. Tudo numa linha e '$' escapado."""
    return re.sub(r"\n\s*", " ", svg).replace("$", "&#36;")


def sala_ilustrada(mesas: list[dict], pregao: bool, hora: int) -> None:
    """A sala: parede com janelas e o painel da mesa de operações; embaixo, cada agente na sua baia."""
    rot = {"trabalhando": "● trabalhando", "vigiando": "● vigiando", "pausa": "○ em pausa", "erro": "! atenção"}
    cor = {"trabalhando": "var(--verde)", "vigiando": "var(--azul)", "pausa": "var(--apagado)", "erro": "var(--vermelho)"}
    baias = []
    for m in mesas:
        e = m.get("estado", "pausa")
        baias.append(
            f'<div class="sa-baia {e}">{_uma_linha(boneco(m["id"], e))}'
            f'<div class="sa-info"><div><span class="sa-nome">{html.escape(m["nome"])}</span> '
            f'<span class="sa-cargo">· {html.escape(m["cargo"])}</span></div>'
            f'<span class="sa-hora" style="color:{cor.get(e)}">{rot.get(e, e)}</span></div>'
            f'<div class="sa-tarefa">{html.escape(m.get("tarefa") or "aguardando a primeira tarefa")}</div>'
            f'<div class="sa-hora">{html.escape(m.get("desde") or "")}</div></div>')
    st.markdown(_uma_linha(CSS_SALA) + f'<div class="sa-parede">{_uma_linha(_parede(pregao, hora))}</div>'
                f'<div class="sa-chao">{"".join(baias)}</div>',
                unsafe_allow_html=True)


def sala_3d(mesas: list[dict], pregao: bool, hora: int, fita_itens: list[tuple], altura: int = 620) -> None:
    """Sala dos Agentes em 3D (Three.js, servido localmente por /app/static). Gira sozinha; arraste para olhar em volta."""
    import json
    dados = {
        "pregao": bool(pregao), "hora": int(hora),
        "fita": [[t, round(float(p), 2), round(float(v), 4) if v == v else 0.0] for t, p, v in fita_itens[:16]],
        "agentes": [{"id": m["id"], "nome": m["nome"], "cargo": m["cargo"], "estado": m.get("estado", "pausa"),
                     "aparencia": APARENCIA.get(m["id"], APARENCIA["aurum"])} for m in mesas],
    }
    pagina = f"""
<div id="sala3d" style="width:100%;height:{altura}px;position:relative;border:1px solid #262A33;border-radius:6px;overflow:hidden;background:#0A0B0D">
  <div id="sala3d-carregando" style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
       color:#8B919C;font:600 14px 'IBM Plex Mono',monospace;text-align:center;padding:20px">Montando a sala em 3D…</div>
  <div style="position:absolute;left:10px;bottom:8px;color:#8B919C;font:500 12px Inter,Arial,sans-serif;pointer-events:none">
    arraste para girar · role para aproximar</div>
</div>
<script>window.SALA_DADOS = {json.dumps(dados, ensure_ascii=False)};</script>
<script type="importmap">{{"imports": {{"three": "/app/static/three.module.min.js", "three/addons/": "/app/static/"}}}}</script>
<script type="module" src="/app/static/sala3d.js"></script>
<script>
  setTimeout(function () {{
    var c = document.getElementById('sala3d-carregando');
    if (c) c.textContent = 'Não foi possível abrir a sala em 3D aqui. Abra o painel pelo "Abrir Painel Acoes.bat" ' +
                           '(de dentro da pasta radar_acoes) ou use a visão 2D.';
  }}, 9000);
</script>"""
    if hasattr(st, "iframe"):  # Streamlit novo: components.html foi aposentado
        st.iframe(pagina, height=altura + 4)
    else:
        import streamlit.components.v1 as components
        components.html(pagina, height=altura + 4)
