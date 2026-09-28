"""Modo público (versão aberta na internet, ex.: Hugging Face Spaces).

RADAR_PUBLICO=1  → esconde dados pessoais (CPF), mostra aviso legal, some botões de manutenção.
RADAR_DATASET=<usuario/repo>  → na 1ª execução baixa o banco e os caches do dataset do Hugging Face.
"""
import os

from radar.util import DADOS

PUBLICO = os.environ.get("RADAR_PUBLICO") == "1"
DATASET = os.environ.get("RADAR_DATASET", "")


def garantir_banco() -> None:
    if (DADOS / "radar.duckdb").exists() or not DATASET:
        return
    from huggingface_hub import snapshot_download
    snapshot_download(repo_id=DATASET, repo_type="dataset", local_dir=str(DADOS))


def atualizado_em() -> str:
    arq = DADOS / "atualizado_em.txt"
    return arq.read_text(encoding="utf-8").strip() if arq.exists() else ""
