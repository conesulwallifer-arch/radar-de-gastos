"""Alertas do dia (comparando com a apuração anterior) e envio por Telegram e/ou e-mail."""
from __future__ import annotations

import os
import time
import smtplib
from datetime import date, timedelta
from email.mime.text import MIMEText

import pandas as pd
import requests

from . import RAIZ


def carregar_config() -> None:
    """Lê radar_acoes/config.env (veja acoes.carregar_config)."""
    from . import carregar_config as _c
    _c()


def _texto(v) -> str | None:
    """Datas vêm como texto ISO; célula vazia numa tabela vira NaN (que é 'verdadeiro' em Python) — trata como ausente."""
    return v if isinstance(v, str) and v else None


def _fmt_pct(x) -> str:
    return "—" if x is None or x != x else f"{x*100:+.1f}%".replace(".", ",")


def _fmt_r(x) -> str:
    return "—" if x is None or x != x else f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def gerar(atual: pd.DataFrame, anterior: pd.DataFrame | None, noticias: dict[str, list[dict]],
          carteira: list[str] | None = None, top: int = 10, hoje: date | None = None) -> list[dict]:
    """Lista de alertas {nivel, tipo, ticker, texto}. nivel: 1 = mais importante."""
    hoje = hoje or date.today()
    carteira = set(carteira or [])
    alertas: list[dict] = []
    ant = anterior.set_index("ticker") if anterior is not None and len(anterior) else pd.DataFrame()

    def add(nivel, tipo, t, texto):
        alertas.append({"nivel": nivel, "tipo": tipo, "ticker": t, "texto": texto})

    for _, r in atual.iterrows():
        t = r["ticker"]
        a = ant.loc[t] if t in ant.index else None
        # Oportunidade de compra
        if r["sinal"] == "Comprar":
            novo = a is None or a.get("sinal") != "Comprar"
            add(1 if novo else 3, "Oportunidade", t,
                f"{'NOVA ' if novo else ''}oportunidade: {t} ({r['nome']}) a {_fmt_r(r['preco'])}, abaixo do preço-teto "
                f"{_fmt_r(r['preco_teto_bazin'])} (margem {_fmt_pct(r['margem_bazin'])}), DY médio 5a {_fmt_pct(r['dy_medio_5a'])}, nota {r['nota']:.0f}.")
        # Mesa de analistas: novo consenso de compra forte
        if r.get("consenso") == "Compra forte" and (a is None or a.get("consenso") != "Compra forte"):
            placar = f"{r.get('placar', 0):+.2f}".replace(".", ",")
            add(1, "Mesa", t, f"A mesa de analistas chegou a consenso de COMPRA FORTE em {t} "
                              f"({int(r.get('a_favor', 0))} agentes a favor, placar {placar}).")
        # Entrou/saiu do top
        if a is not None and r["posicao"] <= top < a["posicao"]:
            add(2, "Ranking", t, f"{t} entrou no top {top} (era {int(a['posicao'])}º, agora {int(r['posicao'])}º).")
        if a is not None and a["posicao"] <= top < r["posicao"]:
            add(2, "Ranking", t, f"{t} saiu do top {top} (agora {int(r['posicao'])}º).")
        # Queda forte numa ação boa
        if r["var_dia"] == r["var_dia"] and r["var_dia"] <= -0.05 and r["nota"] >= 55:
            add(1, "Queda forte", t, f"{t} caiu {_fmt_pct(r['var_dia'])} hoje. Boa empresa (nota {r['nota']:.0f}): "
                                     "veja as notícias — pode ser oportunidade ou problema.")
        # Novo provento anunciado
        if a is not None and _texto(r.get("ultimo_provento_data")) and r.get("ultimo_provento_data") != a.get("ultimo_provento_data"):
            add(1, "Provento", t, f"{t} tem novo provento: {_fmt_r(r['ultimo_provento_valor'])} por ação (data-ex {r['ultimo_provento_data']}).")
        # Data-com chegando
        ex = _texto(r.get("ex_dividendo"))
        if ex:
            try:
                dex = date.fromisoformat(ex)
                if hoje <= dex <= hoje + timedelta(days=10) and (r["nota"] >= 55 or t in carteira):
                    add(1, "Data-com", t, f"{t}: data-ex em {dex:%d/%m}. Para receber o provento, compre até o pregão anterior "
                                          f"({(pd.Timestamp(dex) - pd.offsets.BDay(1)):%d/%m}).")
            except ValueError:
                pass
        # Balanço chegando (antecipação: resultado mexe com preço e com proventos)
        pb = _texto(r.get("proximo_balanco"))
        if pb and (r["posicao"] <= 15 or t in carteira):
            try:
                dpb = date.fromisoformat(pb)
                if hoje <= dpb <= hoje + timedelta(days=7):
                    add(2, "Balanço", t, f"{t} divulga resultado em {dpb:%d/%m}. A equipe vai reavaliar no dia seguinte; "
                                         "evite decisões grandes antes do número sair.")
            except ValueError:
                pass
        # Carteira
        if t in carteira and r["sinal"] == "Evitar" and (a is None or a.get("sinal") != "Evitar"):
            add(1, "Carteira", t, f"{t}, que está na sua carteira, passou para 'Evitar' (nota {r['nota']:.0f}). Revise os fundamentos.")
        # Notícias negativas importantes (top + carteira)
        if r["posicao"] <= 20 or t in carteira:
            for n in noticias.get(t, [])[:10]:
                if n["tom"] == "negativa" and set(n["assuntos"]) & {"Proventos", "Governança", "Resultado"} \
                        and n["quando"] and n["quando"].date() >= hoje - timedelta(days=1):
                    add(2, "Notícia", t, f"{t}: {n['titulo']} ({n['fonte']}) {n['link']}")
    alertas.sort(key=lambda x: (x["nivel"], x["ticker"]))
    return alertas


def texto_resumo(ranking: pd.DataFrame, alertas: list[dict], compras: pd.DataFrame | None = None,
                 top: int = 10, hoje: date | None = None, sobra: float = 0.0) -> str:
    hoje = hoje or date.today()
    l = [f"📈 Radar de Ações — {hoje:%d/%m/%Y}", ""]
    importantes = [a for a in alertas if a["nivel"] <= 2]
    if importantes:
        l.append("🔔 Alertas")
        l += [f"• [{a['tipo']}] {a['texto']}" for a in importantes[:25]]
        l.append("")
    l.append(f"🏆 Top {top} para renda (longo prazo)")
    for _, r in ranking.head(top).iterrows():
        l.append(f"{int(r['posicao'])}. {r['ticker']} — nota {r['nota']:.0f} | {r['sinal']} | {_fmt_r(r['preco'])} | "
                 f"teto {_fmt_r(r['preco_teto_bazin'])} | DY5a {_fmt_pct(r['dy_medio_5a'])}")
    if compras is not None and len(compras):
        l += ["", "🛒 Sugestão para o aporte do mês"]
        l += [f"• {r['ticker']}: {int(r['comprar_qtd'])} cota(s) ≈ {_fmt_r(r['valor'])}" for _, r in compras.iterrows()]
        l.append(f"Total {_fmt_r(compras['valor'].sum())}; sobra {_fmt_r(sobra)} (fica para o próximo mês). "
                 f"Renda anual estimada desta compra: {_fmt_r(compras['renda_anual_estimada'].sum())}.")
    l += ["", "Não é recomendação de investimento. Confira os dados antes de investir."]
    return "\n".join(l)


def enviar_telegram(texto: str) -> bool:
    token, chat = os.getenv("TELEGRAM_TOKEN"), os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat:
        return False
    ok = True
    for parte in _partes(texto, 3900):  # limite de 4096 caracteres por mensagem; corta entre linhas
        enviado = False
        for tentativa in range(3):
            try:
                r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage",
                                  data={"chat_id": chat, "text": parte, "disable_web_page_preview": "true"}, timeout=20)
            except requests.RequestException as e:
                print(f"  [telegram] falhou (tentativa {tentativa + 1}): {type(e).__name__}: {str(e).replace(token, '***')[:160]}")
                time.sleep(2 * (tentativa + 1))
                continue
            if r.ok:
                enviado = True
                break
            print(f"  [telegram] erro {r.status_code}: {r.text[:200].replace(token, '***')}")
            if r.status_code == 429:  # muitas mensagens: o Telegram diz quanto esperar
                try:
                    time.sleep(int(r.json().get("parameters", {}).get("retry_after", 3)) + 1)
                except Exception:  # noqa: BLE001
                    time.sleep(3)
                continue
            break  # 400/401/403: token ou chat errado — repetir não resolve
        ok &= enviado
    return ok


def _partes(texto: str, limite: int) -> list[str]:
    partes, atual = [], ""
    for linha in texto.splitlines(keepends=True):
        while len(linha) > limite:  # linha gigante: corta no limite
            if atual:
                partes.append(atual)
                atual = ""
            partes.append(linha[:limite])
            linha = linha[limite:]
        if len(atual) + len(linha) > limite:
            partes.append(atual)
            atual = ""
        atual += linha
    if atual.strip():
        partes.append(atual)
    return partes


def enviar_email(assunto: str, texto: str) -> bool:
    remetente, senha, destino = os.getenv("EMAIL_REMETENTE"), os.getenv("EMAIL_SENHA"), os.getenv("EMAIL_DESTINO")
    if not remetente or not senha or not destino:
        return False
    msg = MIMEText(texto, "plain", "utf-8")
    msg["Subject"], msg["From"], msg["To"] = assunto, remetente, destino
    try:
        with smtplib.SMTP_SSL(os.getenv("SMTP_HOST", "smtp.gmail.com"), int(os.getenv("SMTP_PORTA", "465")), timeout=30) as s:
            s.login(remetente, senha)
            s.sendmail(remetente, [d.strip() for d in destino.split(",")], msg.as_string())
        return True
    except Exception as e:  # noqa: BLE001
        print(f"  [e-mail] falhou: {e}")
        return False
