# Issue Slip Manager

<p align="center">
  <img src="assets/icons/app_icon.png" width="96" height="96" alt="Issue Slip Manager Logo" />
</p>

<p align="center">
  <strong>Fast, Standalone Windows Desktop Barcode & Material Issue System</strong><br>
  <em>100% Local SQLite &bull; Zero Cloud Dependency &bull; Wireless Mobile Barcode Scanning with GlobalScan</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011%20x64-blue?style=for-the-badge&logo=windows" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/Scanner-GlobalScan%20Play%20Store-green?style=for-the-badge&logo=googleplay" alt="Play Store Scanner">
  <img src="https://img.shields.io/badge/Data%20Privacy-100%25%20Local-purple?style=for-the-badge" alt="Local Data">
  <img src="https://img.shields.io/badge/Tests-76%2F76%20Passing-brightgreen?style=for-the-badge" alt="76 Tests Passing">
</p>

---

## ⚡ Overview

**Issue Slip Manager** is a high-speed, offline Windows desktop application built with Python 3.11, PySide6 (Qt6), SQLite, ReportLab, and openpyxl.

It provides factory floors and warehouses with instant material issue tracking, printable barcode/QR sticker sheets, inventory stock ledger, and seamless wireless barcode scanning from your smartphone.

### 🛡️ 100% Local Data Privacy (Zero Cloud)
* **Zero Cloud Storage**: All materials, issue slips, purchase records, and stock balances are stored strictly in your local SQLite database on your computer (`data/issue_slip.db`).
* **No Third-Party Hosting or Servers**: Runs independently without cloud subscriptions, external APIs, or complex deployment dependencies.

---

## 📱 Wireless Phone Scanner Setup (GlobalScan)

No need to install custom APKs or configure web servers. Connect your smartphone in seconds:

```
+------------------------------------+           Wi-Fi           +------------------------------------+
|  Smartphone (Google Play Store)    | ------------------------> |  Issue Slip Manager (PC Desktop)   |
|  "GlobalScan: Barcode & QR to PC"  |       Virtual Wedge       |  Active Issue Slip / Inward Form   |
+------------------------------------+                           +------------------------------------+
```

### Option 1: "GlobalScan: Barcode & QR to PC" from Google Play Store (Recommended)
1. Install **GlobalScan: Barcode & QR to PC** (or *Barcode to PC*) directly from the Google Play Store on your Android phone.
2. In Issue Slip Manager on your PC, click **Connect Phone** in the top navigation bar to display the server pairing QR code.
3. In the mobile app, tap **Scan Server QR** and scan the QR code on your PC monitor.
4. Point your phone at any barcode or QR sticker. Scans are automatically typed into your active Issue Slip field in real-time!

### Option 2: Instant Phone Camera Scanner (Zero App Install)
* Simply open your smartphone's default **Camera** or **QR Scanner** app.
* Scan the QR code shown in **Connect Phone**.
* Your phone's browser (Chrome, Safari, Edge) opens the high-speed local scanner web app instantly — zero app installation required!

---

## 🖥️ Primary Modules

1. **Barcode & Issue Slip Entry**:
   - Supports wireless phone scanners, USB barcode guns, and manual entry.
   - Real-time stock availability check with automatic deduction on finalized slips.
   - Generates professional PDF slips matching standard industrial templates and exports to Excel.

2. **Barcode & Label Generator**:
   - Creates Code128 barcodes and 2D QR codes.
   - Prints single thermal roll stickers (50x25mm) or multi-label A4 sticker sheets.
   - Batch export catalog with embedded QR images to Excel.

3. **Stock Database Ledger**:
   - Complete material master catalog with category filtering.
   - Stock adjustments with audit trail and historical ledger.
   - Inward purchase receiving with vendor invoice tracking.

---

## 🚀 Running Locally

```powershell
# Clone repository
git clone https://github.com/sameerrout/time.git
cd time

# Install dependencies
pip install -r requirements.txt

# Launch desktop app
python main.py

# Run test suite (76 tests)
python -m unittest discover -s tests -t .
```

---

## 📄 License
Proprietary &copy; 2026. All rights reserved. Built with Python, PySide6, and SQLite.
