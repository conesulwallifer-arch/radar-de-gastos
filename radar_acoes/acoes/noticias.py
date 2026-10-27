"""Notícias por empresa (Google Notícias, RSS público) com classificação simples de tom e de assunto."""
from __future__ import annotations

import re
import unicodedata
import urllib.parse as up
import xml.etree.ElementTree as ET
from datetime import datetime
from email.utils import parsedate_to_datetime

import requests

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36",
      "Accept-Language": "pt-BR,pt;q=0.9"}

POSITIVAS = ["lucro recorde", "lucro sobe", "lucro cresce", "alta", "altas", "dispara", "disparam", "sobe", "sobem", "avanca", "avancam",
             "supera", "superam", "recorde",
             "aprova dividendos", "anuncia dividendos", "anuncia jcp", "juros sobre capital", "recompra", "eleva",
             "upgrade", "recomendacao de compra", "otimista", "melhora", "crescimento", "aumenta dividendos", "dividendos extraordinarios",
             "bonificacao", "elevacao de rating", "acima do esperado", "forte"]
NEGATIVAS = ["prejuizo", "queda", "quedas", "despenca", "despencam", "cai", "caem", "recua", "recuam", "rebaixa", "downgrade", "abaixo do esperado",
             "investigacao", "multa", "processo", "fraude", "recuperacao judicial", "corta dividendos", "reduz dividendos",
             "suspende dividendos", "endividamento", "rombo", "renuncia", "greve", "acidente", "interferencia",
             "recomendacao de venda", "pessimista", "piora", "calote", "rebaixamento"]

ASSUNTOS = {
    "Proventos": ["dividendo", "jcp", "juros sobre capital", "provento", "data com", "data-com", "bonificacao", "payout"],
    "Resultado": ["lucro", "prejuizo", "balanco", "resultado", "trimestre", "receita", "ebitda", "4t", "3t", "2t", "1t"],
    "Fato relevante": ["fato relevante", "comunicado", "aquisicao", "fusao", "incorporacao", "oferta", "follow-on", "recompra"],
    "Recomendação": ["recomendacao", "preco-alvo", "preco alvo", "rebaixa", "eleva", "carteira recomendada", "rating"],
    "Governança": ["ceo", "presidente", "conselho", "governo", "interferencia", "investigacao", "cvm", "processo"],
}


def _norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode()


def _prefixo(texto: str, termos: list[str]) -> int:
    return sum(1 for t in termos if re.search(rf"\b{re.escape(t)}", texto))  # assuntos: "dividendo" pega "dividendos"


def _conta(texto: str, termos: list[str]) -> int:
    return sum(1 for t in termos if re.search(rf"\b{re.escape(t)}\b", texto))  # palavra inteira: "cai" não casa com "caixa"


def classificar(titulo: str) -> dict:
    t = _norm(titulo)
    pos, neg = _conta(t, POSITIVAS), _conta(t, NEGATIVAS)
    tom = "positiva" if pos > neg else "negativa" if neg > pos else "neutra"
    assuntos = [a for a, termos in ASSUNTOS.items() if _prefixo(t, termos)]
    return {"tom": tom, "pontos": pos - neg, "assuntos": assuntos or ["Geral"]}


def buscar(ticker: str, nome: str | None = None, dias: int = 30, n: int = 20) -> list[dict]:
    termos = [f'"{ticker}"']
    if nome:
        curto = re.sub(r"\b(S\.?A\.?|SA|Cia|Companhia|Participacoes|Participações|Holding)\b\.?", "", nome, flags=re.I).strip(" .,-")
        if len(curto) >= 3:
            termos.append(f'"{curto}"')
    return buscar_consulta(f"({' OR '.join(termos)})", dias, n, ticker=ticker)


def buscar_consulta(consulta: str, dias: int = 7, n: int = 20, ticker: str = "") -> list[dict]:
    """Busca livre no Google Notícias (ex.: 'Copom Selic'), com tom e assunto de cada manchete."""
    q = f"{consulta} when:{dias}d"
    url = f"https://news.google.com/rss/search?q={up.quote(q)}&hl=pt-BR&gl=BR&ceid=BR:pt-419"
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
            quando = parsedate_to_datetime(it.findtext("pubDate") or "").replace(tzinfo=None)
        except Exception:  # noqa: BLE001
            quando = None
        itens.append({"ticker": ticker, "titulo": titulo, "fonte": fonte, "quando": quando,
                      "link": it.findtext("link") or "", **classificar(titulo)})
    itens.sort(key=lambda x: x["quando"] or datetime.min, reverse=True)
    return itens[:n]


def resumo(itens: list[dict]) -> dict:
    """Saldo de tom das notícias: de -1 (só negativas) a +1 (só positivas)."""
    if not itens:
        return {"qtd": 0, "saldo": 0.0, "positivas": 0, "negativas": 0}
    pos = sum(1 for x in itens if x["tom"] == "positiva")
    neg = sum(1 for x in itens if x["tom"] == "negativa")
    return {"qtd": len(itens), "saldo": (pos - neg) / len(itens), "positivas": pos, "negativas": neg}
