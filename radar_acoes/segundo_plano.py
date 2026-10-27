"""Liga/desliga a equipe AURUM em segundo plano no Windows (sem janela, inicia junto com o Windows).

    python segundo_plano.py ligar      (ou "Ligar AURUM 24h.bat")
    python segundo_plano.py desligar   (ou "Desligar AURUM 24h.bat")
    python segundo_plano.py status

Usa a pasta "Inicializar" do seu usuário — não precisa de administrador. Com o computador ligado (mesmo sem o painel
aberto), a equipe trabalha. Com o computador desligado, quem cobre é o GitHub Actions (veja o README).
"""
from __future__ import annotations

import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
AGENTE = RAIZ / "agente.py"
DADOS = RAIZ / "dados_acoes"
NOME_ATALHO = "AURUM equipe.vbs"


def pasta_inicializar() -> Path:
    return Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"


def pythonw() -> str:
    p = Path(sys.executable)
    cand = p.with_name("pythonw.exe")
    return str(cand if cand.exists() else p)


def ligada() -> tuple[bool, str]:
    try:
        vivo = datetime.fromisoformat((DADOS / "agente_vivo.txt").read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        return False, "nunca ligada"
    minutos = (datetime.now() - vivo).total_seconds() / 60
    return minutos < 12, f"último sinal de vida há {minutos:.0f} min"


def ligar() -> str:
    if os.name != "nt":
        return "Fora do Windows: use  nohup python agente.py &  ou um agendador (cron/systemd)."
    vbs = pasta_inicializar() / NOME_ATALHO
    vbs.parent.mkdir(parents=True, exist_ok=True)
    cmd = f'""{pythonw()}"" ""{AGENTE}""'
    vbs.write_text(f'Set s = CreateObject("WScript.Shell")\r\ns.CurrentDirectory = "{RAIZ}"\r\n'
                   f's.Environment("PROCESS")("AURUM_OCULTO") = "1"\r\ns.Run "{cmd}", 0, False\r\n', encoding="utf-16")  # UTF-16: o Windows lê certo caminhos com acento (ex.: C:\\Users\\João)
    if not ligada()[0]:
        env = {**os.environ, "AURUM_OCULTO": "1"}
        subprocess.Popen([pythonw(), str(AGENTE)], cwd=RAIZ, env=env,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0),
                         close_fds=True)
    return ("✅ Equipe ligada em segundo plano. Ela também liga sozinha sempre que o Windows iniciar.\n"
            f"   (atalho criado em: {vbs})")


def desligar() -> str:
    msgs = []
    if os.name == "nt":
        vbs = pasta_inicializar() / NOME_ATALHO
        if vbs.exists():
            vbs.unlink()
            msgs.append("✅ Não liga mais sozinha com o Windows.")
        try:
            pid = int((DADOS / "agente.pid").read_text().strip())
            parou = False
            for img in ("pythonw.exe", "python.exe"):  # só encerra se o processo for mesmo o Python (o número pode ter sido reusado)
                r = subprocess.run(["taskkill", "/F", "/FI", f"PID eq {pid}", "/FI", f"IMAGENAME eq {img}"], capture_output=True, text=True)
                saida = (r.stdout or "").upper()
                parou |= r.returncode == 0 and ("SUCCESS" in saida or "ÊXITO" in saida or "XITO" in saida)
            (DADOS / "agente.pid").unlink(missing_ok=True)
            (DADOS / "agente_vivo.txt").unlink(missing_ok=True)
            msgs.append("✅ Equipe parada agora." if parou else "A equipe já estava parada.")
        except (FileNotFoundError, ValueError):
            msgs.append("A equipe já estava parada.")
    else:
        msgs.append("Fora do Windows: pare o processo do agente.py manualmente.")
    return "\n".join(msgs)


if __name__ == "__main__":
    acao = (sys.argv[1] if len(sys.argv) > 1 else "status").lower()
    if acao == "ligar":
        print(ligar())
    elif acao == "desligar":
        print(desligar())
    else:
        ok, txt = ligada()
        print(("🟢 Equipe trabalhando" if ok else "⚪ Equipe parada") + f" ({txt}).")
