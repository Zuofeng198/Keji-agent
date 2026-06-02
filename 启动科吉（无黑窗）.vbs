' 科吉 AI 助手 — 无控制台窗口启动器
' 双击此文件以静默启动桌面应用

Dim shell, fso, currentDir, exePath, batPath

Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

' 优先尝试打包后的 exe
exePath = currentDir & "\dist\科吉AI助手.exe"
If fso.FileExists(exePath) Then
    CreateObject("WScript.Shell").Run """" & exePath & """", 0, False
    WScript.Quit
End If

' 回退到 bat 启动器（隐藏窗口）
batPath = currentDir & "\启动科吉.bat"
If fso.FileExists(batPath) Then
    CreateObject("WScript.Shell").Run "cmd.exe /c """ & batPath & """", 0, False
    WScript.Quit
End If

' 最后的回退：直接运行 desktop.py
pythonPath = currentDir & "\venv\Scripts\python.exe"
If fso.FileExists(pythonPath) Then
    CreateObject("WScript.Shell").Run """" & pythonPath & """ """ & currentDir & "\desktop.py"" --mode desktop", 0, False
    WScript.Quit
End If

MsgBox "未找到可执行文件，请先运行 build.bat 构建项目。", vbExclamation, "科吉 AI 助手"
