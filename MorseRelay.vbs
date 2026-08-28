Set WshShell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")

' Get the directory this script is running from
strDir = Fso.GetParentFolderName(WScript.ScriptFullName)

' Change directory to the app folder, then run pythonw main.py silently
' pythonw.exe runs python without a console window
WshShell.CurrentDirectory = strDir
WshShell.Run "pythonw main.py", 0, False

Set WshShell = Nothing
Set Fso = Nothing