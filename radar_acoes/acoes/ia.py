"""Acesso à IA (Claude) compartilhado pelo AURUM e pela mesa de analistas. Opcional: sem chave, nada aqui é chamado."""
from __future__ import annotations

import json
import os

MODELO = os.getenv("AURUM_MODELO") or os.getenv("JARVIS_MODELO") or "claude-opus-5-5"  # JARVIS_*: nome antigo, ainda aceito


def disponivel() -> bool:
    if os.getenv("AURUM_SEM_IA") or os.getenv("JARVIS_SEM_IA"):
        return False
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return False
    return bool(os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"))


def pesquisa_web(max_buscas: int) -> dict:
    return {"type": "web_search_20260209", "name": "web_search", "max_uses": max_buscas,
            "user_location": {"type": "approximate", "country": "BR", "timezone": "America/Sao_Paulo"}}


def chamar(sistema: list[dict] | str, mensagens: list[dict], ferramentas: list[dict] | None = None,
           esquema: dict | None = None, esforco: str = "medium") -> str | None:
    """Chama o Claude e devolve o texto final (ou None se falhar/recusar — quem chama usa o modo por regras).

    - ferramentas: ex. [pesquisa_web(5)]; o turno pode pausar (pause_turn) e continuamos.
    - esquema: JSON Schema para resposta estruturada (output_config.format); o texto devolvido é JSON válido.
    """
    import anthropic

    client = anthropic.Anthropic()
    msgs = list(mensagens)
    output_config: dict = {"effort": esforco}
    if esquema:
        output_config["format"] = {"type": "json_schema", "schema": esquema}
    try:
        for _ in range(4):
            resp = client.beta.messages.create(
                model=MODELO, max_tokens=16000, system=sistema, messages=msgs, output_config=output_config,
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
                **({"tools": ferramentas} if ferramentas else {}),
            )
            if resp.stop_reason == "pause_turn":
                msgs.append({"role": "assistant", "content": resp.content})
                continue
            if resp.stop_reason in ("refusal", "max_tokens"):
                return None
            texto = "".join(b.text for b in resp.content if b.type == "text").strip()
            return texto or None
    except anthropic.AuthenticationError:
        print("  [IA] chave inválida — usando o modo por regras.")
    except anthropic.RateLimitError:
        print("  [IA] limite de uso atingido — usando o modo por regras.")
    except anthropic.APIStatusError as e:
        print(f"  [IA] erro {e.status_code} — usando o modo por regras.")
    except anthropic.APIConnectionError:
        print("  [IA] sem conexão — usando o modo por regras.")
    return None


def chamar_json(sistema, mensagens, esquema: dict, esforco: str = "medium") -> dict | None:
    texto = chamar(sistema, mensagens, esquema=esquema, esforco=esforco)
    if not texto:
        return None
    try:
        return json.loads(texto)
    except json.JSONDecodeError:
        return None
