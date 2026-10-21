import os
import sys
import shutil
import subprocess
from pathlib import Path

def build_portable_app():
    root_dir = Path(__file__).resolve().parent
    main_py = root_dir / "main.py"
    icon_ico = root_dir / "assets" / "icons" / "app_icon.ico"
    assets_dir = root_dir / "assets"
    
    print("=" * 60)
    print("Building Portable Windows Desktop Application with PyInstaller")
    print("=" * 60)
    
    pwa_dir = root_dir / "app" / "server" / "pwa"
    
    # PyInstaller command arguments
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name=IssueSlipManager",
        "--noconsole",
        f"--icon={str(icon_ico)}",
        f"--add-data={str(assets_dir)};assets",
        f"--add-data={str(pwa_dir)};app/server/pwa",
        "--clean",
        "--noconfirm",
        str(main_py)
    ]
    
    print(f"Executing: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=str(root_dir))
    if result.returncode != 0:
        print("PyInstaller build failed!")
        return False
        
    dist_app_dir = root_dir / "dist" / "IssueSlipManager"
    if not dist_app_dir.exists():
        print("Build output directory not found!")
        return False

    # Ensure writable portable folders exist inside the distribution folder
    (dist_app_dir / "data").mkdir(exist_ok=True)
    (dist_app_dir / "data" / "certs").mkdir(parents=True, exist_ok=True)
    (dist_app_dir / "logs").mkdir(exist_ok=True)
    (dist_app_dir / "backups").mkdir(exist_ok=True)
    
    # Copy PWA assets to distribution
    dist_pwa = dist_app_dir / "app" / "server" / "pwa"
    if dist_pwa.exists():
        shutil.rmtree(str(dist_pwa))
    dist_pwa.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(str(pwa_dir), str(dist_pwa))
    print(f"Copied PWA mobile assets to portable distribution.")

    # Copy current initialized database to distribution data folder
    src_db = root_dir / "data" / "issue_slip.db"
    if src_db.exists():
        shutil.copy2(str(src_db), str(dist_app_dir / "data" / "issue_slip.db"))
        print(f"Copied local database to portable distribution.")

    # Copy plant QR catalog JSON (1,734 materials from 73-page catalog)
    src_catalog = root_dir / "data" / "plant_qr_catalog.json"
    if src_catalog.exists():
        shutil.copy2(str(src_catalog), str(dist_app_dir / "data" / "plant_qr_catalog.json"))
        print(f"Copied plant QR catalog (1,734 materials) to portable distribution.")

    # Copy plant inventory master JSON (1,734 materials with stock numbers)
    src_inv = root_dir / "data" / "plant_inventory_master.json"
    if src_inv.exists():
        shutil.copy2(str(src_inv), str(dist_app_dir / "data" / "plant_inventory_master.json"))
        print(f"Copied plant inventory master (1,734 materials) to portable distribution.")

    # Create USB Pendrive launcher batch script inside distribution
    launcher_bat = dist_app_dir / "Launch_IssueSlipManager.bat"
    with open(launcher_bat, "w", encoding="utf-8") as f:
        f.write('@echo off\nstart "" "%~dp0IssueSlipManager.exe"\n')
        
    # Create Portable README
    readme_txt = dist_app_dir / "PORTABLE_USB_INSTRUCTIONS.txt"
    with open(readme_txt, "w", encoding="utf-8") as f:
        f.write("""===================================================================
PORTABLE BARCODE-BASED ISSUE SLIP MANAGEMENT SYSTEM
===================================================================

HOW TO RUN FROM A USB PENDRIVE:
1. Copy this entire 'IssueSlipManager' folder to any USB flash drive.
2. Plug the USB flash drive into any compatible Windows 10/11 PC.
3. Double-click 'IssueSlipManager.exe' or 'Launch_IssueSlipManager.bat'.
4. No Python installation, internet access, or administrator rights required!

DATA STORAGE:
All material records, barcodes, issue slips, and stock transactions
are saved locally in the 'data/issue_slip.db' file inside this folder.
Backups can be saved into the 'backups/' directory.
===================================================================
""")

    print(f"\nPortable Windows application ready at:\n{dist_app_dir}")
    print(f"Executable: {dist_app_dir / 'IssueSlipManager.exe'}")
    return True

if __name__ == "__main__":
    build_portable_app()
