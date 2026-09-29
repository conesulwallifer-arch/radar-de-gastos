"""Manchetes recentes (Google Notícias, RSS público). Mostra só título, veículo, data e link para a matéria original."""
from __future__ import annotations

import urllib.parse as up
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

import requests
import streamlit as st

from radar.util import UA


@st.cache_data(ttl=1800, show_spinner=False)
def buscar(termo: str, n: int = 15) -> list[dict]:
    url = f"https://news.google.com/rss/search?q={up.quote(termo)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
    try:
        r = requests.get(url, headers=UA, timeout=20)
        r.raise_for_status()
        raiz = ET.fromstring(r.content)
    except Exception:  # noqa: BLE001
        return []
    itens = []
    for it in raiz.iter("item"):
        titulo = (it.findtext("title") or "").strip()
        fonte = (it.findtext("source") or "").strip()
        if fonte and titulo.endswith(" - " + fonte):
            titulo = titulo[: -len(fonte) - 3]
        try:
            quando = parsedate_to_datetime(it.findtext("pubDate") or "")
        except Exception:  # noqa: BLE001
            quando = None
        itens.append({"titulo": titulo, "fonte": fonte, "quando": quando, "link": it.findtext("link") or ""})
    itens.sort(key=lambda x: x["quando"] or 0, reverse=True)
    return itens[:n]


def mostrar(termo: str, n: int = 15, chave: str = "nt"):
    itens = buscar(termo, n)
    if not itens:
        st.caption("Nenhuma notícia encontrada agora (ou o serviço de notícias está fora do ar).")
        return
    for x in itens:
        data = f"{x['quando']:%d/%m/%Y %H:%M}" if x["quando"] else ""
        st.markdown(f"- [{x['titulo']}]({x['link']})  \n  <span style='color:#8a8f98;font-size:12px'>{x['fonte']} · {data}</span>",
                    unsafe_allow_html=True)
    st.caption("Manchetes do Google Notícias; clique para ler no site do veículo. O radar não escreve nem edita notícias.")
