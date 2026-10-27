"""Assistente de configuração do AURUM: Telegram, e-mail (opcional), chave da IA e aporte mensal.

    python configurar.py      (ou dois cliques em "Configurar AURUM.bat")

Pergunta o que precisa, descobre sozinho o seu chat do Telegram, testa cada item e grava o arquivo config.env.
Nada é enviado para outro lugar além do próprio Telegram e da Anthropic (para testar a chave).
"""
from __future__ import annotations

import getpass
import os
import sys
import time
from pathlib import Path

import requests

RAIZ = Path(__file__).resolve().parent
ARQ = RAIZ / "config.env"


def ler_config() -> dict[str, str]:
    cfg = {}
    if ARQ.exists():
        for linha in ARQ.read_text(encoding="utf-8").splitlines():
            if "=" in linha and not linha.lstrip().startswith("#"):
                k, v = linha.split("=", 1)
                cfg[k.strip()] = v.strip()
    return cfg


def gravar_config(cfg: dict[str, str]) -> None:
    linhas = ["# Gerado pelo assistente configurar.py — NÃO compartilhe este arquivo (tem suas senhas e chaves)."]
    for k, v in cfg.items():
        if v:
            linhas.append(f"{k}={v}")
    ARQ.write_text("\n".join(linhas) + "\n", encoding="utf-8")


def perguntar(texto: str, atual: str = "", segredo: bool = False) -> str:
    dica = " [Enter mantém o atual]" if atual else ""
    if segredo:
        dica += " (cole com o botão direito do mouse; por segurança o texto NÃO aparece na tela — é normal)"
    leitor = getpass.getpass if segredo else input
    resp = leitor(f"{texto}{dica}: ").strip()
    return resp or atual


def titulo(t: str) -> None:
    print("\n" + "=" * 64 + f"\n  {t}\n" + "=" * 64)


# ------------------------------------------------------------------ Telegram
def descobrir_chat(token: str, espera_s: int = 120) -> str | None:
    """Espera você mandar uma mensagem ao bot e devolve o id do chat."""
    url = f"https://api.telegram.org/bot{token}/getUpdates"
    fim = time.time() + espera_s
    while time.time() < fim:
        try:
            r = requests.get(url, timeout=20).json()
        except requests.RequestException:
            r = {}
        for upd in reversed(r.get("result", [])):
            msg = upd.get("message") or upd.get("channel_post") or {}
            chat = msg.get("chat", {})
            if chat.get("id"):
                return str(chat["id"])
        print("   ...aguardando sua mensagem para o bot (mande um 'oi' no Telegram)")
        time.sleep(5)
    return None


def configurar_telegram(cfg: dict) -> None:
    titulo("1/3  ALERTAS NO CELULAR (TELEGRAM)")
    print("""Passo a passo no celular:
  1. Abra o Telegram e procure por  @BotFather  (tem um selo azul de verificado).
  2. Toque em Iniciar e mande:  /newbot
  3. Escolha um nome (ex.: AURUM Investimentos) e depois um usuário terminado em 'bot' (ex.: aurum_seunome_bot).
  4. O BotFather responde com um TOKEN parecido com  123456789:ABCdefGhIJKlmNoPQRstuVWxyz
  5. Copie esse token e cole aqui.
""")
    token = perguntar("Cole o token do bot", cfg.get("TELEGRAM_TOKEN", ""), segredo=True)
    if not token:
        print("   Pulando o Telegram.")
        return
    try:
        eu = requests.get(f"https://api.telegram.org/bot{token}/getMe", timeout=20).json()
    except requests.RequestException as e:
        print(f"   ❌ Não consegui falar com o Telegram ({e}). Verifique a internet e rode de novo.")
        return
    if not eu.get("ok"):
        print("   ❌ Token inválido. Confira se copiou inteiro (com o número, os dois-pontos e as letras).")
        return
    nome_bot = eu["result"].get("username")
    print(f"   ✅ Token válido: seu bot é @{nome_bot}")
    cfg["TELEGRAM_TOKEN"] = token
    print(f"\n   Agora, no Telegram, abra o seu bot (procure @{nome_bot}), toque em INICIAR e mande qualquer mensagem, ex.: oi")
    chat = cfg.get("TELEGRAM_CHAT_ID") or descobrir_chat(token)
    if not chat:
        print("   ❌ Não recebi sua mensagem em 2 minutos. Rode o assistente de novo e mande o 'oi' para o bot.")
        return
    cfg["TELEGRAM_CHAT_ID"] = chat
    r = requests.post(f"https://api.telegram.org/bot{token}/sendMessage", timeout=20,
                      data={"chat_id": chat, "text": "🪙 AURUM conectado! A partir de agora você recebe aqui os alertas e o relatório do dia."})
    print("   ✅ Mensagem de teste enviada — confira no Telegram!" if r.ok else f"   ❌ O envio falhou: {r.text[:200]}")


# ------------------------------------------------------------------ IA
def configurar_ia(cfg: dict) -> None:
    titulo("2/3  RELATÓRIOS COM IA E PESQUISA NA INTERNET (OPCIONAL)")
    print("""Com a chave, o AURUM, os agentes e o Atlas usam a IA Claude: escrevem o relatório, pesquisam notícias
na internet e conversam livremente com você no painel. É pago por uso (centavos de dólar por relatório ou pergunta;
com o agente ligado todo dia, conte algo como alguns dólares por mês — você pode pôr um limite de gasto no site).

Passo a passo no computador:
  1. Entre em  https://console.anthropic.com  e crie sua conta.
  2. Em "Billing" (Cobrança), adicione um cartão e créditos (ex.: US$ 5). Ali dá para definir um limite mensal.
  3. Em "API Keys", clique em "Create Key", dê um nome (ex.: AURUM) e copie a chave (começa com  sk-ant- ).
     Ela só aparece uma vez: cole aqui em seguida.
""")
    chave = perguntar("Cole a chave da IA (ou Enter para pular)", cfg.get("ANTHROPIC_API_KEY", ""), segredo=True)
    if not chave:
        print("   Pulando a IA: o AURUM funciona no modo local (grátis).")
        return
    try:
        import anthropic
    except ImportError:
        print("   ❌ Falta instalar a biblioteca. Rode:  python -m pip install -r requirements.txt  e depois este assistente de novo.")
        return
    sys.path.insert(0, str(RAIZ))
    from acoes.ia import MODELO
    try:
        modelo = anthropic.Anthropic(api_key=chave).models.retrieve(MODELO)  # confere a chave sem gastar créditos
        print(f"   ✅ Chave válida, com acesso ao modelo {modelo.display_name}.")
        cfg["ANTHROPIC_API_KEY"] = chave
    except anthropic.AuthenticationError:
        print("   ❌ Chave inválida. Copie de novo do site (começa com sk-ant-).")
    except anthropic.PermissionDeniedError:
        print("   ❌ A chave não tem permissão. Confira se a conta tem créditos em Billing.")
    except anthropic.APIConnectionError:
        print("   ⚠️ Sem conexão para testar agora; gravei a chave mesmo assim.")
        cfg["ANTHROPIC_API_KEY"] = chave
    except anthropic.APIStatusError as e:
        print(f"   ⚠️ Não deu para confirmar ({e.status_code}); gravei a chave mesmo assim.")
        cfg["ANTHROPIC_API_KEY"] = chave


# ------------------------------------------------------------------ plano e e-mail
def configurar_plano(cfg: dict) -> None:
    titulo("3/3  SEU APORTE MENSAL E E-MAIL (OPCIONAL)")
    ap = perguntar("Quanto você pretende investir por mês, em reais (ex.: 1000)", cfg.get("APORTE_MENSAL", "1000"))
    try:
        cfg["APORTE_MENSAL"] = str(int(float(ap.replace(".", "").replace(",", "."))))
    except ValueError:
        print("   Valor não entendido; mantive 1000. Você pode mudar depois na aba 🎯 do painel.")
        cfg["APORTE_MENSAL"] = "1000"
    if perguntar("Quer receber também por e-mail? (s/n)", "n").lower().startswith("s"):
        print("   Para Gmail: ative a verificação em 2 etapas e crie uma 'senha de app' em myaccount.google.com/apppasswords.")
        cfg["EMAIL_REMETENTE"] = perguntar("   Seu Gmail", cfg.get("EMAIL_REMETENTE", ""))
        cfg["EMAIL_SENHA"] = perguntar("   Senha de app (16 letras)", cfg.get("EMAIL_SENHA", ""), segredo=True).replace(" ", "")
        cfg["EMAIL_DESTINO"] = perguntar("   Enviar para (pode ser o mesmo Gmail)", cfg.get("EMAIL_DESTINO", "") or cfg["EMAIL_REMETENTE"])


def main() -> None:
    print("\n🪙  AURUM — assistente de configuração\n(seus dados ficam só neste computador, no arquivo config.env)")
    cfg = ler_config()
    configurar_telegram(cfg)
    configurar_ia(cfg)
    configurar_plano(cfg)
    gravar_config(cfg)
    titulo("PRONTO!")
    print(f"Configuração salva em: {ARQ}")
    print("  • Telegram:", "✅ ligado" if cfg.get("TELEGRAM_CHAT_ID") else "— desligado")
    print("  • IA + pesquisa na internet:", "✅ ligada" if cfg.get("ANTHROPIC_API_KEY") else "— modo local (grátis)")
    print("  • E-mail:", "✅ ligado" if cfg.get("EMAIL_SENHA") else "— desligado")
    print(f"  • Aporte mensal: R$ {cfg.get('APORTE_MENSAL')}")
    print("\nPróximos passos: dois cliques em 'Iniciar AURUM.bat' (agente diário) e 'Abrir Painel Acoes.bat' (painel).")
    if os.name == "nt":
        input("\nAperte Enter para fechar.")


if __name__ == "__main__":
    main()
