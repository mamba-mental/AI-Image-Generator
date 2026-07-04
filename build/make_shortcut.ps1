# Create/refresh the desktop shortcut for the frozen app.
# Real Desktop = GetFolderPath('Desktop') - resolves the OneDrive redirection; never hardcode %USERPROFILE%\Desktop.
$repo = Split-Path -Parent $PSScriptRoot
$exe = Join-Path $repo "dist\AI Studio Void\AI Studio Void.exe"
if (-not (Test-Path $exe)) { Write-Error "exe not found: $exe - build first"; exit 1 }
$desktop = [Environment]::GetFolderPath('Desktop')
$lnk = Join-Path $desktop 'AI Studio Void.lnk'
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $exe
$s.WorkingDirectory = Split-Path -Parent $exe
$s.IconLocation = Join-Path $repo 'ai-studio-void.ico'
$s.Description = 'AI Studio Void - fal.ai / Replicate / HF / Gemini media studio'
$s.Save()
Write-Output "shortcut: $lnk -> $exe"
