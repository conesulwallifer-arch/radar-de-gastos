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

from acoes import AVISO, DADOS, alertas, analise, aporte, atlas, backtest, escritorio, dados, demo, aurum, macro, memoria, mesa, meta, noticias, plano, previsao, previsor, universo  # noqa: E402

HIST = DADOS / "historico"
REL = DADOS / "relatorios"
ULTIMO = DADOS / "ultimo.pkl"


_print_original = print


def print(*args, **kwargs):  # noqa: A001 — mensagens de acompanhamento nunca podem derrubar a apuração
    try:
        _print_original(*args, **kwargs)
    except UnicodeEncodeError:
        _print_original(*(str(a).encode("ascii", "replace").decode() for a in args), **kwargs)
    except (OSError, ValueError):
        pass


def _tx(x: float) -> str:
    return f"{x * 100:.2f}%".replace(".", ",")


def anterior(hoje: date) -> pd.DataFrame | None:
    arqs = sorted(p for p in HIST.glob("ranking_*.csv") if p.stem < f"ranking_{hoje:%Y-%m-%d}")
    return pd.read_csv(arqs[-1]) if arqs else None


def apurar(tickers: list[str], valor_aporte: float = 0.0, usar_demo: bool = False, com_noticias: bool = True,
           enviar: bool = True, forcar: bool = False, usar_ia: bool = True, progresso=None) -> dict:
    falar = progresso or (lambda m: None)
    escritorio.SILENCIOSO = usar_demo
    escritorio.status("aurum", "trabalhando", "coordenando a apuração do dia")
    hoje = date.today()
    HIST.mkdir(parents=True, exist_ok=True)
    REL.mkdir(parents=True, exist_ok=True)
    cart = aporte.ler_carteira()
    tickers = list(dict.fromkeys(tickers + cart["ticker"].tolist()))

    print(f"1/5 Coletando preços, proventos e indicadores de {len(tickers)} ações...")
    falar(f"📡 Coletando cotações, proventos e balanços de {len(tickers)} empresas...")
    base = {t: demo.gerar(t) for t in tickers} if usar_demo else dados.coletar_varios(tickers, forcar=forcar)
    sem_dados = [t for t in tickers if t not in base]
    if not usar_demo:
        atlas.limpar_descobertas(sem_dados)  # propostas do Atlas sem dados no Yahoo saem da lista
    if not base:
        raise SystemExit("Nenhum dado coletado. Verifique a internet (ou rode com --demo).")

    print("2/5 Calculando indicadores e notas...")
    selic_hoje = macro.indicadores()["selic"]  # usado no preço justo por dividendos descontados
    rk = analise.ranking(base, selic=selic_hoje)

    print("3/5 Buscando notícias...")
    falar("📰 Buscando as notícias das 30 primeiras e da sua carteira...")
    news: dict[str, list[dict]] = {}
    if com_noticias:
        alvo = list(dict.fromkeys(rk.head(30)["ticker"].tolist() + cart["ticker"].tolist()))
        for t in alvo:
            if t in base:
                nome = base[t]["info"].get("shortName") or base[t]["info"].get("longName")
                news[t] = demo.noticias(t) if usar_demo else noticias.buscar(t, nome, dias=30)
        rk = analise.ranking(base, {t: noticias.resumo(v)["saldo"] for t, v in news.items()}, selic=selic_hoje)

    print("4/5 Fazendo previsões...")
    falar("📊 Calculando previsões de proventos e de preço (1, 3 e 5 anos)...")
    prev = []
    for _, r in rk.iterrows():
        try:
            prev.append({"ticker": r["ticker"], **previsao.prever(r.to_dict(), base[r["ticker"]]["precos"])})
        except Exception as e:  # noqa: BLE001
            print(f"  [aviso] previsão de {r['ticker']}: {e}")
    rk = rk.merge(pd.DataFrame(prev), on="ticker", how="left")

    print("5/5 Juros (Banco Central), teste no passado, meta e alertas...")
    falar("🏦 Consultando Selic e inflação no Banco Central e refazendo o teste dos últimos 5 anos...")
    mac = macro.indicadores()
    mac["focus"] = macro.expectativas()
    mac["leitura_juros"] = macro.leitura_juros(mac["selic"], mac["focus"])
    if mac["leitura_juros"]:
        escritorio.registrar("risco", "leu o Boletim Focus: " + mac["leitura_juros"].split(". ")[0])
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

    print("🔮 Previsor: chance de alta/queda no próximo mês + teste de acerto no passado...")
    falar("🔮 **Íris** está calculando a chance de alta/queda no próximo mês e conferindo o próprio placar de acertos...")
    precos_base = {t: d["precos"] for t, d in base.items()}
    prev_cp = previsor.prever_todas(precos_base)
    validacao = previsor.validar_historico(precos_base)
    validacao.pop("casos", None)
    prev_cal, fator = previsor.calibrar(prev_cp, validacao)
    if len(prev_cp):
        if not usar_demo:  # dados fictícios nunca entram no placar real
            previsor.registrar(prev_cp.assign(direcao=prev_cp["prob_alta"].map(previsor.direcao)),
                               dict(zip(rk["ticker"], rk["preco"])), hoje)
        rk = rk.merge(prev_cal[["ticker", "prob_alta", "prob_bruta", "direcao", "ret_mediano", "ret_p10", "ret_p90"]]
                      .rename(columns={"prob_alta": "prob_alta_1m", "prob_bruta": "prob_alta_1m_bruta", "direcao": "direcao_1m",
                                       "ret_mediano": "ret_mediano_1m", "ret_p10": "ret_p10_1m", "ret_p90": "ret_p90_1m"}),
                      on="ticker", how="left")
    placar = previsor.placar_real(precos_base)

    print("🧠 Mesa de analistas: 7 agentes analisando cada ação...")
    falar("🧠 Cada agente está consultando a própria memória (votos passados × o que aconteceu de verdade)...")
    proventos_base = {t: d["proventos"] for t, d in base.items()}
    cerebro = memoria.avaliar(precos_base, proventos_base)
    aprendizado = memoria.fatores(cerebro)
    falar("🧠 Reunião da mesa de analistas começou.")
    reuniao = mesa.reuniao(rk, precos_base, news, mac, prev_cal, fator, cart, str(hoje), usar_ia=usar_ia,
                           progresso=falar, aprendizado=aprendizado, cerebro=cerebro)
    reuniao["cerebro"] = cerebro
    if not usar_demo:  # dados fictícios nunca entram na memória dos agentes
        # a decisão da EQUIPE também vai para a memória: é assim que se mede se o time está acertando
        nota_eq = {"Compra forte": 2, "Compra": 1, "Neutro": 0, "Evitar": -1, "Vetado": -2}
        cons_eq = reuniao["consenso"].set_index("ticker")["consenso"]
        votos_mem = {t: {**ops, "equipe": {"voto": nota_eq.get(cons_eq.get(t), 0)}} for t, ops in reuniao["opinioes"].items()}
        memoria.registrar(votos_mem, dict(zip(rk["ticker"], rk["preco"])), hoje)
    rk = rk.merge(reuniao["consenso"], on="ticker", how="left")
    for linha in reuniao["log"]:
        print("   " + linha)
    # dupla checagem: só fica "Comprar/Acumular" se a nota do sistema E a mesa de agentes concordarem
    rk["checagem"] = "ok"
    vetar = rk["vetado"].fillna(False) & rk["sinal"].isin(["Comprar", "Acumular"])
    rk.loc[vetar, "checagem"] = "vetada por " + rk.loc[vetar, "vetado_por"].fillna("")
    discorda = ~vetar & rk["sinal"].isin(["Comprar", "Acumular"]) & rk["consenso"].isin(["Evitar"])
    rk.loc[discorda, "checagem"] = "a mesa de agentes não confirmou"
    rebaixa = rk["sinal"].isin(["Comprar", "Acumular"]) & (rk["checagem"] != "ok")
    rk.loc[rebaixa, "sinal"] = "Aguardar"
    rk.loc[rk["sinal"].eq("Comprar") & rk["consenso"].eq("Neutro"), "sinal"] = "Acumular"
    print(f"   🪙 AURUM (dupla checagem): {int(rebaixa.sum())} ação(ões) tiradas das compras por falta de confirmação.")
    falar(f"🪙 **AURUM** fez a dupla checagem (nota do sistema × mesa): {int(rebaixa.sum())} ação(ões) saíram da lista de compras.")

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

    if not usar_demo:  # o histórico (base dos alertas de "mudou desde ontem") só guarda dados reais
        rk.drop(columns=["meses_pagamento", "proximos_meses"], errors="ignore").to_csv(HIST / f"ranking_{hoje:%Y-%m-%d}.csv", index=False)
    resultado = {"data": hoje, "demo": usar_demo, "ranking": rk, "noticias": news, "alertas": alts,
                 "compras": compras, "sobra": sobra, "aporte": valor_aporte, "sem_dados": sem_dados,
                 "precos": {t: d["precos"] for t, d in base.items()},
                 "proventos": {t: d["proventos"] for t, d in base.items()},
                 "info": {t: d["info"] for t, d in base.items()},
                 "macro": mac, "backtest": bt, "carteira_esperada": cart_esp, "ibov": ibov,
                 "mesa": reuniao, "previsor": {"validacao": validacao, "fator": fator, "placar_real": placar}}
    print("🪙 AURUM escrevendo o relatório do dia" + (" (IA + pesquisa na web)..." if usar_ia and aurum.ia_disponivel() else "..."))
    falar("🧭 **Atlas** (explorador autônomo) está decidindo por conta própria o que investigar...")
    resumo_atlas = mesa.resumo_texto(reuniao) + "\n" + "\n".join(
        f"{int(r['posicao'])}. {r['ticker']} nota {r['nota']:.0f} sinal {r['sinal']} consenso {r.get('consenso')}"
        for _, r in rk.head(15).iterrows())
    resultado["atlas"] = atlas.explorar(resultado, anterior(hoje), resumo_atlas, usar_ia=usar_ia)
    for passo in resultado["atlas"]["diario"]:
        falar("   🧭 Atlas " + passo)
    resultado["alertas"] = sorted(alts + resultado["atlas"]["alertas"], key=lambda a: (a["nivel"], a["ticker"]))
    falar("🪙 **AURUM** está escrevendo o relatório do dia...")
    escritorio.status("aurum", "trabalhando", "escrevendo o relatório do dia")
    resultado["aurum"] = aurum.relatorio(resultado, pl, usar_ia=usar_ia)
    escritorio.registrar("aurum", f"apuração concluída: {len(rk)} empresas, {sum(a['nivel'] == 1 for a in resultado['alertas'])} "
                                  f"alertas importantes; {mesa.resumo_texto(reuniao)}")
    escritorio.status("aurum", "pausa", "relatório do dia entregue")
    texto = "🪙 AURUM\n\n" + resultado["aurum"]["texto"].replace("**", "") + "\n\n" + "─" * 20 + "\n\n" + texto
    texto = texto.replace("─" * 20, "🧭 Atlas, o explorador:\n" + resultado["atlas"]["relatorio"].replace("**", "") + "\n\n" + "─" * 20, 1)
    (REL / f"relatorio_{hoje:%Y-%m-%d}.txt").write_text(texto, encoding="utf-8")
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
    ap.add_argument("--sem-ia", action="store_true", help="AURUM só por regras, mesmo com chave da IA")
    a = ap.parse_args()
    alertas.carregar_config()
    if not a.aporte:
        a.aporte = float(os.getenv("APORTE_MENSAL", "0") or 0)
    apurar([t.upper() for t in a.tickers] if a.tickers else universo.tickers(), a.aporte, a.demo,
           not a.sem_noticias, not a.sem_envio, a.forcar, not a.sem_ia)


if __name__ == "__main__":
    main()
