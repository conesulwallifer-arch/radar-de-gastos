"""Radar de Ações: ranking de ações para renda (dividendos/JCP), notícias, previsões e alertas diários."""
import os
import sys
import time
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

# No Windows, quando a saída vai para arquivo (painel sem janela, agendador), o padrão é cp1252, que não
# sabe escrever emojis: um simples print("🔮 ...") derrubava a apuração. Força UTF-8 e, se mesmo assim
# algum caractere não couber, troca por "?" em vez de quebrar.
for _fluxo in (sys.stdout, sys.stderr):
    try:
        _fluxo.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # sem console (pythonw) ou fluxo que não aceita reconfigurar
        pass

RAIZ = Path(__file__).resolve().parent.parent
DADOS = RAIZ / "dados_acoes"
DADOS.mkdir(parents=True, exist_ok=True)

AVISO = ("Ferramenta educacional. Não é recomendação de investimento: previsões são estimativas estatísticas "
         "com base no passado, e o passado não garante o futuro. Confira os dados no RI da empresa antes de investir.")

FUSO = ZoneInfo("America/Sao_Paulo")


def hoje_brt() -> date:
    """Data de hoje no horário de Brasília (o relógio do Windows pode estar em outro fuso)."""
    return datetime.now(FUSO).date()


def carregar_config() -> None:
    """Lê radar_acoes/config.env para as variáveis de ambiente. Valores vazios não "travam" a chave:
    se você preencher depois, a próxima leitura já pega (o processo 24h roda por semanas)."""
    arq = RAIZ / "config.env"
    try:
        linhas = arq.read_text(encoding="utf-8-sig").splitlines()  # -sig: aceita arquivo salvo com BOM
    except OSError:
        return
    for linha in linhas:
        if "=" in linha and not linha.lstrip().startswith("#"):
            k, v = linha.split("=", 1)
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if k and v and not os.environ.get(k):
                os.environ[k] = v


carregar_config()  # já na importação: painel, apuração e equipe 24h enxergam a chave da IA e o Telegram


def gravar_atomico(destino: Path, escrever) -> None:
    """Grava num arquivo temporário e troca de uma vez: quem lê nunca pega o arquivo pela metade, e uma queda de energia
    no meio não corrompe o original. `escrever(f)` recebe o arquivo aberto em modo binário."""
    destino.parent.mkdir(parents=True, exist_ok=True)
    tmp = destino.with_name(f"{destino.name}.{os.getpid()}.tmp")
    with open(tmp, "wb") as f:
        escrever(f)
        f.flush()
        os.fsync(f.fileno())
    for i in range(10):
        try:
            os.replace(tmp, destino)
            return
        except PermissionError:  # Windows: alguém está lendo o arquivo agora — espera um pouco
            time.sleep(0.2 * (i + 1))
    os.replace(tmp, destino)


def salvar_csv(df, destino: Path, **kw) -> None:
    gravar_atomico(destino, lambda f: f.write(df.to_csv(index=False, **kw).encode("utf-8")))


def travar(caminho: Path):
    """Trava entre processos (painel × equipe 24h). Devolve o arquivo travado ou None se outro já está com a trava."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    f = open(caminho, "a+")
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        f.close()
        return None
    return f


def destravar(f) -> None:
    if f is None:
        return
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass
    f.close()
