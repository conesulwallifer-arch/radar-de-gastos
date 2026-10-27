"""AURUM — o assistente do Radar de Ações.

Dois modos:
- Sem chave de IA: fala a partir de regras, usando só os dados da apuração (funciona sempre, de graça).
- Com ANTHROPIC_API_KEY: usa o Claude para escrever o relatório do dia, pesquisar notícias na web sobre as
  ações do plano e responder perguntas livres. Custa alguns centavos de dólar por relatório/pergunta.

Regra de ouro dos dois modos: só afirmar o que está nos dados (ou numa fonte citada), mostrar a data de cada
número e nunca prometer retorno.
"""
from __future__ import annotations

import json
import re
from datetime import datetime

import pandas as pd

from . import aporte, ia, mesa as mesa_mod, meta, plano as plano_mod



# ------------------------------------------------------------------ formatação
def _r(x, casas=2) -> str:
    if x is None or x != x:
        return "—"
    return f"R$ {x:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _p(x, casas=1) -> str:
    return "—" if x is None or x != x else f"{x * 100:.{casas}f}%".replace(".", ",")


def saudacao(nome: str = "", agora: datetime | None = None) -> str:
    h = (agora or datetime.now()).hour
    base = "Bom dia" if 5 <= h < 12 else "Boa tarde" if 12 <= h < 18 else "Boa noite"
    return f"{base}, {nome}" if nome else base


# ------------------------------------------------------------------ contexto do dia
def contexto(R: dict, pl: dict | None = None, cart: pd.DataFrame | None = None) -> dict:
    """Resumo da apuração em valores simples — base para o relatório, para o chat e para a IA."""
    pl = pl or plano_mod.ler()
    cart = cart if cart is not None else aporte.ler_carteira()
    rk: pd.DataFrame = R["ranking"]
    mac = R.get("macro") or {"selic": 0.14, "ipca_12m": 0.045, "cdi_liquido": 0.119, "estimado": True}
    compras, sobra = aporte.sugerir(rk, pl["aporte_mensal"], cart)
    esc = aporte.escolher(rk, 10, 2)
    ce = R.get("carteira_esperada") or meta.carteira_esperada(esc)
    pat = plano_mod.patrimonio_atual(pl, cart, rk)
    infl = mac["ipca_12m"] if pl.get("corrigir_inflacao") else 0.0
    sim = meta.simular(pl["meta"], pat, pl["aporte_mensal"], ce["retorno"], ce["volatilidade"], pl["aumento_aporte_aa"], infl)
    mais500 = meta.meses_ate(pl["meta"], pat, pl["aporte_mensal"] + 500, ce["retorno"], pl["aumento_aporte_aa"], infl)
    rf = meta.meses_ate(pl["meta"], pat, pl["aporte_mensal"], mac["cdi_liquido"], pl["aumento_aporte_aa"], infl)
    datas = rk["data_cotacao"].dropna() if "data_cotacao" in rk else pd.Series(dtype=str)

    def linha(r):
        return {k: (None if (isinstance(v, float) and v != v) else v) for k, v in {
            "ticker": r["ticker"], "empresa": r["nome"], "setor": r["setor"], "posicao": int(r["posicao"]),
            "sinal": r["sinal"], "nota": round(float(r["nota"]), 1), "confianca_dados": r.get("confianca"),
            "preco": round(float(r["preco"]), 2), "preco_teto": round(float(r["preco_teto_bazin"]), 2) if r["preco_teto_bazin"] == r["preco_teto_bazin"] else None,
            "abaixo_do_teto": round(float(r["margem_bazin"]), 3) if r["margem_bazin"] == r["margem_bazin"] else None,
            "proventos_ano_medio_5a_pct": round(float(r["dy_medio_5a"]), 3) if r["dy_medio_5a"] == r["dy_medio_5a"] else None,
            "proventos_previstos_12m_rs": round(float(r.get("proventos_previstos_12m") or 0), 2),
            "retorno_total_esperado": round(float(r.get("retorno_total_esperado_aa") or 0), 3),
            "anos_pagando_de_10": int(r["anos_pagou_10"]), "roe": round(float(r["roe"]), 3) if r["roe"] == r["roe"] else None,
            "meses_que_paga": r.get("meses_provaveis"), "por_que": r.get("por_que"), "avisos": r.get("avisos_dados") or None,
            "consenso_mesa": r.get("consenso"), "chance_alta_1m": r.get("prob_alta_1m"),
            "otto_proventos_12m_faixa": [_arred(r.get("otto_prov_p10")), _arred(r.get("otto_prov_12m")), _arred(r.get("otto_prov_p90"))],
            "otto_chance_corte": _arred(r.get("otto_prob_corte"), 3), "otto_acerto_historico": _arred(r.get("otto_acerto"), 3),
            "bento_ordem_80pct": _arred(r.get("bento_preco_80")), "bento_ordem_50pct": _arred(r.get("bento_preco_50")),
            "sofia_chance_superar_3m": _arred(r.get("sofia_prob"), 3),
        }.items()}

    imp = [a for a in R.get("alertas", []) if a["nivel"] == 1]
    bt = R.get("backtest") or {}
    return {
        "data_apuracao": str(R["data"]), "cotacoes_ate": str(datas.max()) if len(datas) else None, "demo": bool(R.get("demo")),
        "nome": pl.get("nome", ""), "n_empresas": len(rk),
        "macro": {"selic": mac["selic"], "ipca_12m": mac["ipca_12m"], "renda_fixa_liquida": mac["cdi_liquido"],
                  "estimado": bool(mac.get("estimado")), "expectativas_focus": mac.get("focus") or None,
                  "leitura_juros": mac.get("leitura_juros")},
        "proximos_balancos": sorted([(r["ticker"], r["proximo_balanco"]) for _, r in rk.head(20).iterrows()
                                     if isinstance(r.get("proximo_balanco"), str)], key=lambda x: x[1])[:8],
        "plano": {"meta": pl["meta"], "aporte_mensal": pl["aporte_mensal"], "aumento_aporte_aa": pl["aumento_aporte_aa"],
                  "patrimonio_hoje": pat, "meta_corrigida_inflacao": bool(pl.get("corrigir_inflacao"))},
        "projecao": {"retorno_esperado_carteira": ce["retorno"], "oscilacao_carteira": ce["volatilidade"],
                     "meses_anos_bons": sim["meses_10"], "meses_mais_provavel": sim["meses_50"], "meses_anos_ruins": sim["meses_90"],
                     "meses_com_500_a_mais": mais500, "meses_so_renda_fixa": rf},
        "compras_do_mes": [{"ticker": r["ticker"], "cotas": int(r["comprar_qtd"]), "preco": round(float(r["preco"]), 2),
                            "total": round(float(r["valor"]), 2), "renda_anual": round(float(r["renda_anual_estimada"]), 2)}
                           for _, r in compras.iterrows()],
        "sobra_do_mes": sobra,
        "top10": [linha(r) for _, r in rk.head(10).iterrows()],
        "carteira": [linha(r) for _, r in rk[rk["ticker"].isin(cart["ticker"])].iterrows()] if len(cart) else [],
        "alertas_importantes": [f"[{a['tipo']}] {a['texto']}" for a in imp[:12]],
        "dados_duvidosos": rk.loc[rk.get("confianca", pd.Series(dtype=str)) == "Baixa", "ticker"].tolist() if "confianca" in rk else [],
        "teste_no_passado": {k: bt.get(k) for k in ("meses", "investido", "sistema", "tir_sistema", "cdi", "tir_cdi", "ibovespa", "tir_ibovespa")} if bt else None,
        "mesa_de_analistas": ({"resumo": mesa_mod.resumo_texto(R["mesa"]), "atividade": R["mesa"]["log"]} if R.get("mesa") else None),
        "previsora_iris": _iris(R),
        "equipe_previsibilidade": _previsibilidade(R),
        "mesa_trading": _trading(R),
        "atlas_explorador": (R.get("atlas") or {}).get("relatorio"),
        "noticias_recentes": {t: [f"{n['titulo']} ({n['fonte']}, tom {n['tom']})" for n in v[:4]]
                              for t, v in (R.get("noticias") or {}).items() if t in {x["ticker"] for _, x in rk.head(10).iterrows()}},
    }


def _arred(x, casas: int = 2):
    return None if x is None or x != x else round(float(x), casas)


def _previsibilidade(R: dict) -> dict | None:
    """Otto, Bento e Sofia: placar no teste sem colar + previsões das ações que estamos para comprar."""
    pl = R.get("oraculos")
    rk = R["ranking"]
    if not pl or "otto_prov_12m" not in rk:
        return None
    alvo = rk[rk["sinal"].isin(["Comprar", "Acumular"])].head(6)
    return {
        "placar": {"otto": pl.get("otto"), "bento": pl.get("bento"),
                   "sofia": {k: v for k, v in (pl.get("sofia") or {}).items() if k != "pesos"}},
        "para_comprar": [{"ticker": r["ticker"], "proventos_12m": _arred(r.get("otto_prov_12m")),
                          "faixa": [_arred(r.get("otto_prov_p10")), _arred(r.get("otto_prov_p90"))],
                          "chance_corte": _arred(r.get("otto_prob_corte"), 3), "ordem_80": _arred(r.get("bento_preco_80")),
                          "ordem_50": _arred(r.get("bento_preco_50")), "sofia": _arred(r.get("sofia_prob"), 3)}
                         for _, r in alvo.iterrows()],
    }


def _trading(R: dict) -> dict | None:
    tr = R.get("trading") or {}
    pad, sin = tr.get("padroes"), tr.get("sinais")
    if pad is None or not len(pad):
        return None
    return {"padroes": [{"padrao": r["nome"], "status": r["status"], "acerto_3a": _arred(r.get("acerto_conf"), 3),
                         "ganho_medio_por_operacao": _arred(r.get("expectativa_conf"), 4), "operacoes": r.get("n_conf")}
                        for _, r in pad.iterrows()],
            "sinais_hoje": [{"ticker": r["ticker"], "padrao": r["padrao_nome"], "status": r["status"], "entrada": _arred(r["preco"]),
                             "stop": _arred(r["stop"]), "alvo": _arred(r["alvo"]), "barata": bool(r["barata"])}
                            for _, r in (sin.head(8).iterrows() if sin is not None and len(sin) else [])]}


def texto_trading(c: dict) -> str:
    m = c.get("mesa_trading")
    if not m:
        return "A Mesa de Trading ainda não rodou: faça uma apuração."
    ap = [p for p in m["padroes"] if p["status"].startswith("✅")]
    txt = (f"⚡ Leo testou 5 padrões de médio prazo: {len(ap)} aprovado(s)"
           + (f" ({', '.join(p['padrao'] for p in ap)})" if ap else " — nenhum venceu o chute com folga no teste, então não há sinal confiável") + ". ")
    sinais = [x for x in m["sinais_hoje"] if x["status"].startswith("✅")]
    if sinais:
        txt += "Sinais de hoje: " + "; ".join(f"{x['ticker']} ({x['padrao']}): entrada ~{_r(x['entrada'])}, stop {_r(x['stop'])}, alvo {_r(x['alvo'])}"
                                              for x in sinais[:4]) + ". "
    else:
        txt += "Hoje não há sinal de padrão aprovado — não operar também é uma decisão. "
    return txt + "Arrisque no máximo 1% do capital de trading por operação e respeite o stop."


def texto_previsibilidade(c: dict) -> str | None:
    e = c.get("equipe_previsibilidade")
    if not e or not e["para_comprar"]:
        return None
    po = (e["placar"] or {}).get("otto") or {}
    itens = []
    for x in e["para_comprar"][:3]:
        partes = [f"**{x['ticker']}**: Otto prevê {_r(x['proventos_12m'])}/ação em 12 meses"
                  + (f" (risco de corte {_p(x['chance_corte'], 0)})" if x["chance_corte"] is not None else "")]
        if x["ordem_80"]:
            partes.append(f"Bento sugere ordem a {_r(x['ordem_80'])} (80% de chance de executar em 1 mês)")
        itens.append(", ".join(partes))
    teste = (f" No teste sem colar, o método de proventos do Otto errou por menos de 25% em {_p(po.get('acerto'), 0)} dos casos."
             if po.get("n") else "")
    return "🔭 Previsões para o que está na lista de compras — " + "; ".join(itens) + "." + teste


def _iris(R: dict) -> dict | None:
    pv = R.get("previsor")
    rk = R["ranking"]
    if not pv or "prob_alta_1m" not in rk:
        return None
    v = pv["validacao"]
    ok = rk.dropna(subset=["prob_alta_1m"])
    return {"acerto_historico": v.get("acerto"), "acerto_do_chute": v.get("chute_alta"), "previsoes_testadas": v.get("n"),
            "vantagem_comprovada": pv["fator"] > 0, "placar_real": pv.get("placar_real"),
            "maior_chance_alta": [(r["ticker"], round(float(r["prob_alta_1m"]), 2)) for _, r in ok.nlargest(5, "prob_alta_1m").iterrows()],
            "maior_chance_queda": [(r["ticker"], round(float(r["prob_alta_1m"]), 2)) for _, r in ok.nsmallest(5, "prob_alta_1m").iterrows()]}


def texto_iris(c: dict) -> str:
    i = c.get("previsora_iris")
    if not i:
        return "A Íris ainda não tem previsões de curto prazo nesta apuração."
    teste = (f"No teste com os últimos 3 anos ({i['previsoes_testadas']} previsões), acertei {_p(i['acerto_historico'])} "
             f"das direções — quem chutasse 'sempre sobe' acertaria {_p(i['acerto_do_chute'])}.")
    if not i["vantagem_comprovada"]:
        return ("🔮 Íris: " + teste + " Como não mostrei vantagem sobre o chute, neutralizei minhas previsões de curto prazo: "
                "elas não influenciam as compras. O curto prazo da bolsa é quase aleatório; o longo prazo é que paga.")
    alta = ", ".join(f"{t} ({_p(p, 0)})" for t, p in i["maior_chance_alta"][:3])
    queda = ", ".join(f"{t} ({_p(p, 0)})" for t, p in i["maior_chance_queda"][:3])
    return (f"🔮 Íris: maior chance de ALTA no próximo mês: {alta}. Maior chance de QUEDA: {queda}. " + teste
            + " São probabilidades, não certezas.")


# ------------------------------------------------------------------ voz por regras (sem IA)
def relatorio_regras(c: dict) -> list[str]:
    """Relatório do dia em tópicos, no tom do AURUM, só com dados da apuração."""
    p, proj, mac = c["plano"], c["projecao"], c["macro"]
    nome = c.get("nome") or ""
    linhas = [f"{saudacao(nome)}. Varredura concluída: {c['n_empresas']} empresas analisadas"
              + (f", cotações até {pd.Timestamp(c['cotacoes_ate']):%d/%m/%Y}." if c.get("cotacoes_ate") else ".")]
    if c["demo"]:
        linhas.append("⚠️ Atenção: estou operando com DADOS FICTÍCIOS de demonstração. Nada aqui vale para investir.")
    compra = [x for x in c["top10"] if x["sinal"] == "Comprar"]
    if compra:
        b = compra[0]
        linhas.append(f"🎯 Melhor oportunidade agora: **{b['ticker']}** ({b['empresa']}), nota {b['nota']:.0f}. {b['por_que']}")
    else:
        linhas.append("🎯 Nenhuma das 10 primeiras está abaixo do preço-teto hoje. Paciência também é estratégia: "
                      "o aporte pode esperar na renda fixa até surgir preço bom.")
    if c["compras_do_mes"]:
        lista = ", ".join(f"{x['ticker']} ({x['cotas']})" for x in c["compras_do_mes"])
        renda = sum(x["renda_anual"] for x in c["compras_do_mes"])
        linhas.append(f"🛒 Plano do mês para {_r(p['aporte_mensal'])}: {lista}. Isso acrescenta cerca de {_r(renda)} por ano em proventos.")
    linhas.append(f"🚀 Rumo a {_r(p['meta'], 0)}: você tem {_r(p['patrimonio_hoje'], 0)}. No ritmo atual, o mais provável é chegar em "
                  f"**{meta.fmt_tempo(proj['meses_mais_provavel'])}** (com anos ruins, até {meta.fmt_tempo(proj['meses_anos_ruins'])}). "
                  + (f"Com R$ 500 a mais por mês, cairia para {meta.fmt_tempo(proj['meses_com_500_a_mais'])}." if proj["meses_com_500_a_mais"] else ""))
    rf = proj.get("meses_so_renda_fixa")
    cmp = (f"a renda fixa líquida ({_p(mac['renda_fixa_liquida'])} a.a.) chegaria em {meta.fmt_tempo(rf)} — "
           + ("tão rápido quanto as ações hoje; considere dividir o aporte entre as duas."
              if rf is not None and proj["meses_mais_provavel"] is not None and rf <= proj["meses_mais_provavel"]
              else "as ações tendem a ganhar no longo prazo, com mais oscilação."))
    linhas.append(f"🏦 Cenário: Selic {_p(mac['selic'], 2)}, inflação {_p(mac['ipca_12m'])}. Para comparação, {cmp}"
                  + (" (taxas estimadas: Banco Central fora do ar)" if mac["estimado"] else ""))
    if c.get("mesa_de_analistas"):
        linhas.append(f"🧠 Mesa de analistas (Dora, Fausto, Vitória, Téo, Nina, Íris, Rex, Otto, Bento e Sofia): {c['mesa_de_analistas']['resumo']}.")
    tp = texto_previsibilidade(c)
    if tp:
        linhas.append(tp)
    if c.get("previsora_iris"):
        linhas.append(texto_iris(c))
    if c.get("atlas_explorador"):
        linhas.append("🧭 Atlas, explorando por conta própria: " + c["atlas_explorador"].splitlines()[0])
    if mac.get("leitura_juros"):
        linhas.append("🔭 Um passo à frente: " + mac["leitura_juros"])
    if c.get("proximos_balancos"):
        linhas.append("🗓️ Balanços chegando: " + ", ".join(f"{t} ({pd.Timestamp(d):%d/%m})" for t, d in c["proximos_balancos"][:5]) + ".")
    if c["alertas_importantes"]:
        linhas.append(f"🔔 {len(c['alertas_importantes'])} alerta(s) importante(s). Principal: {c['alertas_importantes'][0]}")
    if c["dados_duvidosos"]:
        linhas.append(f"🛡️ Por precaução, não recomendo compra em {', '.join(c['dados_duvidosos'][:6])}: os dados vieram inconsistentes.")
    bt = c.get("teste_no_passado")
    if bt and bt.get("tir_sistema") == bt.get("tir_sistema") and bt.get("tir_sistema") is not None:
        linhas.append(f"🧪 No teste dos últimos {bt['meses'] // 12} anos, o método rendeu {_p(bt['tir_sistema'])} ao ano "
                      f"(CDI: {_p(bt['tir_cdi'])}). Passado não garante futuro, mas mostra que o método faz sentido.")
    return linhas


def _acha_ticker(texto: str, tickers: list[str]) -> str | None:
    conhecidos = set(tickers)
    for tok in re.findall(r"[A-Z0-9]{4,8}", texto.upper()):
        if tok in conhecidos:
            return tok
        if tok.endswith("F") and tok[:-1] in conhecidos:  # código do mercado fracionário (ex.: TAEE11F)
            return tok[:-1]
    return None


def responder_regras(pergunta: str, c: dict, R: dict) -> str:
    """Respostas sem IA para as perguntas mais comuns."""
    q = pergunta.lower()
    rk: pd.DataFrame = R["ranking"]
    t = _acha_ticker(pergunta, rk["ticker"].tolist())
    if any(k in q for k in ("trade", "trading", "swing", "operar", "stop", "alvo", "vender com lucro", "curto prazo")) and not t:
        return texto_trading(c)
    if t:
        r = rk.set_index("ticker").loc[t]
        txt = (f"**{t} — {r['nome']}**: sinal **{r['sinal']}**, nota {r['nota']:.0f}/100 ({int(r['posicao'])}º de {len(rk)}). "
               f"Preço {_r(r['preco'])}, preço-teto {_r(r['preco_teto_bazin'])}. {r['por_que']} "
               f"Previsão de proventos nos próximos 12 meses: {_r(r.get('proventos_previstos_12m'))} por ação ({_p(r.get('dy_previsto'))}). "
               f"Confiança dos dados: {r.get('confianca', '—')}.")
        if _arred(r.get("otto_prov_12m")) is not None:
            txt += (f" 💵 Otto: {_r(r['otto_prov_12m'])} por ação em 12 meses (faixa {_r(r.get('otto_prov_p10'))} a {_r(r.get('otto_prov_p90'))}), "
                    f"risco de corte {_p(r.get('otto_prob_corte'), 0)}.")
        if _arred(r.get("bento_preco_80")) is not None:
            txt += f" 🎯 Bento: ordem a {_r(r['bento_preco_80'])} executa ~80% das vezes em 1 mês; a {_r(r.get('bento_preco_50'))}, ~50%."
        if R.get("mesa") and t in R["mesa"]["opinioes"]:
            ops = R["mesa"]["opinioes"][t]
            txt += f"\n\nMesa de analistas: **{r.get('consenso', '—')}**. " + " ".join(
                f"{mesa_mod.POR_ID[a].icone} {mesa_mod.POR_ID[a].apelido}: {o['argumentos'][0] if o['argumentos'] else 'sem comentário'}"
                for a, o in ops.items())
        if r.get("prob_alta_1m") == r.get("prob_alta_1m") and r.get("prob_alta_1m") is not None:
            txt += f" Chance de alta no próximo mês (Íris): {_p(r['prob_alta_1m'], 0)}."
        news = (R.get("noticias") or {}).get(t, [])
        if news:
            txt += f" Última notícia: “{news[0]['titulo']}” ({news[0]['fonte']})."
        return txt
    if any(k in q for k in ("cair", "subir", "queda", "alta", "previs", "próximo mês", "proximo mes", "curto prazo")):
        return texto_iris(c)
    if any(k in q for k in ("agente", "mesa", "equipe", "time", "analistas")):
        m = c.get("mesa_de_analistas")
        if not m:
            return "A mesa de analistas ainda não se reuniu nesta apuração. Clique em Apurar agora."
        return "Minha equipe hoje: " + m["resumo"] + ".\n\n" + "\n".join("- " + x for x in m["atividade"])
    if any(k in q for k in ("meta", "milh", "quando", "tempo", "chegar", "aposent", "rápido", "rapido")):
        p, pr = c["plano"], c["projecao"]
        return (f"Com {_r(p['patrimonio_hoje'], 0)} hoje e {_r(p['aporte_mensal'], 0)} por mês, o mais provável é chegar a {_r(p['meta'], 0)} em "
                f"**{meta.fmt_tempo(pr['meses_mais_provavel'])}** (anos bons: {meta.fmt_tempo(pr['meses_anos_bons'])}; ruins: "
                f"{meta.fmt_tempo(pr['meses_anos_ruins'])}). A alavanca mais forte é o aporte: +R$ 500/mês → "
                f"{meta.fmt_tempo(pr['meses_com_500_a_mais'])}. Veja a aba 🎯 para testar outros valores.")
    if any(k in q for k in ("compr", "aporte", "investir", "onde coloco", "onde invisto")):
        if not c["compras_do_mes"]:
            return "Hoje nada está com preço bom. Recomendo deixar o aporte na renda fixa e aguardar o meu aviso."
        return ("Para este mês: " + "; ".join(f"**{x['ticker']}** {x['cotas']} cota(s) a {_r(x['preco'])} = {_r(x['total'])}"
                                             for x in c["compras_do_mes"]) + f". Sobra {_r(c['sobra_do_mes'])}.")
    if any(k in q for k in ("dividend", "provento", "jcp", "renda passiva", "renda mensal")):
        top = sorted([x for x in c["top10"] if x["sinal"] in ("Comprar", "Acumular")],
                     key=lambda x: x["proventos_ano_medio_5a_pct"] or 0, reverse=True)[:5]
        return "Melhores pagadoras entre as bem avaliadas: " + "; ".join(
            f"**{x['ticker']}** paga em média {_p(x['proventos_ano_medio_5a_pct'])} ao ano (costuma pagar em {x['meses_que_paga']})" for x in top) + "."
    if any(k in q for k in ("selic", "juros", "renda fixa", "cdi", "tesouro", "poupan")):
        m = c["macro"]
        return (f"Selic em {_p(m['selic'], 2)}; renda fixa líquida ≈ {_p(m['renda_fixa_liquida'])} ao ano. "
                f"Só na renda fixa você chegaria à meta em {meta.fmt_tempo(c['projecao']['meses_so_renda_fixa'])}. "
                "Quando os juros estão altos, dividir entre renda fixa e ações reduz o risco sem atrasar muito a meta.")
    if any(k in q for k in ("risco", "perder", "seguro", "confi", "garant")):
        bt = c.get("teste_no_passado") or {}
        return ("Nenhum sistema garante retorno — eu também não. O que faço é reduzir erros: só boas pagadoras, preço abaixo do teto, "
                "no máximo 2 por setor, e bloqueio ações com dados duvidosos. "
                + (f"No teste dos últimos anos o método rendeu {_p(bt.get('tir_sistema'))} ao ano contra {_p(bt.get('tir_cdi'))} do CDI. " if bt else "")
                + "Tenha reserva de emergência e não venda no pânico.")
    if any(k in q for k in ("melhor", "top", "ranking", "recomend")):
        return "Top 5 agora: " + "; ".join(f"{x['posicao']}. **{x['ticker']}** ({x['sinal']}, nota {x['nota']:.0f})" for x in c["top10"][:5]) + "."
    return ("Posso te responder sobre: uma ação específica (ex.: *TAEE11 vale a pena?*), *o que comprar este mês*, "
            "*quando chego no milhão*, *melhores pagadoras de dividendos*, *quais podem subir ou cair*, *o que a equipe decidiu*, "
            "*Selic e renda fixa* e *riscos*. "
            "Para conversa livre e pesquisa na internet, configure a chave da IA (ANTHROPIC_API_KEY) — veja o README.")


# ------------------------------------------------------------------ IA (Claude), opcional
SISTEMA = """Você é AURUM, o estrategista-chefe de investimentos do usuário, com o tom de uma mesa de operações profissional:
objetivo, preciso, confiante e cordial, sempre em português do Brasil. O objetivo do usuário é construir patrimônio
(meta no contexto) com aportes mensais em ações brasileiras que pagam dividendos e JCP, no longo prazo.

Regras inegociáveis:
- Use APENAS os números do CONTEXTO (apuração do Radar de Ações) e o que encontrar na pesquisa web, citando a fonte. Nunca invente cotação, provento ou indicador.
- Diga a data dos dados quando citar números. Se "demo" for true, avise que os dados são fictícios.
- Nunca prometa retorno nem diga que algo é garantido. Fale em chances e cenários. Lembre de reserva de emergência e diversificação quando fizer sentido.
- Se a renda fixa estiver tão boa quanto as ações para a meta, diga isso com franqueza.
- Ações com "avisos" ou confiança Baixa: recomende conferir antes de comprar.
- Seja direto: tópicos curtos, valores em R$ no formato brasileiro, nada de jargão sem explicar.
- Isto é apoio à decisão, não recomendação formal de investimento."""

PEDIDO_RELATORIO = """Escreva o relatório diário (no máximo 300 palavras), com estes tópicos:
1. Saudação de uma linha e o estado dos dados (data das cotações).
2. A melhor oportunidade do dia e por quê.
3. O plano de compras do mês (já calculado no contexto) em uma frase.
4. Onde o usuário está em relação à meta e a alavanca mais forte para acelerar.
5. Pesquisa: busque na web notícias dos últimos 7 dias sobre as 3 primeiras ações do plano do mês (e da carteira, se houver).
   Se algo mudar a tese (corte de dividendos, investigação, fato relevante, troca de comando), destaque com a fonte. Se nada relevante, diga isso.
6. Um alerta de risco honesto, se houver.
Termine com uma frase curta de recomendação para hoje."""


def ia_disponivel() -> bool:
    return ia.disponivel()


def _chamar(mensagens: list[dict], c: dict, pesquisar: bool, max_buscas: int = 5) -> str | None:
    """Chama o Claude com o contexto do dia (em cache) e, se pedido, a ferramenta de pesquisa web."""
    sistema = [{"type": "text", "text": SISTEMA},
               {"type": "text", "text": "CONTEXTO (apuração do Radar de Ações):\n" + json.dumps(c, ensure_ascii=False, sort_keys=True, default=str),
                "cache_control": {"type": "ephemeral"}}]
    return ia.chamar(sistema, mensagens, [ia.pesquisa_web(max_buscas)] if pesquisar else None)


def relatorio(R: dict, pl: dict | None = None, usar_ia: bool = True) -> dict:
    """{'texto': str (markdown), 'fonte': 'IA'|'regras', 'hora': iso}."""
    c = contexto(R, pl)
    texto, fonte = None, "regras"
    if usar_ia and ia_disponivel():
        texto = _chamar([{"role": "user", "content": PEDIDO_RELATORIO}], c, pesquisar=not c["demo"])
        fonte = "IA" if texto else "regras"
    if not texto:
        texto = "\n\n".join(relatorio_regras(c))
    return {"texto": texto, "fonte": fonte, "hora": datetime.now().isoformat(timespec="minutes")}


def perguntar(pergunta: str, historico: list[dict], R: dict, pl: dict | None = None) -> tuple[str, str]:
    """(resposta, fonte). historico: [{'role': 'user'|'assistant', 'content': str}, ...] sem a pergunta atual."""
    c = contexto(R, pl)
    if ia_disponivel():
        resp = _chamar(historico + [{"role": "user", "content": pergunta}], c, pesquisar=not c["demo"], max_buscas=3)
        if resp:
            return resp, "IA"
    return responder_regras(pergunta, c, R), "regras"
