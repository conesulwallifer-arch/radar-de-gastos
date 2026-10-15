"""Lista de ações da B3 acompanhadas: empresas com histórico de proventos, de setores perenes.

Para mudar a lista, crie dados_acoes/minha_lista.txt com um código por linha (ex.: TAEE11).
Se algum código mudar na B3 (fusão, troca de ticker), ele aparece como "sem dados" no relatório.
"""
from __future__ import annotations

from . import DADOS

SETORES: dict[str, list[str]] = {
    "Bancos": ["ITUB4", "BBDC4", "BBAS3", "SANB11", "ABCB4", "BRSR6", "BPAC11"],
    "Holdings": ["ITSA4", "BRAP4", "SIMH3"],
    "Seguros": ["BBSE3", "CXSE3", "PSSA3"],
    "Energia elétrica": ["TAEE11", "EGIE3", "CMIG4", "CPLE3", "ISAE4", "ALUP11", "ENGI11", "CPFE3", "EQTL3", "AURE3"],
    "Saneamento": ["SAPR11", "SBSP3", "CSMG3"],
    "Telecom": ["VIVT3", "TIMS3"],
    "Petróleo e gás": ["PETR4", "PRIO3", "VBBR3", "UGPA3", "RECV3"],
    "Mineração e siderurgia": ["VALE3", "CMIN3", "GGBR4", "GOAU4"],
    "Papel e celulose": ["KLBN11", "SUZB3"],
    "Bolsa e serviços financeiros": ["B3SA3"],
    "Bens industriais": ["WEGE3", "LEVE3", "TUPY3", "POMO4", "RANI3", "UNIP6"],
    "Consumo": ["ABEV3", "MDIA3", "GRND3", "SLCE3"],
    "Saúde": ["ODPV3", "FLRY3"],
    "Construção": ["CYRE3", "DIRR3", "EZTC3"],
    "Shoppings": ["MULT3", "ALOS3"],
}

SETOR_DE = {t: s for s, ts in SETORES.items() for t in ts}


def tickers() -> list[str]:
    arq = DADOS / "minha_lista.txt"
    if arq.exists():
        lista = [l.strip().upper() for l in arq.read_text(encoding="utf-8").splitlines()]
        lista = [l for l in lista if l and not l.startswith("#")]
        if lista:
            return list(dict.fromkeys(lista))
    return [t for ts in SETORES.values() for t in ts]


def setor(ticker: str, info_setor: str | None = None) -> str:
    return SETOR_DE.get(ticker) or info_setor or "Outros"
