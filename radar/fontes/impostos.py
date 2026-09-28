"""Arrecadação federal mês a mês, por tributo e por UF (Receita Federal, dados abertos).

Fonte: https://www.gov.br/receitafederal/dados/arrecadacao-estado.csv
Valores em R$ correntes. Não inclui ICMS, ISS, IPVA, IPTU (estaduais/municipais) nem FGTS.
"""
from __future__ import annotations

import io
import time
import unicodedata

import pandas as pd
import requests

from radar.util import DADOS, UA

URL = "https://www.gov.br/receitafederal/dados/arrecadacao-estado.csv"
ARQ = DADOS / "bruto" / "receita" / "arrecadacao-estado.csv"

MESES = {m: i for i, m in enumerate(
    ["janeiro", "fevereiro", "marco", "abril", "maio", "junho", "julho",
     "agosto", "setembro", "outubro", "novembro", "dezembro"], 1)}

# grupo amigável -> colunas (a 1ª que tiver valor na linha vale; se a coluna "total"
# estiver vazia, soma as subcolunas — evita contar em dobro entre épocas do arquivo)
GRUPOS = {
    "Previdência (INSS)": ("RECEITA PREVIDENCIÁRIA", ["RECEITA PREVIDENCIÁRIA - PRÓPRIA", "RECEITA PREVIDENCIÁRIA - DEMAIS"]),
    "COFINS": ("COFINS", ["COFINS - FINANCEIRAS", "COFINS - DEMAIS"]),
    "IR de empresas (IRPJ)": (None, ["IRPJ - ENTIDADES FINANCEIRAS", "IRPJ - DEMAIS EMPRESAS"]),
    "IR sobre salários (retido)": (None, ["IRRF - RENDIMENTOS DO TRABALHO"]),
    "CSLL": ("CSLL", ["CSLL - FINANCEIRAS", "CSLL - DEMAIS"]),
    "IR sobre aplicações (retido)": (None, ["IRRF - RENDIMENTOS DO CAPITAL"]),
    "PIS/PASEP": ("CONTRIBUIÇÃO PARA O PIS/PASEP", ["CONTRIBUIÇÃO PARA O PIS/PASEP - FINANCEIRAS", "CONTRIBUIÇÃO PARA O PIS/PASEP - DEMAIS"]),
    "IPI": (None, ["IPI - FUMO", "IPI - BEBIDAS", "IPI - AUTOMÓVEIS", "IPI - VINCULADO À IMPORTACAO", "IPI - OUTROS"]),
    "Simples Nacional": (None, ["PAGAMENTO UNIFICADO"]),
    "IOF": (None, ["IMPOSTO S/ OPERAÇÕES FINANCEIRAS"]),
    "Imposto de Importação": (None, ["IMPOSTO SOBRE IMPORTAÇÃO"]),
    "IR pessoa física (declaração)": (None, ["IRPF"]),
    "IR remessas ao exterior": (None, ["IRRF - REMESSAS P/ EXTERIOR"]),
    "IR retido (outros)": (None, ["IRRF - OUTROS RENDIMENTOS", "RETENÇÃO NA FONTE - LEI 10.833, Art. 30"]),
    "Previdência dos servidores": ("CONTRIBUIÇÃO PLANO SEG. SOC. SERVIDORES", ["CPSSS - Contrib. p/ o Plano de Segurid. Social Serv. Público"]),
    "CIDE-Combustíveis": ("CIDE-COMBUSTÍVEIS", ["CIDE-COMBUSTÍVEIS (parc. não dedutível)"]),
    "ITR (terra rural)": (None, ["IMPOSTO TERRITORIAL RURAL"]),
    "Imposto de Exportação": (None, ["IMPOSTO SOBRE EXPORTAÇÃO"]),
    "CPMF (extinta)": (None, ["CPMF", "IMPOSTO PROVIS.S/ MOVIMENT. FINANC. - IPMF"]),
    "Outras receitas": (None, ["OUTRAS RECEITAS ADMINISTRADAS", "DEMAIS RECEITAS", "REFIS", "PAES",
                               "CONTRIBUICÕES PARA FUNDAF", "ADMINISTRADAS POR OUTROS ÓRGÃOS"]),
}


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", str(s)) if not unicodedata.combining(c)).strip().lower()


def _num(s: pd.Series) -> pd.Series:
    s = s.astype(str).str.strip().replace({"": None, "nan": None, "-": None})
    tem_virg = s.str.contains(",", na=False)
    s = s.where(~tem_virg, s.str.replace(".", "", regex=False).str.replace(",", ".", regex=False))
    s = s.where(tem_virg | (s.str.count(r"\.") <= 1), s.str.replace(".", "", regex=False))
    return pd.to_numeric(s, errors="coerce").fillna(0.0)


def baixar(forcar: bool = False, max_dias: int = 7) -> bool:
    """Baixa o CSV da Receita (cache de 7 dias). Retorna True se há arquivo local."""
    if ARQ.exists() and not forcar and time.time() - ARQ.stat().st_mtime < max_dias * 86400:
        return True
    try:
        r = requests.get(URL, headers=UA, timeout=120)
        r.raise_for_status()
        ARQ.parent.mkdir(parents=True, exist_ok=True)
        tmp = ARQ.with_suffix(".part")
        tmp.write_bytes(r.content)
        tmp.replace(ARQ)
        return True
    except Exception as e:  # sem internet: usa o que tiver
        print(f"  arrecadação: falha ao baixar ({e})")
        return ARQ.exists()


def carregar() -> pd.DataFrame:
    """Tabela longa: data (1º dia do mês), uf, tributo, valor."""
    bruto = ARQ.read_bytes()
    for enc in ("utf-8-sig", "latin-1"):
        try:
            txt = bruto.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    df = pd.read_csv(io.StringIO(txt), sep=";", dtype=str, keep_default_na=False)
    df.columns = [c.strip() for c in df.columns]
    # casa nomes de coluna ignorando acento/caixa
    idx = {_sem_acento(c): c for c in df.columns}
    col = lambda nome: idx.get(_sem_acento(nome)) if nome else None

    ano = pd.to_numeric(df[col("Ano")], errors="coerce")
    mes = df[col("Mês")].map(lambda m: MESES.get(_sem_acento(m)) or pd.to_numeric(m, errors="coerce"))
    base = pd.DataFrame({"data": pd.to_datetime(dict(year=ano, month=mes, day=1), errors="coerce"),
                         "uf": df[col("UF")].str.strip().str.upper()})
    partes = []
    for nome, (total, subs) in GRUPOS.items():
        v_sub = sum((_num(df[c]) for c in map(col, subs) if c), pd.Series(0.0, index=df.index))
        c_tot = col(total)
        v = _num(df[c_tot]).where(lambda x: x > 0, v_sub) if c_tot else v_sub
        partes.append(base.assign(tributo=nome, valor=v))
    out = pd.concat(partes, ignore_index=True)
    out = out[out["data"].notna() & (out["valor"] != 0)]
    return out


def ritmo(df: pd.DataFrame, agora: pd.Timestamp | None = None) -> dict:
    """Base do impostômetro: acumulado oficial do ano + estimativa até agora pelo ritmo dos últimos 12 meses."""
    agora = agora or pd.Timestamp.now()
    ultimo = df["data"].max()                      # último mês publicado
    fim_ult = ultimo + pd.offsets.MonthBegin(1)    # 1º dia do mês seguinte
    ini12 = ultimo - pd.DateOffset(months=11)
    ult12 = df[df["data"] >= ini12]["valor"].sum()
    seg12 = (fim_ult - ini12).total_seconds()
    # ajusta pelo crescimento: compara os 12 meses com os 12 anteriores
    ant = df[(df["data"] >= ini12 - pd.DateOffset(months=12)) & (df["data"] < ini12)]["valor"].sum()
    cresc = (ult12 / ant) if ant > 0 else 1.0
    cresc = min(max(cresc, 0.8), 1.3)
    por_seg = ult12 / seg12 * cresc ** 0.5         # meio ano de crescimento à frente
    inicio_ano = pd.Timestamp(agora.year, 1, 1)
    oficial_ano = df[df["data"] >= inicio_ano]["valor"].sum()
    base_ts = max(fim_ult, inicio_ano)
    return {
        "por_segundo": float(por_seg),
        "oficial_ano": float(oficial_ano),
        "base_ts": base_ts,                        # a estimativa corre a partir daqui
        "ultimo_mes": ultimo,
        "ult12": float(ult12),
        "crescimento": float(cresc),
        "ano": agora.year,
    }


# ---------------------------------------------------------------------------
# Recolhimentos DIA A DIA (Tesouro Gerencial → Portal da Transparência, atualização diária)
# ---------------------------------------------------------------------------
URLS_DIA = [
    "https://dadosabertos-download.cgu.gov.br/PortalDaTransparencia/saida/receitas/{ano}_Receitas.zip",
    "https://portaldatransparencia.gov.br/download-de-dados/receitas/{ano}",
]
PASTA_DIA = DADOS / "bruto" / "receita"


def arq_dia(ano: int):
    return PASTA_DIA / f"{ano}_Receitas.zip"


def baixar_diario(ano: int, max_horas: float = 3, forcar: bool = False) -> bool:
    """Baixa o arquivo de receitas do ano. O ano corrente é renovado a cada `max_horas`."""
    import datetime as _dt
    arq = arq_dia(ano)
    corrente = ano == _dt.date.today().year
    if arq.exists() and not forcar and (not corrente or time.time() - arq.stat().st_mtime < max_horas * 3600):
        return True
    for url in URLS_DIA:
        try:
            r = requests.get(url.format(ano=ano), headers=UA, timeout=180)
            if r.status_code != 200 or r.content[:2] != b"PK":
                print(f"  receitas {ano}: [{r.status_code}] {url.format(ano=ano)}")
                continue
            PASTA_DIA.mkdir(parents=True, exist_ok=True)
            tmp = arq.with_suffix(".part")
            tmp.write_bytes(r.content)
            tmp.replace(arq)
            return True
        except Exception as e:  # noqa: BLE001
            print(f"  receitas {ano}: falha {e}")
    return arq.exists()


def _acha(cols, *chaves, evita=()):
    for c in cols:
        n = _sem_acento(c)
        if all(k in n for k in chaves) and not any(e in n for e in evita):
            return c
    return None


def carregar_diario(anos) -> pd.DataFrame:
    """Recolhimentos de impostos e contribuições da União por dia: data, especie, detalhe, valor."""
    import zipfile
    from radar.util import ler_csv
    partes = []
    for ano in anos:
        arq = arq_dia(ano)
        if not arq.exists():
            continue
        z = zipfile.ZipFile(arq)
        nome = next((n for n in z.namelist() if n.lower().endswith(".csv")), None)
        if not nome:
            continue
        cab = z.open(nome).readline()
        cab = cab.decode("utf-8-sig", errors="ignore") if cab[:3] == b"\xef\xbb\xbf" else cab.decode("latin-1")
        cols = [c.strip().strip('"') for c in cab.strip().split(";")]
        c_data = _acha(cols, "data")
        c_val = _acha(cols, "valor", "realizado")
        c_cat = _acha(cols, "categoria")
        c_ori = _acha(cols, "origem")
        c_esp = _acha(cols, "especie")
        c_det = _acha(cols, "detalhamento")
        if not (c_data and c_val and (c_ori or c_esp)):
            print(f"  receitas {ano}: colunas não reconhecidas: {cols}")
            continue
        use = [c for c in (c_data, c_val, c_cat, c_ori, c_esp, c_det) if c]

        def filtro(b, c_ori=c_ori, c_esp=c_esp, c_cat=c_cat):
            txt = (b[c_ori] if c_ori else b[c_esp]).fillna("").map(_sem_acento)
            ok = txt.str.contains("impost|contribui|tribut", regex=True)
            if c_cat:
                ok &= ~b[c_cat].fillna("").map(_sem_acento).str.contains("intra")
            return b[ok]

        df = ler_csv(lambda: z.open(nome), usecols=use, filtro=filtro)
        if df.empty:
            continue
        out = pd.DataFrame({
            "data": pd.to_datetime(df[c_data].str.strip(), dayfirst=True, errors="coerce"),
            "especie": (df[c_esp] if c_esp else df[c_ori]).fillna("").str.strip(),
            "detalhe": (df[c_det] if c_det else df[c_esp] if c_esp else df[c_ori]).fillna("").str.strip(),
            "valor": _num(df[c_val]),
        })
        partes.append(out[out["data"].notna()])
    if not partes:
        return pd.DataFrame(columns=["data", "especie", "detalhe", "valor"])
    d = pd.concat(partes, ignore_index=True)
    d["data"] = d["data"].dt.normalize()
    return d.groupby(["data", "especie", "detalhe"], as_index=False)["valor"].sum()


def ritmo_diario(d: pd.DataFrame, agora: pd.Timestamp | None = None) -> dict | None:
    """Acumulado REAL do ano até o último dia publicado + estimativa só dos dias que faltam publicar."""
    agora = agora or pd.Timestamp.now()
    if d.empty:
        return None
    por_dia = d.groupby("data")["valor"].sum()
    por_dia = por_dia[por_dia.index <= agora.normalize()]
    ano = por_dia[por_dia.index.year == agora.year]
    if ano.index.nunique() < 5:          # arquivo não é diário ou ainda vazio: usa o mensal
        return None
    ultimo = ano.index.max()
    janela = por_dia[por_dia.index > ultimo - pd.Timedelta(days=90)]
    por_seg = janela.sum() / (90 * 86400)
    return {
        "por_segundo": float(por_seg),
        "oficial_ano": float(ano.sum()),
        "base_ts": ultimo + pd.Timedelta(days=1),
        "ultimo_dia": ultimo,
        "ult_dia_valor": float(ano.loc[ultimo]),
        "ano": agora.year,
        "por_dia": por_dia,
    }


# ---------------------------------------------------------------------------
# Tributos sem série mensal aberta: base anual oficial + crescimento
# ---------------------------------------------------------------------------
# Municipais: Tesouro Nacional, Estimativa da Carga Tributária Bruta do Governo Geral 2024 (Tabela 3).
# FGTS: arrecadação bruta 2025 divulgada pelo Conselho Curador do FGTS (fgts.gov.br).
ESTIMADOS = {
    # nome: (ano base, valor R$, esfera)
    "ISS": (2024, 136_618e6, "Municipal"),
    "IPTU": (2024, 70_033e6, "Municipal"),
    "ITBI": (2024, 24_364e6, "Municipal"),
    "Outros municipais (taxas e contribuições)": (2024, (282_203 - 136_618 - 70_033 - 24_364) * 1e6, "Municipal"),
    "FGTS": (2025, 212_600e6, "FGTS"),
}
FONTE_ESTIMADOS = ("Municipais: Tesouro Nacional, Carga Tributária do Governo Geral 2024. "
                   "FGTS: arrecadação bruta 2025 (R$ 212,6 bi), Conselho Curador do FGTS.")


def estimado_anual(nome: str, ano: int, cresc: float) -> float:
    ano_b, v, _ = ESTIMADOS[nome]
    return v * cresc ** (ano - ano_b)
