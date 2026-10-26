@echo off
REM Desliga o painel AURUM que esta rodando escondido (porta 8501). Nao mexe na Equipe 24h.
set ACHOU=0
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8501 " ^| findstr LISTENING') do (
  taskkill /F /PID %%p >nul 2>&1
  set ACHOU=1
)
if "%ACHOU%"=="1" (echo Painel desligado.) else (echo O painel ja estava desligado.)
timeout /t 3 >nul
