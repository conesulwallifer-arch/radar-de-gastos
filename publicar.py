"""Publica o Radar de Gastos na internet (Hugging Face Spaces, grátis).

  python publicar.py

1ª vez: pede o token do Hugging Face (huggingface.co/settings/tokens, tipo "Write") e guarda em dados/.hf_token.
O que faz:
  1. cria uma cópia PÚBLICA do banco, com CPFs de pessoas físicas ocultos (LGPD);
  2. pré-carrega as fichas dos deputados e senadores (foto, contatos, redes);
  3. sobe os dados para o dataset  <usuario>/radar-de-gastos-dados;
  4. sobe o app para o Space       <usuario>/radar-de-gastos  e reinicia.
"""
import argparse
import datetime as dt
import shutil
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import duckdb

from radar.util import DADOS

RAIZ = Path(__file__).resolve().parent
PUB = DADOS / "publico"
TOKEN_ARQ = DADOS / ".hf_token"

# sal secreto (fica só no seu PC, em dados/.sal): sem ele ninguém consegue reverter os códigos para CPF
SAL_ARQ = DADOS / ".sal"
if not SAL_ARQ.exists():
    import secrets
    SAL_ARQ.parent.mkdir(parents=True, exist_ok=True)
    SAL_ARQ.write_text(secrets.token_hex(32))
SAL = SAL_ARQ.read_text().strip()
PID = "CASE WHEN {c} LIKE 'P-%' THEN 'P-' || substr(md5('" + SAL + "' || {c}), 1, 14) ELSE {c} END"
CPF = "CASE WHEN length({c}) = 11 THEN '***' || substr({c}, 4, 6) || '**#' || substr(md5('" + SAL + "' || {c}), 1, 6) ELSE {c} END"
TRANSFORMA = {
    "gastos": {"politico_id": PID, "politico_cpf": "''", "fornecedor_doc": CPF},
    "alertas": {"politico_id": PID, "detalhe": r"regexp_replace({c}, '\b\d{{3}}(\d{{6}})\d{{2}}\b', '***\1**', 'g')"},
    "politicos": {"politico_id": PID, "cpf": "''"},
    "receitas": {"politico_id": PID, "politico_cpf": "''", "doador_doc": CPF},
    "candidatos": {"cpf": "''", "pessoa": "substr(md5('" + SAL + "' || 'P-' || pessoa), 1, 14)"},
    "ids_externos": {"politico_id": PID},
    "sancoes": {"doc": CPF},
}


def token() -> str:
    import os
    if os.environ.get("HF_TOKEN"):
        return os.environ["HF_TOKEN"]
    if TOKEN_ARQ.exists():
        return TOKEN_ARQ.read_text().strip()
    print("\nCole aqui o token do Hugging Face (huggingface.co/settings/tokens → Create new token → tipo Write):")
    t = input("> ").strip()
    TOKEN_ARQ.write_text(t)
    return t


GH_ARQ = DADOS / ".gh_token"
IGNORAR_CODIGO = ("dados/", "__pycache__", "tests/", "deploy/", ".bat", ".zip", ".pyc")


def gh_token() -> str:
    import os
    if os.environ.get("GH_TOKEN"):
        return os.environ["GH_TOKEN"]
    if GH_ARQ.exists():
        return GH_ARQ.read_text().strip()
    print("\nCole aqui o token do GitHub (github.com/settings/tokens/new → marque 'public_repo' → Generate token):")
    t = input("> ").strip()
    GH_ARQ.write_text(t)
    return t


def enviar_github(repo_nome: str) -> str:
    """Cria (se preciso) o repositório público e envia o código do app. Retorna 'usuario/repo'."""
    import base64
    import requests
    h = {"Authorization": f"token {gh_token()}", "Accept": "application/vnd.github+json"}
    api = "https://api.github.com"
    r = requests.get(f"{api}/user", headers=h, timeout=30)
    if r.status_code != 200:
        GH_ARQ.unlink(missing_ok=True)
        sys.exit(f"Token do GitHub recusado ({r.status_code}). Rode de novo e cole um token válido.")
    dono = r.json()["login"]
    repo = f"{dono}/{repo_nome}"
    if requests.get(f"{api}/repos/{repo}", headers=h, timeout=30).status_code == 404:
        r = requests.post(f"{api}/user/repos", headers=h, timeout=30,
                          json={"name": repo_nome, "private": False, "auto_init": True,
                                "description": "Radar de Gastos — fiscalização cidadã de gastos de políticos"})
        r.raise_for_status()
    arquivos = [p for p in RAIZ.rglob("*") if p.is_file()
                and not any(x in p.relative_to(RAIZ).as_posix() for x in IGNORAR_CODIGO)]
    for p in arquivos:
        rel = p.relative_to(RAIZ).as_posix()
        url = f"{api}/repos/{repo}/contents/{rel}"
        atual = requests.get(url, headers=h, timeout=30)
        corpo = {"message": f"atualiza {rel}", "content": base64.b64encode(p.read_bytes()).decode()}
        if atual.status_code == 200:
            if atual.json().get("content", "").replace("\n", "") == corpo["content"]:
                continue
            corpo["sha"] = atual.json()["sha"]
        requests.put(url, headers=h, json=corpo, timeout=60).raise_for_status()
        print(f"   {rel}")
    return repo


def banco_publico():
    print("1/4 Criando a cópia pública do banco (CPFs ocultos)...")
    if PUB.exists():
        shutil.rmtree(PUB)
    PUB.mkdir(parents=True)
    dst = duckdb.connect(str(PUB / "radar.duckdb"))
    dst.execute(f"ATTACH '{(DADOS / 'radar.duckdb').as_posix()}' AS o (READ_ONLY)")
    tabelas = [r[0] for r in dst.execute("SELECT table_name FROM information_schema.tables WHERE table_catalog='o'").fetchall()]
    for t in tabelas:
        cols = [r[0] for r in dst.execute(f"SELECT column_name FROM information_schema.columns WHERE table_catalog='o' AND table_name='{t}' ORDER BY ordinal_position").fetchall()]
        regras = TRANSFORMA.get(t, {})
        sel = ", ".join((f"{regras[c].format(c=c)} AS {c}" if c in regras else c) for c in cols)
        dst.execute(f"CREATE TABLE {t} AS SELECT {sel} FROM o.{t}")
        print(f"   {t}: {dst.execute(f'SELECT count(*) FROM {t}').fetchone()[0]:,}".replace(",", "."))
    dst.execute("DETACH o")
    dst.close()
    (PUB / "atualizado_em.txt").write_text(dt.datetime.now().strftime("%d/%m/%Y %H:%M"), encoding="utf-8")
    for sub in ("receita", "siconfi", "perfis"):
        if (DADOS / "bruto" / sub).exists():
            shutil.copytree(DADOS / "bruto" / sub, PUB / "bruto" / sub, ignore=shutil.ignore_patterns("*.part"))


def fichas():
    print("2/4 Pré-carregando fichas de deputados e senadores (foto, contatos, redes)...")
    import perfil_ui as pf
    con = duckdb.connect(str(DADOS / "radar.duckdb"), read_only=True)
    try:
        ids = [r[0] for r in con.execute("SELECT DISTINCT id_origem FROM ids_externos").fetchall()]
    except Exception:  # noqa: BLE001
        ids = []
    con.close()

    def um(i):
        try:
            if i.startswith("CD-") and i[3:].isdigit():
                d = i[3:]
                js = pf._get_json(f"{pf.CAMARA}/deputados/{d}", f"cd_{d}")
                pf._get_json(f"{pf.CAMARA}/deputados/{d}/historico", f"cd_hist_{d}")
                pf._get_json(f"{pf.CAMARA}/deputados/{d}/mandatosExternos", f"cd_ext_{d}")
                pf._foto_ok(((js or {}).get("dados", {}).get("ultimoStatus") or {}).get("urlFoto"))
            elif i.startswith("SF-") and i[3:].isdigit():
                c = i[3:]
                js = pf._get_json(f"{pf.SENADO}/senador/{c}.json", f"sf_{c}")
                pf._get_json(f"{pf.SENADO}/senador/{c}/mandatos.json", f"sf_mand_{c}")
                pf._foto_ok((pf._achar(js, "IdentificacaoParlamentar") or {}).get("UrlFotoParlamentar"))
        except Exception:  # noqa: BLE001
            pass
    with ThreadPoolExecutor(8) as ex:
        list(ex.map(um, ids))
    pf._get_json(f"{pf.SENADO}/senador/lista/atual.json", "sf_lista_atual", 7)
    print(f"   {len(ids)} fichas prontas")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--nome", default="radar-de-gastos", help="nome do Space")
    ap.add_argument("--sem-fichas", action="store_true")
    ap.add_argument("--destino", choices=["streamlit", "hf"], default="streamlit",
                    help="streamlit = grátis (Streamlit Cloud + GitHub); hf = Space do Hugging Face (exige PRO)")
    a = ap.parse_args()
    if not (DADOS / "radar.duckdb").exists():
        sys.exit("Não achei dados\\radar.duckdb. Rode o Atualizar Radar primeiro.")
    from huggingface_hub import HfApi
    api = HfApi(token=token())
    user = api.whoami()["name"]
    space, dataset = f"{user}/{a.nome}", f"{user}/{a.nome}-dados"

    if not a.sem_fichas:
        fichas()
    banco_publico()

    print(f"3/4 Enviando os dados para {dataset} (pode levar alguns minutos)...")
    api.create_repo(dataset, repo_type="dataset", exist_ok=True)
    # tudo em 3 arquivos (o site baixa rápido e sem bater no limite de requisições do Hugging Face)
    if (PUB / "bruto").exists():
        shutil.make_archive(str(PUB / "bruto"), "zip", root_dir=str(PUB / "bruto"))
    from huggingface_hub import CommitOperationAdd, CommitOperationDelete
    ops = [CommitOperationAdd(path_in_repo=n, path_or_fileobj=str(PUB / n))
           for n in ("radar.duckdb", "atualizado_em.txt", "bruto.zip") if (PUB / n).exists()]
    antigos = [f for f in api.list_repo_files(dataset, repo_type="dataset") if f.startswith("bruto/")]
    ops += [CommitOperationDelete(path_in_repo=f) for f in antigos]
    api.create_commit(dataset, repo_type="dataset", operations=ops,
                      commit_message=f"dados {dt.date.today():%d/%m/%Y}")

    if a.destino == "streamlit":
        print("4/4 Enviando o código do app para o GitHub...")
        repo = enviar_github(a.nome)
        print("\n✅ Dados e código enviados!")
        print(f"   Código:  https://github.com/{repo}")
        print("\nSe for a 1ª vez, faça o deploy (só uma vez):")
        print("   1. Abra https://share.streamlit.io e entre com a conta do GitHub")
        print("   2. Create app → Deploy a public app from GitHub")
        print(f"   3. Repository: {repo}   Branch: main   Main file path: app.py")
        print(f"   4. App URL: escolha o nome (ex.: radar-de-gastos)")
        print("   5. Advanced settings → Python 3.12 → em Secrets cole as 2 linhas abaixo → Save → Deploy:")
        print('        RADAR_PUBLICO = "1"')
        print(f'        RADAR_DATASET = "{dataset}"')
        print("\nNas próximas atualizações o site pega os dados novos sozinho após reiniciar")
        print("(no painel do Streamlit: ⋮ → Reboot app).")
        return
    print(f"4/4 Enviando o app para o Space {space}...")
    api.create_repo(space, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(folder_path=str(RAIZ), repo_id=space, repo_type="space", commit_message="app",
                      ignore_patterns=["dados/**", "**/__pycache__/**", "*.bat", "tests/**", "README.md", "deploy/**", "*.zip"])
    api.upload_file(path_or_fileobj=str(RAIZ / "deploy" / "Dockerfile"), path_in_repo="Dockerfile", repo_id=space, repo_type="space")
    api.upload_file(path_or_fileobj=str(RAIZ / "deploy" / "README_space.md"), path_in_repo="README.md", repo_id=space, repo_type="space")
    api.add_space_variable(space, "RADAR_DATASET", dataset)
    api.add_space_variable(space, "RADAR_PUBLICO", "1")
    try:
        api.restart_space(space)
    except Exception:  # noqa: BLE001
        pass
    print("\n✅ Publicado! Em 3 a 5 minutos o app estará no ar em:")
    print(f"   https://huggingface.co/spaces/{space}")
    print(f"   link direto (melhor para compartilhar): https://{user.lower()}-{a.nome}.hf.space")


if __name__ == "__main__":
    main()
