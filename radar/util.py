"""Utilitários comuns: download com cache, leitura tolerante de CSV, validação de CPF/CNPJ."""
from __future__ import annotations

import io
import re
import time
import zipfile
from pathlib import Path

import pandas as pd
import requests

DADOS = Path(__file__).resolve().parent.parent / "dados"
BRUTO = DADOS / "bruto"
BRUTO.mkdir(parents=True, exist_ok=True)

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0 Safari/537.36 RadarGastos/1.0",
      "Accept": "*/*", "Accept-Language": "pt-BR,pt;q=0.9"}


def baixar(url: str, destino: Path, forcar: bool = False, tentativas: int = 3) -> Path | None:
    """Baixa um arquivo com cache local. Retorna None se não existir (404)."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    if destino.exists() and destino.stat().st_size > 0 and not forcar:
        return destino
    for i in range(tentativas):
        try:
            with requests.get(url, headers=UA, stream=True, timeout=120) as r:
                if r.status_code in (403, 404):
                    print(f"  [{r.status_code}] {url}")
                    return None
                r.raise_for_status()
                tmp = destino.with_suffix(destino.suffix + ".part")
                total = 0
                with open(tmp, "wb") as f:
                    for bloco in r.iter_content(1 << 20):
                        f.write(bloco)
                        total += len(bloco)
                tmp.rename(destino)
                print(f"  baixado {destino.name} ({total/1e6:.1f} MB)")
                return destino
        except requests.RequestException as e:
            print(f"  falha ({i+1}/{tentativas}) {url}: {e}")
            time.sleep(3 * (i + 1))
    return None


def ler_csv(fonte, sep=";", encoding="utf-8", filtro=None, usecols=None, **kw) -> pd.DataFrame:
    """Lê CSV como texto (dtype=str), tentando encodings comuns do governo.

    `fonte` pode ser caminho, BytesIO ou uma função que abre o arquivo (streaming, sem
    carregar tudo na memória). `filtro(df_pedaco) -> df_pedaco` é aplicado a cada bloco de
    200 mil linhas, para arquivos gigantes (TSE) caberem em qualquer computador.
    """
    cols = None
    if usecols:
        alvo = set(usecols)
        cols = lambda c: c in alvo
    for enc in (encoding, "utf-8-sig", "latin-1"):
        try:
            f = fonte() if callable(fonte) else fonte
            if hasattr(f, "seek"):
                try:
                    f.seek(0)
                except Exception:  # noqa: BLE001
                    pass
            leitor = pd.read_csv(f, sep=sep, dtype=str, encoding=enc, on_bad_lines="skip",
                                 low_memory=True, usecols=cols, chunksize=200_000, **kw)
            partes = [(filtro(b) if filtro else b) for b in leitor]
            partes = [b for b in partes if len(b)]
            return pd.concat(partes, ignore_index=True) if partes else pd.DataFrame()
        except UnicodeDecodeError:
            continue
    raise ValueError(f"não consegui ler {fonte}")


def csvs_do_zip(caminho: Path, padrao: str):
    """Lista (nome, abridor) dos CSVs do zip cujo nome casa com o regex.
    Não lê nada ainda: o arquivo só é aberto (em streaming) quando `abridor()` é chamado."""
    z = zipfile.ZipFile(caminho)
    saida = []
    for nome in z.namelist():
        if re.search(padrao, nome, re.I):
            saida.append((nome, (lambda n=nome: z.open(n))))
    return saida


def so_digitos(s) -> str:
    return re.sub(r"\D", "", str(s)) if isinstance(s, str) else ""


def valor_br(serie: pd.Series) -> pd.Series:
    """Converte '1.234,56' ou '1234.56' em float."""
    s = serie.fillna("").astype(str).str.strip()
    tem_virgula = s.str.contains(",", regex=False)
    s = s.where(~tem_virgula, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def _dv(digs: str, pesos: list[int]) -> int:
    r = sum(int(d) * p for d, p in zip(digs, pesos)) % 11
    return 0 if r < 2 else 11 - r


def cpf_valido(c: str) -> bool:
    if len(c) != 11 or c == c[0] * 11:
        return False
    d1 = _dv(c[:9], list(range(10, 1, -1)))
    d2 = _dv(c[:9] + str(d1), list(range(11, 1, -1)))
    return c[-2:] == f"{d1}{d2}"


def cnpj_valido(c: str) -> bool:
    if len(c) != 14 or c == c[0] * 14:
        return False
    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = _dv(c[:12], p1)
    d2 = _dv(c[:12] + str(d1), [6] + p1)
    return c[-2:] == f"{d1}{d2}"


def doc_valido(d: str) -> bool | None:
    """True/False para CPF/CNPJ; None quando não se aplica (vazio, exterior, mascarado)."""
    if not d or len(d) not in (11, 14):
        return None
    return cpf_valido(d) if len(d) == 11 else cnpj_valido(d)


def col(df: pd.DataFrame, *candidatos: str) -> str | None:
    """Acha a primeira coluna existente (ignorando caixa/acentos simples)."""
    norm = {re.sub(r"[^a-z0-9]", "", c.lower()): c for c in df.columns}
    for c in candidatos:
        k = re.sub(r"[^a-z0-9]", "", c.lower())
        if k in norm:
            return norm[k]
    return None


def normaliza_doc(d: str) -> str:
    """Recupera zeros à esquerda perdidos (planilhas do governo às vezes gravam CPF/CNPJ como número)."""
    d = so_digitos(d) if not (isinstance(d, str) and d.isdigit()) else d
    # códigos de preenchimento (ex.: 00000000000001 em telefonia) não são documentos
    if not d or len(d.lstrip("0")) < 6:
        return ""
    if len(d) in (12, 13):
        return d.zfill(14)
    if len(d) == 11:
        if cpf_valido(d):
            return d
        return d.zfill(14) if cnpj_valido(d.zfill(14)) else d
    if len(d) < 11:
        if cpf_valido(d.zfill(11)):
            return d.zfill(11)
        if cnpj_valido(d.zfill(14)):
            return d.zfill(14)
    return d


def norm_nome(t) -> str:
    import unicodedata
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode()
    return " ".join(t.upper().split())


def chave_pessoa(cpf: str, nome: str, nasc: str = "") -> str:
    """CPF quando válido; senão nome + nascimento (o TSE mascara CPFs em algumas bases)."""
    import hashlib
    if cpf and len(cpf) == 11 and cpf_valido(cpf):
        return cpf
    base = norm_nome(nome) + "|" + str(nasc or "")
    return "N" + hashlib.md5(base.encode()).hexdigest()[:12]


def data_br(serie: pd.Series) -> pd.Series:
    """Converte datas de qualquer fonte: ISO (2025-03-05, inclusive vinda do Excel) ou brasileira (05/03/2025).
    Datas impossíveis (ano 0023, 2049...) viram vazio em vez de quebrar."""
    s = serie.fillna("").astype(str).str.strip().str[:10]
    iso = s.str.match(r"^\d{4}-\d{2}-\d{2}$")
    partes = []
    for mask, kw in ((iso, {"format": "%Y-%m-%d"}), (~iso, {"dayfirst": True})):
        if mask.any():
            p = pd.to_datetime(s[mask], errors="coerce", **kw)
            ok = p.notna() & p.dt.year.between(1990, 2100)
            partes.append(pd.Series([x if o else pd.NaT for x, o in zip(p, ok)], index=p.index, dtype="object"))
    if not partes:
        return pd.Series(pd.NaT, index=serie.index, dtype="datetime64[ns]")
    return pd.to_datetime(pd.concat(partes).reindex(serie.index), errors="coerce")
