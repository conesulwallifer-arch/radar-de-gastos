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
