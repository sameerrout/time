import os
import sys
from pathlib import Path
import subprocess

def create_desktop_shortcut():
    # 1. Paths
    app_dir = Path(__file__).resolve().parent
    main_py = app_dir / "main.py"
    icon_ico = app_dir / "assets" / "icons" / "app_icon.ico"
    pythonw = Path(sys.executable).parent / "pythonw.exe"
    
    if not pythonw.exists():
        pythonw = Path(sys.executable)
        
    # Find active Desktop path (checking OneDrive Desktop first, then User Desktop)
    user_home = Path.home()
    onedrive_desktop = user_home / "OneDrive" / "Desktop"
    standard_desktop = user_home / "Desktop"
    
    desktops_to_install = []
    if onedrive_desktop.exists():
        desktops_to_install.append(onedrive_desktop)
    if standard_desktop.exists() and standard_desktop != onedrive_desktop:
        desktops_to_install.append(standard_desktop)

    ps_script = f"""
$WshShell = New-Object -ComObject WScript.Shell
$desktopPaths = @({','.join([f"'{str(p)}'" for p in desktops_to_install])})

foreach ($dPath in $desktopPaths) {{
    $shortcutPath = Join-Path $dPath "Issue Slip Manager.lnk"
    $Shortcut = $WshShell.CreateShortcut($shortcutPath)
    $Shortcut.TargetPath = "{str(pythonw)}"
    $Shortcut.Arguments = '"{str(main_py)}"'
    $Shortcut.WorkingDirectory = "{str(app_dir)}"
    $Shortcut.IconLocation = "{str(icon_ico)},0"
    $Shortcut.Description = "Portable Barcode-Based Issue Slip Management System"
    $Shortcut.WindowStyle = 1
    $Shortcut.Save()
    Write-Output "Created shortcut at: $shortcutPath"
}}
"""
    temp_ps_file = app_dir / "_make_shortcut.ps1"
    try:
        with open(temp_ps_file, "w", encoding="utf-8") as f:
            f.write(ps_script)
            
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(temp_ps_file)],
            capture_output=True,
            text=True
        )
        print(result.stdout)
        if result.stderr:
            print("Errors:", result.stderr)
    finally:
        if temp_ps_file.exists():
            temp_ps_file.unlink()

if __name__ == "__main__":
    create_desktop_shortcut()
