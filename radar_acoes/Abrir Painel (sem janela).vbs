' Abre o painel AURUM SEM janela preta: ele fica rodando escondido e o navegador abre em http://localhost:8501.
' Para desligar o painel, use "Fechar Painel.bat". Na PRIMEIRA vez use "Abrir Painel Acoes.bat" (instala os componentes).
Option Explicit
Dim sh, fso, pasta, i
Set sh = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
pasta = fso.GetParentFolderName(WScript.ScriptFullName)
sh.CurrentDirectory = pasta

Function PainelLigado()
  PainelLigado = (sh.Run("cmd /c netstat -ano | findstr "":8501 "" | findstr LISTENING >nul", 0, True) = 0)
End Function

If Not PainelLigado() Then
  If Not fso.FolderExists(pasta & "\dados_acoes") Then fso.CreateFolder(pasta & "\dados_acoes")
  sh.Run "cmd /c python -m streamlit run app.py --server.port 8501 --server.headless true > dados_acoes\painel.log 2>&1", 0, False
  For i = 1 To 40
    WScript.Sleep 1000
    If PainelLigado() Then Exit For
  Next
  If Not PainelLigado() Then
    MsgBox "O painel nao ligou. Abra uma vez pelo 'Abrir Painel Acoes.bat' para ver o erro (ou veja dados_acoes\painel.log).", 48, "AURUM"
    WScript.Quit 1
  End If
End If
sh.Run "http://localhost:8501"
