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
    import zipfile
    from huggingface_hub import hf_hub_download
    DADOS.mkdir(parents=True, exist_ok=True)
    for nome in ("atualizado_em.txt", "bruto.zip", "radar.duckdb"):  # o banco por último: só "existe" quando tudo baixou
        try:
            arq = hf_hub_download(repo_id=DATASET, filename=nome, repo_type="dataset", local_dir=str(DADOS))
        except Exception as e:  # noqa: BLE001
            if nome == "radar.duckdb":
                raise
            print(f"  {nome}: {e}")
            continue
        if nome == "bruto.zip":
            with zipfile.ZipFile(arq) as z:
                z.extractall(DADOS / "bruto")


def atualizado_em() -> str:
    arq = DADOS / "atualizado_em.txt"
    return arq.read_text(encoding="utf-8").strip() if arq.exists() else ""
