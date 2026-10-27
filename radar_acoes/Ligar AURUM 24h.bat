@echo off
REM Liga a equipe AURUM em segundo plano (sem janela) e faz ela iniciar junto com o Windows.
cd /d "%~dp0"
python segundo_plano.py ligar
pause
