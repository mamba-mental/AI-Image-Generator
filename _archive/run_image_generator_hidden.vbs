' AI Image Generator - Hidden Launcher
' This script runs the application without showing a command prompt window
' for a cleaner user experience

Option Explicit

' Declare variables
Dim shell, fso, currentDir, pythonCmd, outputDir, errorFile
Dim createPlaceholderCommand, pythonInstalled, exitCode

' Create file system and shell objects
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")

' Get the current directory of the script
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Change to the script directory to ensure relative paths work
shell.CurrentDirectory = currentDir

' Prepare paths
outputDir = currentDir & "\generated_images"
errorFile = currentDir & "\vbs_launcher_error.log"

' Check if Python is installed
On Error Resume Next
pythonInstalled = shell.Run("where python", 0, True)
On Error Goto 0

If pythonInstalled <> 0 Then
    WriteErrorLog "ERROR: Python is not found in your PATH. Please install Python 3.8+ and try again."
    WScript.Quit 1
End If

' Create output directory if it doesn't exist
If Not fso.FolderExists(outputDir) Then
    fso.CreateFolder(outputDir)
End If

' Create placeholder image if it doesn't exist
If Not fso.FileExists(currentDir & "\placeholder.png") Then
    ' Run the create_placeholder script
    createPlaceholderCommand = "python """ & currentDir & "\create_placeholder.py"""
    shell.Run createPlaceholderCommand, 0, True
End If

' Set environment for Hugging Face (if token exists in config)
SetEnvironmentVariablesFromConfig

' Archive previous log file if it exists
If fso.FileExists(currentDir & "\app_debug.log") Then
    On Error Resume Next
    If fso.FileExists(currentDir & "\app_debug_old.log") Then
        fso.DeleteFile currentDir & "\app_debug_old.log", True
    End If
    fso.MoveFile currentDir & "\app_debug.log", currentDir & "\app_debug_old.log"
    On Error Goto 0
End If

' Create the pythonw command to run the application (hidden)
pythonCmd = "pythonw.exe """ & currentDir & "\fixed_app.py"""

' Run the application without showing a window
' 0 = hidden window, False = don't wait for it to complete
exitCode = shell.Run(pythonCmd, 0, False)

' Clean up objects
Set shell = Nothing
Set fso = Nothing

' ===== Helper Functions =====

Sub WriteErrorLog(message)
    Dim logFile
    
    On Error Resume Next
    Set logFile = fso.CreateTextFile(errorFile, True)
    If Err.Number = 0 Then
        logFile.WriteLine Now & " - " & message
        logFile.Close
        
        ' Also show a message box for critical errors
        MsgBox message, vbExclamation, "AI Image Generator Error"
    End If
    On Error Goto 0
End Sub

Sub SetEnvironmentVariablesFromConfig()
    ' Try to read API keys from config and set environment variables
    On Error Resume Next
    
    If fso.FileExists(currentDir & "\config.json") Then
        Dim configFile, configContent, replicate_key, hf_token
        
        Set configFile = fso.OpenTextFile(currentDir & "\config.json", 1)
        configContent = configFile.ReadAll
        configFile.Close
        
        ' Very basic extraction (a proper JSON parser would be better)
        If InStr(configContent, """replicate_api_key""") > 0 Then
            replicate_key = ExtractValueFromJson(configContent, "replicate_api_key")
            If Len(replicate_key) > 0 Then
                shell.Environment("PROCESS").Item("REPLICATE_API_TOKEN") = replicate_key
            End If
        End If
        
        If InStr(configContent, """huggingface_token""") > 0 Then
            hf_token = ExtractValueFromJson(configContent, "huggingface_token")
            If Len(hf_token) > 0 Then
                shell.Environment("PROCESS").Item("HUGGINGFACE_TOKEN") = hf_token
            End If
        End If
    End If
    
    On Error Goto 0
End Sub

Function ExtractValueFromJson(jsonStr, key)
    ' Very basic JSON extraction - not a real parser
    Dim keyPattern, valueStart, valueEnd, value
    
    keyPattern = """" & key & """\s*:\s*""([^""]*)"""
    
    ' Find key position
    Dim regex, matches
    Set regex = New RegExp
    regex.Pattern = keyPattern
    regex.Global = False
    regex.IgnoreCase = True
    
    Set matches = regex.Execute(jsonStr)
    If matches.Count > 0 Then
        ExtractValueFromJson = matches(0).SubMatches(0)
    Else
        ExtractValueFromJson = ""
    End If
End Function
