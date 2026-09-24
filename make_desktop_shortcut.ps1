$ws = New-Object -ComObject WScript.Shell
$root = "E:\workspace0525\AI-CAD"
$bat = $root + "\start.bat"
$desktop = [Environment]::GetFolderPath("Desktop")
$lnk = $desktop + "\AI-CAD one-click.lnk"
$s = $ws.CreateShortcut($lnk)
$s.TargetPath = $bat
$s.WorkingDirectory = $root
$s.IconLocation = $bat + ",0"
$s.Save()
Write-Output ("OK -> " + $lnk)
