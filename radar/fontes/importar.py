"""Importa planilhas exportadas dos portais de transparência locais (prefeitura, câmara).

Coloque os arquivos (CSV, XLS ou XLSX) em  dados\\importar\\  e rode a coleta.
O NOME DO ARQUIVO diz de onde veio e o que é, por exemplo:
    prefeitura_pagamentos_2025.xlsx
    prefeitura_empenhos_2026.csv
    camara_pagamentos_2025.xls
    camara_diarias_2025.csv
- começa com "camara"  → Câmara Municipal;  qualquer outro → Prefeitura
- tem "diaria"          → diárias (o favorecido é a PESSOA que viajou)
As colunas são reconhecidas pelo nome (Data, Credor/Favorecido, CPF/CNPJ, Valor, Histórico...),
então funciona com exportações de sistemas diferentes (NEA, Betha, Fiorilli, IPM...).
"""
from __future__ import annotations

import re
import unicodedata
from pathlib import Path

import pandas as pd

from ..util import DADOS, normaliza_doc, valor_br
from . import GASTOS

PASTA = DADOS / "importar"

COLUNAS = {
    "data": ["data pagamento", "dt pagamento", "data do pagamento", "data empenho", "data de emissao", "data emissao",
             "data liquidacao", "data", "dt emissao", "emissao", "dt. pagamento", "data da despesa", "periodo"],
    "fornecedor": ["credor", "favorecido", "fornecedor", "nome do credor", "beneficiario", "razao social", "nome", "servidor"],
    "doc": ["cpf/cnpj", "cnpj/cpf", "cpf cnpj", "cnpj", "cpf", "documento do credor", "cpf/cnpj do credor", "cnpj/cpf credor"],
    "valor": ["valor pago", "vl pago", "valor liquido", "valor liquidado", "valor empenhado", "valor da diaria",
              "valor total", "valor", "vl. pago", "vlr pago", "total"],
    "documento": ["numero empenho", "nº empenho", "n empenho", "empenho", "numero", "nº", "documento", "processo"],
    "descricao": ["historico", "objeto", "descricao", "especificacao", "finalidade", "motivo", "destino", "elemento"],
    "categoria": ["elemento de despesa", "natureza da despesa", "natureza", "funcao", "acao", "programa", "unidade", "orgao"],
}


def _n(t) -> str:
    t = unicodedata.normalize("NFKD", str(t)).encode("ascii", "ignore").decode().lower()
    return " ".join(re.sub(r"[^a-z0-9/º ]", " ", t).split())


def _ler_bruto(arq: Path) -> pd.DataFrame:
    if arq.suffix.lower() in (".xls", ".xlsx"):
        return pd.read_excel(arq, header=None, dtype=str)
    for enc in ("utf-8-sig", "latin-1"):
        for sep in (";", ",", "\t"):
            try:
                df = pd.read_csv(arq, header=None, dtype=str, sep=sep, encoding=enc, on_bad_lines="skip")
                if df.shape[1] > 2:
                    return df
            except (UnicodeDecodeError, pd.errors.ParserError):
                continue
    return pd.DataFrame()


def _achar_cabecalho(bruto: pd.DataFrame) -> pd.DataFrame:
    """Portais costumam pôr título/filtros antes da tabela: acha a linha que tem 'valor' e um nome de credor."""
    for i in range(min(len(bruto), 40)):
        linha = [_n(x) for x in bruto.iloc[i].fillna("")]
        if any("valor" in c for c in linha) and any(any(k in c for k in ("credor", "favorecido", "fornecedor", "beneficiario", "nome")) for c in linha):
            df = bruto.iloc[i + 1:].copy()
            df.columns = [str(c) if str(c).strip() else f"col{j}" for j, c in enumerate(bruto.iloc[i].fillna(""))]
            return df.dropna(how="all")
    return pd.DataFrame()


def _mapear(cols) -> dict:
    nc = {c: _n(c) for c in cols}
    m = {}
    for campo, cands in COLUNAS.items():
        for cand in cands:
            achou = [c for c, n in nc.items() if n == cand] or [c for c, n in nc.items() if cand in n]
            achou = [c for c in achou if c not in m.values()]
            if achou:
                m[campo] = achou[0]
                break
    return m


def coletar(municipio: str, uf: str, cands: pd.DataFrame | None = None) -> pd.DataFrame:
    PASTA.mkdir(parents=True, exist_ok=True)
    arquivos = [a for a in PASTA.iterdir() if a.suffix.lower() in (".csv", ".xls", ".xlsx")]
    if not arquivos:
        print(f"  Importar: nenhuma planilha em {PASTA} (opcional)")
        return pd.DataFrame(columns=GASTOS)
    # pessoas eleitas do município (para ligar diárias ao vereador/prefeito)
    pessoas = {}
    if cands is not None and not cands.empty:
        loc = cands[(cands["municipio"].str.upper() == municipio.upper()) & cands["eleito"]]
        for r in loc.itertuples():
            pessoas[_n(r.nome)] = (f"P-{r.pessoa}", r.cargo, r.partido, r.cpf)
    partes = []
    for arq in arquivos:
        nome = _n(arq.stem)
        orgao = "CÂMARA MUNICIPAL DE " + municipio.upper() if nome.startswith("camara") else "PREFEITURA MUNICIPAL DE " + municipio.upper()
        tipo = "Diárias" if "diaria" in nome else ("Empenhos" if "empenho" in nome else ("Liquidações" if "liquida" in nome else "Pagamentos"))
        df = _achar_cabecalho(_ler_bruto(arq))
        m = _mapear(df.columns) if not df.empty else {}
        if "valor" not in m or "fornecedor" not in m:
            print(f"  Importar: não reconheci as colunas de {arq.name} — me mande o arquivo para eu ajustar")
            continue
        g = lambda k: df[m[k]].fillna("").astype(str).str.strip() if k in m else pd.Series([""] * len(df), index=df.index)
        out = pd.DataFrame({
            "fonte": f"{tipo} {'Câmara' if nome.startswith('camara') else 'Prefeitura'} (portal)",
            "cargo": "Órgão municipal",
            "politico_id": "ORGP-" + _n(orgao).replace(" ", "-"),
            "politico_cpf": "",
            "politico_nome": orgao,
            "partido": "", "uf": uf.upper(), "municipio": municipio.upper(),
            "data": pd.to_datetime(g("data").str[:10], dayfirst=True, errors="coerce"),
            "categoria": (tipo.upper() + " · " + g("categoria")).str.strip(" ·"),
            "fornecedor": g("fornecedor"),
            "fornecedor_doc": g("doc").map(normaliza_doc),
            "documento": g("documento"),
            "valor": valor_br(g("valor")),
            "url_doc": "",
            "descricao": g("descricao").str[:500],
        })
        out = out[(out["valor"] != 0) & (out["fornecedor"] != "") & ~out["fornecedor"].str.upper().str.startswith("TOTAL")]
        # diária (ou qualquer pagamento) cujo favorecido é um eleito → gasto na conta da pessoa
        hit = out["fornecedor"].map(lambda f: pessoas.get(_n(f)))
        for idx, h in hit.dropna().items():
            out.at[idx, "politico_id"], out.at[idx, "cargo"], out.at[idx, "partido"], out.at[idx, "politico_cpf"] = h
            out.at[idx, "politico_nome"] = out.at[idx, "fornecedor"]
        out["id"] = "IMP-" + _n(arq.stem).replace(" ", "_") + "-" + out.index.astype(str)
        print(f"  Importar: {arq.name}: {len(out)} lançamentos ({hit.notna().sum()} ligados a eleitos) · colunas {m}")
        partes.append(out)
    if not partes:
        return pd.DataFrame(columns=GASTOS)
    r = pd.concat(partes, ignore_index=True)
    r["ano"], r["mes"] = r["data"].dt.year, r["data"].dt.month
    return r.reindex(columns=GASTOS, fill_value="")
