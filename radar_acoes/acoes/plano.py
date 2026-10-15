"""Seu plano pessoal (aporte, meta, quanto já tem fora da bolsa), salvo em dados_acoes/plano.json."""
from __future__ import annotations

import json
import os

from . import DADOS

ARQ = DADOS / "plano.json"
PADRAO = {"aporte_mensal": 1000.0, "meta": 1_000_000.0, "aumento_aporte_aa": 0.05,
          "patrimonio_fora_bolsa": 0.0, "corrigir_inflacao": False}


def ler() -> dict:
    p = dict(PADRAO)
    if os.getenv("APORTE_MENSAL"):
        try:
            p["aporte_mensal"] = float(os.environ["APORTE_MENSAL"])
        except ValueError:
            pass
    try:
        p.update(json.loads(ARQ.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError):
        pass
    return p


def salvar(p: dict) -> None:
    ARQ.parent.mkdir(parents=True, exist_ok=True)
    ARQ.write_text(json.dumps({k: p[k] for k in PADRAO if k in p}, ensure_ascii=False, indent=2), encoding="utf-8")


def patrimonio_atual(p: dict, carteira, ranking) -> float:
    """Valor de hoje da carteira de ações (pelos preços da apuração) + o que você tem fora da bolsa."""
    precos = dict(zip(ranking["ticker"], ranking["preco"])) if ranking is not None and len(ranking) else {}
    em_acoes = sum(q * (precos.get(t) or 0) for t, q in zip(carteira["ticker"], carteira["quantidade"])) if len(carteira) else 0.0
    return float(em_acoes) + float(p.get("patrimonio_fora_bolsa") or 0)
