"""Coletores de dados oficiais. Cada um devolve um DataFrame no esquema unificado GASTOS."""

GASTOS = [
    "id", "fonte", "cargo", "politico_id", "politico_cpf", "politico_nome", "partido", "uf",
    "municipio", "data", "ano", "mes", "categoria", "fornecedor", "fornecedor_doc",
    "documento", "valor", "url_doc", "descricao",
]


def padronizar(df):
    """Garante todas as colunas do esquema (as que a fonte não tem ficam vazias)."""
    return df.reindex(columns=GASTOS, fill_value="")
