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

from acoes import AVISO, DADOS, destravar, gravar_atomico, hoje_brt, travar, alertas, analise, aporte, atlas, backtest, escritorio, dados, demo, aurum, geopolitica, macro, memoria, mesa, meta, noticias, oraculos, plano, previsao, previsor, trading, universo  # noqa: E402

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


FALHAS: list[str] = []  # etapas que falharam nesta apuração (aparecem no relatório; nada derruba a apuração inteira)


def _seguro(nome: str, fn, padrao):
    """Roda uma etapa; se falhar, registra, avisa e segue com um resultado neutro."""
    try:
        return fn()
    except Exception as e:  # noqa: BLE001
        msg = f"{nome}: {type(e).__name__}: {str(e)[:160]}"
        print(f"  [aviso] etapa com problema — {msg}")
        FALHAS.append(msg)
        try:
            escritorio.registrar("aurum", f"uma etapa falhou e foi contornada ({nome}); o resto da apuração seguiu")
        except Exception:  # noqa: BLE001
            pass
        return padrao


def _br(x: float) -> str:
    return f"R$ {x:.2f}"


def _tx(x: float) -> str:
    return f"{x * 100:.2f}%".replace(".", ",")


def anterior(hoje: date) -> pd.DataFrame | None:
    arqs = sorted(p for p in HIST.glob("ranking_*.csv") if p.stem < f"ranking_{hoje:%Y-%m-%d}")
    return pd.read_csv(arqs[-1]) if arqs else None


TRAVA_APURACAO = DADOS / "apuracao.lock"


class ApuracaoEmAndamento(RuntimeError):
    pass


def apurar(*args, **kw) -> dict:
    """Uma apuração por vez no computador inteiro (painel, Equipe 24h e .bat agendado não se atropelam)."""
    trava = travar(TRAVA_APURACAO)
    if trava is None:
        raise ApuracaoEmAndamento("Já tem uma apuração em andamento (Equipe 24h ou outra janela). Aguarde terminar e tente de novo.")
    try:
        return _apurar(*args, **kw)
    finally:
        destravar(trava)


def _apurar(tickers: list[str], valor_aporte: float = 0.0, usar_demo: bool = False, com_noticias: bool = True,
            enviar: bool = True, forcar: bool = False, usar_ia: bool = True, progresso=None) -> dict:
    falar = progresso or (lambda m: None)
    FALHAS.clear()
    enviar = enviar and not usar_demo  # dados fictícios nunca saem no Telegram/e-mail
    escritorio.SILENCIOSO = usar_demo
    escritorio.status("aurum", "trabalhando", "coordenando a apuração do dia")
    hoje = hoje_brt()
    HIST.mkdir(parents=True, exist_ok=True)
    REL.mkdir(parents=True, exist_ok=True)
    cart = aporte.ler_carteira()
    ops_abertas = trading.ler_operacoes()
    ops_abertas = ops_abertas[ops_abertas["status"].str.lower() == "aberta"]["ticker"].tolist()
    tickers = list(dict.fromkeys(tickers + cart["ticker"].tolist() + ops_abertas))  # suas operações de trading também

    print(f"1/5 Coletando preços, proventos e indicadores de {len(tickers)} ações...")
    falar(f"📡 Coletando cotações, proventos e balanços de {len(tickers)} empresas...")
    base = {t: demo.gerar(t) for t in tickers} if usar_demo else dados.coletar_varios(tickers, forcar=forcar)
    sem_dados = [t for t in tickers if t not in base]
    if not usar_demo:
        atlas.limpar_descobertas(sem_dados)  # propostas do Atlas sem dados por vários dias seguidos saem da lista
    if not base:
        raise RuntimeError("Nenhum dado coletado. Verifique a internet (ou rode com --demo).")

    print("2/5 Calculando indicadores e notas...")
    selic_hoje = _seguro("Selic", lambda: macro.indicadores()["selic"], 0.15)  # usado no preço justo por dividendos descontados
    rk = analise.ranking(base, selic=selic_hoje)
    if rk.empty:
        raise RuntimeError("Nenhuma ação com dados suficientes para analisar. Verifique a internet e tente de novo.")

    print("3/5 Buscando notícias...")
    falar("📰 Buscando as notícias das 30 primeiras e da sua carteira...")
    news: dict[str, list[dict]] = {}
    if com_noticias:
        alvo = list(dict.fromkeys(rk.head(30)["ticker"].tolist() + cart["ticker"].tolist()))
        for t in alvo:
            if t in base:
                nome = base[t]["info"].get("shortName") or base[t]["info"].get("longName")
                news[t] = demo.noticias(t) if usar_demo else _seguro(f"notícias de {t}", lambda: noticias.buscar(t, nome, dias=30), [])
        rk2 = _seguro("ranking com notícias", lambda: analise.ranking(base, {t: noticias.resumo(v)["saldo"] for t, v in news.items()},
                                                                     selic=selic_hoje), None)
        rk = rk2 if rk2 is not None and len(rk2) else rk

    print("4/5 Fazendo previsões...")
    falar("📊 Calculando previsões de proventos e de preço (1, 3 e 5 anos)...")
    prev = []
    for _, r in rk.iterrows():
        try:
            prev.append({"ticker": r["ticker"], **previsao.prever(r.to_dict(), base[r["ticker"]]["precos"])})
        except Exception as e:  # noqa: BLE001
            print(f"  [aviso] previsão de {r['ticker']}: {e}")
    if prev:
        rk = rk.merge(pd.DataFrame(prev), on="ticker", how="left")

    print("5/5 Juros (Banco Central), teste no passado, meta e alertas...")
    falar("🏦 Consultando Selic e inflação no Banco Central e refazendo o teste dos últimos 5 anos...")
    mac = _seguro("Banco Central", macro.indicadores, {"selic": 0.15, "ipca_12m": 0.045, "cdi_liquido": 0.12, "estimado": True,
                                                       "data_selic": None, "data_ipca": None})
    mac["focus"] = _seguro("Boletim Focus", macro.expectativas, {})
    mac["leitura_juros"] = _seguro("leitura dos juros", lambda: macro.leitura_juros(mac["selic"], mac["focus"]), None)
    if mac["leitura_juros"]:
        escritorio.registrar("risco", "leu o Boletim Focus: " + mac["leitura_juros"].split(". ")[0])
    ibov = demo.gerar("BOVA11")["precos"] if usar_demo else _seguro("Ibovespa", lambda: (dados.coletar("BOVA11", forcar=forcar) or {}).get("precos"), None)
    cdi, cdi_real = _seguro("CDI", lambda: macro.cdi_mensal(date(hoje.year - 6, 1, 1)), (None, False))
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
    prev_cp = _seguro("Íris (previsões)", lambda: previsor.prever_todas(precos_base), pd.DataFrame())
    validacao = _seguro("Íris (teste)", lambda: previsor.validar_historico(precos_base), {"n": 0})
    validacao.pop("casos", None)
    prev_cal, fator = _seguro("Íris (calibragem)", lambda: previsor.calibrar(prev_cp, validacao), (pd.DataFrame(), 0.0))
    if len(prev_cp) and len(prev_cal):
        if not usar_demo:  # dados fictícios nunca entram no placar real
            previsor.registrar(prev_cp.assign(direcao=prev_cp["prob_alta"].map(previsor.direcao)),
                               dict(zip(rk["ticker"], rk["preco"])), hoje)
        rk = rk.merge(prev_cal[["ticker", "prob_alta", "prob_bruta", "direcao", "ret_mediano", "ret_p10", "ret_p90"]]
                      .rename(columns={"prob_alta": "prob_alta_1m", "prob_bruta": "prob_alta_1m_bruta", "direcao": "direcao_1m",
                                       "ret_mediano": "ret_mediano_1m", "ret_p10": "ret_p10_1m", "ret_p90": "ret_p90_1m"}),
                      on="ticker", how="left")
    placar = _seguro("Íris (placar)", lambda: previsor.placar_real(precos_base), {})
    proventos_base = {t: d["proventos"] for t, d in base.items()}

    print("🔭 Equipe de previsibilidade: Otto (proventos), Bento (entrada) e Sofia (modelo conjunto)...")
    falar("💵 **Otto** está prevendo os proventos dos próximos 12 meses e a chance de corte — e conferindo o próprio placar...")
    falar("🎯 **Bento** está calculando o preço certo para a ordem de compra de cada ação...")
    falar("🧮 **Sofia** está treinando e testando o modelo conjunto (sem olhar o futuro)...")
    escritorio.status(["proventos", "entrada", "conjunto"], "trabalhando", "prevendo e testando no passado")
    try:
        orac = oraculos.rodar(rk, precos_base, proventos_base, hoje)
    except Exception as e:  # noqa: BLE001 — previsão extra nunca derruba a apuração
        print(f"  [aviso] equipe de previsibilidade: {e}")
        orac = {"tabela": pd.DataFrame(), "placar": {}}
    if len(orac["tabela"]):
        rk = rk.merge(orac["tabela"], on="ticker", how="left")
    po, pb, ps = (orac["placar"].get(k, {}) for k in ("otto", "bento", "sofia"))
    fator_sofia = float(ps.get("fator", 0.0) or 0.0)
    if po.get("n"):
        escritorio.registrar("proventos", f"previu os proventos de {len(orac['tabela'])} ações; no teste de {po['n']} anos-ação, "
                             f"errou por menos de 25% em {po['acerto'] * 100:.0f}% das vezes".replace(".", ","))
    if pb.get("n"):
        escritorio.registrar("entrada", f"calculou os preços de entrada; no teste, a ordem de '80%' executou em {pb['real_80'] * 100:.0f}% "
                             f"e a de '50%' em {pb['real_50'] * 100:.0f}% das vezes")
    if ps.get("n"):
        escritorio.registrar("conjunto", (f"testou o modelo em {ps['meses']} meses: acerto {ps['acerto'] * 100:.1f}% (chute = 50%) — "
                                          + ("vai votar" if fator_sofia > 0 else "não bateu o chute, não vota")).replace(".", ","))
    escritorio.status(["proventos", "entrada", "conjunto"], "pausa", "previsões do dia entregues")

    print("🌎 Helena: governo, juros, câmbio, commodities e exterior...")
    falar("🌎 **Helena** está lendo o noticiário de governo, Copom, EUA, China e impostos, e medindo como cada ação reage a dólar, petróleo e minério...")
    escritorio.status("macro", "trabalhando", "lendo o cenário político e econômico")
    try:
        if usar_demo:
            fat = {"ibov": demo.gerar("BOVA11")["precos"], "dolar": demo.gerar("FX_DOLAR")["precos"],
                   "petroleo": demo.gerar("FX_BRENT")["precos"], "minerio": demo.gerar("FX_MINERIO")["precos"]}
            temas = {t: [{"titulo": f"[DEMO] Manchete fictícia sobre {t.lower()}", "fonte": "Notícia fictícia", "quando": None,
                          "link": "", **noticias.classificar(f"manchete sobre {t}")}] for t in geopolitica.TEMAS}
        else:
            fat = geopolitica.baixar_fatores(forcar=forcar)
            temas = geopolitica.noticias_temas()
        cen = geopolitica.rodar(rk, precos_base, fat, temas, mac, usar_ia=usar_ia and not usar_demo)
    except Exception as e:  # noqa: BLE001 — o cenário nunca derruba a apuração
        print(f"  [aviso] Helena (cenário): {e}")
        cen = {"tabela": pd.DataFrame(), "setores": pd.DataFrame(), "movimentos": {}, "validacao": {"n": 0}, "fator": 0.0,
               "clima": pd.DataFrame(), "temas": {}, "leitura_ia": None}
    if len(cen["tabela"]):
        rk = rk.merge(cen["tabela"][["ticker", "vento", "motor"]].rename(columns={"vento": "vento_macro", "motor": "motor_macro"}),
                      on="ticker", how="left")
    vm = cen["validacao"]
    escritorio.registrar("macro", f"leu {sum(len(v) for v in cen['temas'].values())} manchetes de {len(cen['temas'])} temas e mediu a sensibilidade "
                         f"de {len(cen['tabela'])} ações a dólar, petróleo, minério e juros dos EUA"
                         + (f"; no teste de {vm['meses']} meses, o vento macro {'provou' if cen['fator'] > 0 else 'não provou'} vantagem" if vm.get("n") else ""))
    escritorio.status("macro", "pausa", "cenário do dia entregue")

    print("🧠 Mesa de analistas: 11 agentes analisando cada ação...")
    falar("🧠 Cada agente está consultando a própria memória (votos passados × o que aconteceu de verdade)...")
    cerebro = _seguro("memória dos agentes", lambda: memoria.avaliar(precos_base, proventos_base),
                      {"por_agente": pd.DataFrame(), "votos_guardados": 0, "desde": None, "pendentes": 0})
    aprendizado = _seguro("pesos aprendidos", lambda: memoria.fatores(cerebro), {})
    falar("🧠 Reunião da mesa de analistas começou.")
    reuniao = _seguro("mesa de analistas", lambda: mesa.reuniao(
        rk, precos_base, news, mac, prev_cal, fator, cart, str(hoje), usar_ia=usar_ia, progresso=falar, aprendizado=aprendizado,
        cerebro=cerebro, oraculos=orac["tabela"], fator_sofia=fator_sofia, cenario=cen["tabela"], fator_macro=cen["fator"]), None)
    if reuniao is None:  # mesa falhou: ninguém vota, ninguém veta, e o relatório avisa
        reuniao = {"consenso": pd.DataFrame({"ticker": rk["ticker"], "placar": 0.0, "consenso": "Neutro", "a_favor": 0, "contra": 0,
                                             "vetado": False, "vetado_por": ""}),
                   "opinioes": {}, "log": ["⚠️ A mesa de analistas não conseguiu se reunir hoje (veja o aviso)."], "ia": False,
                   "fator_previsor": fator, "verificacoes": [], "aprendizado": {}, "hora": ""}
    reuniao["cerebro"] = cerebro
    if not usar_demo:  # dados fictícios nunca entram na memória dos agentes
        # a decisão da EQUIPE também vai para a memória: é assim que se mede se o time está acertando
        nota_eq = {"Compra forte": 2, "Compra": 1, "Neutro": 0, "Evitar": -1, "Vetado": -2}
        cons_eq = reuniao["consenso"].set_index("ticker")["consenso"]
        votos_mem = {t: {**ops, "equipe": {"voto": nota_eq.get(cons_eq.get(t), 0)}} for t, ops in reuniao["opinioes"].items()}
        if votos_mem:
            _seguro("memória (gravar votos)", lambda: memoria.registrar(votos_mem, dict(zip(rk["ticker"], rk["preco"])), hoje), None)
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

    print("⚡ Mesa de trading: testando os padrões no histórico e procurando sinais de hoje...")
    falar("⚡ **Leo** (trader de médio prazo) está testando 5 padrões em todas as ações e procurando sinais de hoje...")
    escritorio.status("trading", "trabalhando", "testando padrões e procurando sinais")
    try:
        bt_tr = trading.backtest(precos_base, proventos_base)
        sinais_tr = trading.sinais_hoje(bt_tr, rk)
        if not usar_demo:  # dados fictícios nunca entram no placar real
            trading.registrar(sinais_tr[sinais_tr["status"] == "✅ Aprovado"] if len(sinais_tr) else sinais_tr, hoje)
        tr = {**trading.resumir(bt_tr), "sinais": sinais_tr, "placar_real": trading.placar_real(precos_base)}
        aprov = bt_tr["padroes"][bt_tr["padroes"]["status"] == "✅ Aprovado"]["nome"].tolist() if len(bt_tr["padroes"]) else []
        n_ap = int((sinais_tr["status"] == "✅ Aprovado").sum()) if len(sinais_tr) else 0
        escritorio.registrar("trading", f"testou 5 padrões em {len(bt_tr['ind'])} ações ({len(bt_tr['operacoes'])} operações simuladas): "
                             f"{len(aprov)} aprovado(s); hoje {n_ap} sinal(is) de padrão aprovado")
        falar(f"   ✓ ⚡ Leo: {len(aprov)} padrão(ões) aprovado(s) no teste; {n_ap} sinal(is) hoje.")
    except Exception as e:  # noqa: BLE001 — o trading nunca derruba a apuração
        print(f"  [aviso] mesa de trading: {e}")
        tr = {"padroes": pd.DataFrame(), "chute": {}, "sinais": pd.DataFrame(), "placar_real": {"n": 0}, "n_operacoes": 0}
    escritorio.status("trading", "pausa", "sinais do dia entregues")

    alts = _seguro("alertas", lambda: alertas.gerar(rk, anterior(hoje), news, carteira=cart["ticker"].tolist()), [])
    compras, sobra = (_seguro("sugestão de compras", lambda: aporte.sugerir(rk, valor_aporte, cart), (pd.DataFrame(), 0.0))
                      if valor_aporte > 0 else (pd.DataFrame(), 0.0))
    texto = _seguro("resumo", lambda: alertas.texto_resumo(rk, alts, compras, sobra=sobra), "Resumo indisponível hoje (veja o painel).")
    datas = rk["data_cotacao"].dropna()
    cab = [f"Cotações de {pd.Timestamp(datas.max()):%d/%m/%Y} (Yahoo Finance)." if len(datas) else "",
           f"Selic {_tx(mac['selic'])} · IPCA 12m {_tx(mac['ipca_12m'])} · renda fixa líquida ≈ {_tx(mac['cdi_liquido'])} a.a."
           + (" (estimado, Banco Central fora do ar)" if mac["estimado"] else " (Banco Central)"),
           f"🎯 Meta {alertas._fmt_r(pl['meta'])}: patrimônio hoje {alertas._fmt_r(pat)}, aportando {alertas._fmt_r(pl['aporte_mensal'])}/mês "
           f"→ metade das simulações chega em {meta.fmt_tempo(sim['meses_50'])}; 9 em 10 chegam em até {meta.fmt_tempo(sim['meses_90'])}."]
    texto = "\n".join(c for c in cab if c) + "\n\n" + texto
    s_ap = tr["sinais"][tr["sinais"]["status"] == "✅ Aprovado"] if len(tr["sinais"]) else pd.DataFrame()
    if len(s_ap):
        texto += "\n\n⚡ Trading (médio prazo) — sinais de padrões aprovados no teste:\n" + "\n".join(
            f"• {r['ticker']}: {r['padrao_nome']} — entrada ~{_br(r['preco'])}, stop {_br(r['stop'])}, alvo {_br(r['alvo'])} "
            f"(acerto do padrão {r['acerto_padrao'] * 100:.0f}%)".replace(".", ",") for _, r in s_ap.head(5).iterrows())
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
                 "mesa": reuniao, "previsor": {"validacao": validacao, "fator": fator, "placar_real": placar},
                 "oraculos": orac["placar"], "trading": tr, "cenario": cen}
    print("🪙 AURUM escrevendo o relatório do dia" + (" (IA + pesquisa na web)..." if usar_ia and aurum.ia_disponivel() else "..."))
    falar("🧭 **Atlas** (explorador autônomo) está decidindo por conta própria o que investigar...")
    resumo_atlas = mesa.resumo_texto(reuniao) + "\n" + "\n".join(
        f"{int(r['posicao'])}. {r['ticker']} nota {r['nota']:.0f} sinal {r['sinal']} consenso {r.get('consenso')}"
        for _, r in rk.head(15).iterrows())
    resultado["atlas"] = _seguro("Atlas", lambda: atlas.explorar(resultado, anterior(hoje), resumo_atlas, usar_ia=usar_ia),
                                 {"diario": [], "alertas": [], "relatorio": "O Atlas não conseguiu explorar hoje."})
    for passo in resultado["atlas"]["diario"]:
        falar("   🧭 Atlas " + passo)
    resultado["alertas"] = sorted(alts + resultado["atlas"]["alertas"], key=lambda a: (a["nivel"], a["ticker"]))
    falar("🪙 **AURUM** está escrevendo o relatório do dia...")
    escritorio.status("aurum", "trabalhando", "escrevendo o relatório do dia")
    resultado["aurum"] = _seguro("relatório do AURUM", lambda: aurum.relatorio(resultado, pl, usar_ia=usar_ia),
                                 {"texto": "O AURUM não conseguiu escrever o relatório completo hoje; os números estão no painel.",
                                  "fonte": "regras", "hora": ""})
    escritorio.registrar("aurum", f"apuração concluída: {len(rk)} empresas, {sum(a['nivel'] == 1 for a in resultado['alertas'])} "
                                  f"alertas importantes; {mesa.resumo_texto(reuniao)}")
    escritorio.status("aurum", "pausa", "relatório do dia entregue")
    texto = "🪙 AURUM\n\n" + resultado["aurum"]["texto"].replace("**", "") + "\n\n" + "─" * 20 + "\n\n" + texto
    texto = texto.replace("─" * 20, "🧭 Atlas, o explorador:\n" + resultado["atlas"]["relatorio"].replace("**", "") + "\n\n" + "─" * 20, 1)
    if FALHAS:
        texto += "\n\n⚠️ Etapas com problema hoje (o resto foi feito normalmente): " + "; ".join(FALHAS[:6])
    resultado["falhas"] = list(FALHAS)
    resultado["hora"] = pd.Timestamp.now(tz="America/Sao_Paulo").strftime("%Y-%m-%d %H:%M")
    if not usar_demo:  # o relatório do dia só guarda dados reais
        (REL / f"relatorio_{hoje:%Y-%m-%d}.txt").write_text(texto, encoding="utf-8")
    gravar_atomico(ULTIMO, lambda f: pickle.dump(resultado, f))  # o painel nunca lê o arquivo pela metade

    if not os.getenv("CI"):  # no GitHub Actions o log pode ser público: o relatório (com carteira e patrimônio) não vai para lá
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
