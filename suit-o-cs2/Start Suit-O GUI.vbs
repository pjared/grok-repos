' Start Suit-O's desktop window with pythonw so no console appears.
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
folder = fso.GetParentFolderName(WScript.ScriptFullName)
pythonw = folder & "\.venv\Scripts\pythonw.exe"
If Not fso.FileExists(pythonw) Then
    MsgBox "Could not find .venv\Scripts\pythonw.exe in " & folder & "." & vbCrLf & _
        "Create the virtual environment first. See README.md.", vbCritical, "Suit-O"
    WScript.Quit 1
End If
shell.CurrentDirectory = folder
shell.Run """" & pythonw & """ -m suit_o.gui", 0, False
