"""Apuração diária do Radar de Ações.

    python apurar.py                     # apura, salva o relatório e envia alertas (Telegram/e-mail, se configurado)
    python apurar.py --aporte 1000       # inclui a sugestão de compra para um aporte de R$ 1.000
    python apurar.py --demo              # testa com dados fictícios, sem internet
    python apurar.py --tickers TAEE11 BBSE3 ITSA4

Agende para rodar todo dia útil após o fechamento da B3 (ex.: 19h). Veja o README.
"""
from __future__ import annotations

import argparse
import os
import pickle
import sys
from datetime import date

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from acoes import AVISO, DADOS, alertas, analise, aporte, backtest, dados, demo, macro, meta, noticias, plano, previsao, universo  # noqa: E402

HIST = DADOS / "historico"
REL = DADOS / "relatorios"
ULTIMO = DADOS / "ultimo.pkl"


def _tx(x: float) -> str:
    return f"{x * 100:.2f}%".replace(".", ",")


def anterior(hoje: date) -> pd.DataFrame | None:
    arqs = sorted(p for p in HIST.glob("ranking_*.csv") if p.stem < f"ranking_{hoje:%Y-%m-%d}")
    return pd.read_csv(arqs[-1]) if arqs else None


def apurar(tickers: list[str], valor_aporte: float = 0.0, usar_demo: bool = False, com_noticias: bool = True,
           enviar: bool = True, forcar: bool = False) -> dict:
    hoje = date.today()
    HIST.mkdir(parents=True, exist_ok=True)
    REL.mkdir(parents=True, exist_ok=True)
    cart = aporte.ler_carteira()
    tickers = list(dict.fromkeys(tickers + cart["ticker"].tolist()))

    print(f"1/5 Coletando preços, proventos e indicadores de {len(tickers)} ações...")
    base = {t: demo.gerar(t) for t in tickers} if usar_demo else dados.coletar_varios(tickers, forcar=forcar)
    sem_dados = [t for t in tickers if t not in base]
    if not base:
        raise SystemExit("Nenhum dado coletado. Verifique a internet (ou rode com --demo).")

    print("2/5 Calculando indicadores e notas...")
    rk = analise.ranking(base)

    print("3/5 Buscando notícias...")
    news: dict[str, list[dict]] = {}
    if com_noticias:
        alvo = list(dict.fromkeys(rk.head(30)["ticker"].tolist() + cart["ticker"].tolist()))
        for t in alvo:
            if t in base:
                nome = base[t]["info"].get("shortName") or base[t]["info"].get("longName")
                news[t] = demo.noticias(t) if usar_demo else noticias.buscar(t, nome, dias=30)
        rk = analise.ranking(base, {t: noticias.resumo(v)["saldo"] for t, v in news.items()})

    print("4/5 Fazendo previsões...")
    prev = []
    for _, r in rk.iterrows():
        try:
            prev.append({"ticker": r["ticker"], **previsao.prever(r.to_dict(), base[r["ticker"]]["precos"])})
        except Exception as e:  # noqa: BLE001
            print(f"  [aviso] previsão de {r['ticker']}: {e}")
    rk = rk.merge(pd.DataFrame(prev), on="ticker", how="left")

    print("5/5 Juros (Banco Central), teste no passado, meta e alertas...")
    mac = macro.indicadores()
    ibov = demo.gerar("BOVA11")["precos"] if usar_demo else (dados.coletar("BOVA11", forcar=forcar) or {}).get("precos")
    cdi, cdi_real = macro.cdi_mensal(date(hoje.year - 6, 1, 1))
    try:
        bt = backtest.rodar(base, anos=5, aporte=valor_aporte or 1000.0, cdi=cdi, ibov=ibov)
        bt["cdi_real"] = cdi_real
    except Exception as e:  # noqa: BLE001
        print(f"  [aviso] teste no passado falhou: {e}")
        bt = None
    pl = plano.ler()
    if valor_aporte:
        pl["aporte_mensal"] = valor_aporte
    esc = aporte.escolher(rk, 10, 2)
    cart_esp = meta.carteira_esperada(esc)
    pat = plano.patrimonio_atual(pl, cart, rk)
    inflacao = mac["ipca_12m"] if pl["corrigir_inflacao"] else 0.0
    sim = meta.simular(pl["meta"], pat, pl["aporte_mensal"], cart_esp["retorno"], cart_esp["volatilidade"],
                       pl["aumento_aporte_aa"], inflacao)

    alts = alertas.gerar(rk, anterior(hoje), news, carteira=cart["ticker"].tolist())
    compras, sobra = aporte.sugerir(rk, valor_aporte, cart) if valor_aporte > 0 else (pd.DataFrame(), 0.0)
    texto = alertas.texto_resumo(rk, alts, compras, sobra=sobra)
    datas = rk["data_cotacao"].dropna()
    cab = [f"Cotações de {pd.Timestamp(datas.max()):%d/%m/%Y} (Yahoo Finance)." if len(datas) else "",
           f"Selic {_tx(mac['selic'])} · IPCA 12m {_tx(mac['ipca_12m'])} · renda fixa líquida ≈ {_tx(mac['cdi_liquido'])} a.a."
           + (" (estimado, Banco Central fora do ar)" if mac["estimado"] else " (Banco Central)"),
           f"🎯 Meta {alertas._fmt_r(pl['meta'])}: patrimônio hoje {alertas._fmt_r(pat)}, aportando {alertas._fmt_r(pl['aporte_mensal'])}/mês "
           f"→ metade das simulações chega em {meta.fmt_tempo(sim['meses_50'])}; 9 em 10 chegam em até {meta.fmt_tempo(sim['meses_90'])}."]
    texto = "\n".join(c for c in cab if c) + "\n\n" + texto
    if sem_dados:
        texto += f"\n\nSem dados hoje (código pode ter mudado na B3): {', '.join(sem_dados)}"
    if usar_demo:
        texto = "⚠️ MODO DEMONSTRAÇÃO — DADOS FICTÍCIOS\n\n" + texto

    rk.drop(columns=["meses_pagamento", "proximos_meses"], errors="ignore").to_csv(HIST / f"ranking_{hoje:%Y-%m-%d}.csv", index=False)
    (REL / f"relatorio_{hoje:%Y-%m-%d}.txt").write_text(texto, encoding="utf-8")
    resultado = {"data": hoje, "demo": usar_demo, "ranking": rk, "noticias": news, "alertas": alts,
                 "compras": compras, "sobra": sobra, "aporte": valor_aporte, "sem_dados": sem_dados,
                 "precos": {t: d["precos"] for t, d in base.items()},
                 "proventos": {t: d["proventos"] for t, d in base.items()},
                 "info": {t: d["info"] for t, d in base.items()},
                 "macro": mac, "backtest": bt, "carteira_esperada": cart_esp, "ibov": ibov}
    with open(ULTIMO, "wb") as f:
        pickle.dump(resultado, f)

    print("\n" + texto + "\n")
    if enviar:
        alertas.carregar_config()
        assunto = f"Radar de Ações {hoje:%d/%m}: {sum(a['nivel'] == 1 for a in alts)} alertas importantes"
        if alertas.enviar_telegram(texto):
            print("Enviado no Telegram.")
        if alertas.enviar_email(assunto, texto):
            print("Enviado por e-mail.")
    print(AVISO)
    return resultado


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--aporte", type=float, default=float(os.getenv("APORTE_MENSAL", "0") or 0),
                    help="valor do aporte do mês em R$ (ou variável APORTE_MENSAL)")
    ap.add_argument("--tickers", nargs="*", help="códigos (padrão: lista do universo.py ou dados_acoes/minha_lista.txt)")
    ap.add_argument("--demo", action="store_true", help="usa dados fictícios (teste sem internet)")
    ap.add_argument("--sem-noticias", action="store_true")
    ap.add_argument("--sem-envio", action="store_true", help="não envia Telegram/e-mail")
    ap.add_argument("--forcar", action="store_true", help="ignora o cache do dia e baixa de novo")
    a = ap.parse_args()
    alertas.carregar_config()
    if not a.aporte:
        a.aporte = float(os.getenv("APORTE_MENSAL", "0") or 0)
    apurar([t.upper() for t in a.tickers] if a.tickers else universo.tickers(), a.aporte, a.demo,
           not a.sem_noticias, not a.sem_envio, a.forcar)


if __name__ == "__main__":
    main()
