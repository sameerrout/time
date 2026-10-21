# Issue Slip Manager & TTL Scanner Suite

<p align="center">
  <img src="assets/icons/app_icon.png" width="96" height="96" alt="TTL Scanner Suite Logo" />
</p>

<p align="center">
  <strong>High-Speed Industrial Wireless Barcode & Issue Slip System</strong><br>
  <em>100% Local SQLite &bull; Zero Cloud Storage &bull; Offline-First &bull; Local Wi-Fi + Encrypted Zero-Config Remote Tunnel</em>
</p>

<p align="center">
  <a href="https://github.com/sameerrout/time/releases/tag/v1.0.0"><img src="https://img.shields.io/badge/Release-v1.0.0-emerald?style=for-the-badge&logo=github" alt="Release v1.0.0"></a>
  <img src="https://img.shields.io/badge/Windows-10%20%7C%2011%20x64-blue?style=for-the-badge&logo=windows" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/Android-7.0%2B-green?style=for-the-badge&logo=android" alt="Android 7.0+">
  <img src="https://img.shields.io/badge/Data%20Privacy-100%25%20Local-purple?style=for-the-badge" alt="Local Data">
  <img src="https://img.shields.io/badge/Tests-84%2F84%20Passing-brightgreen?style=for-the-badge" alt="84 Tests Passing">
</p>

---

## 🌐 Live Web Site & Downloads

You can view the interactive download site directly via GitHub Pages or open `index.html`:
- 🔗 **Web Site**: [https://sameerrout.github.io/time/](https://sameerrout.github.io/time/) *(enable GitHub Pages on branch `main`)*
- 📦 **GitHub Releases**: [https://github.com/sameerrout/time/releases/tag/v1.0.0](https://github.com/sameerrout/time/releases/tag/v1.0.0)

### 📥 One-Click Downloads

| Target | Platform | Asset | Size | Checksum (SHA-256) |
|---|---|---|---|---|
| **Windows Desktop** | Windows 10 / 11 (64-bit) | [**Download Windows ZIP**](https://github.com/sameerrout/time/releases/download/v1.0.0/IssueSlipManager-v1.0.0-Windows-x64.zip) | ~179 MB | `f4c4ac6b06018f92ea64e67e7db4a9a9db1a4a4b70a1f49c0118801593c7dc27` |
| **Mobile Scanner** | Android 7.0+ (ARM64 / x86_64) | [**Download Android APK**](https://github.com/sameerrout/time/releases/download/v1.0.0/TTL-Scanner-1.0.0.apk) | ~34.5 MB | `0923ffe7136a3b7c586abe955721bdb35e2f486db0c18d4fc3057062d660e39e` |

---

## ⚡ What is TTL Scanner Suite?

TTL Scanner Suite transforms factory floors, stockrooms, and warehouses by turning any Android smartphone into a rugged, high-speed wireless barcode & QR scanner that feeds live inventory and issue slips directly into your desktop database.

### 🛡️ Hard Privacy & Security Rules (Zero Cloud)
1. **NO DATA IN THE CLOUD**: There are zero cloud databases and zero cloud APIs holding inventory, users, or scan logs. All data lives in your local SQLite database file on your PC.
2. **Offline-First Queue**: The mobile scanner caches all scans locally in an encrypted Room SQLite database if the network drops. Scans sync automatically once connection resumes.
3. **Dual Connection Modes**:
   - **Local Wi-Fi Mode**: Connects directly over LAN with self-signed TLS certificates and mDNS discovery.
   - **Remote Tunnel Mode**: Built-in Cloudflare quick tunnel for off-site or multi-building scanning without static IPs, port forwarding, or firewall changes.

---

## 📱 Features

### Desktop Application (`IssueSlipManager`)
- **PySide6 (Qt6) Modern Interface**: Fast, responsive desktop client running natively on Windows 10/11.
- **Barcode & Issue Slip Entry**: Real-time barcode entry, multi-item issue slips, and atomic stock deductions.
- **Barcode & Label Generator**: Generate Code128 and QR codes, real-time label previews, PNG export, and printable A4 PDF sticker sheets.
- **Stock Database Ledger**: Complete material catalog, live search filters, adjustments with audit logging, and CSV/Excel import & export.
- **Wireless Mobile Controller**: Monitor connected mobile scanners, manage paired devices, revoke tokens, and view real-time sync pulses.

### Android Mobile App (`TTL Scanner`)
- **Jetpack Compose + Material 3**: Sleek dark industrial UI optimized for warehouse lighting.
- **CameraX + Google ML Kit**: Instant offline barcode & QR code recognition.
- **Continuous & Single Scan**: High-speed continuous conveyor scanning with duplicate throttling and haptic audio feedback.
- **Offline Room Database**: Full offline queue with automatic exponential backoff retries via Android WorkManager.
- **Hardware Torch & Torch Toggle**: In-app flashlight toggle for dimly lit storage bays.

---

## 🚀 Quick Setup & Pairing Guide

```
+-------------------+      LAN Wi-Fi or Cloudflare Tunnel      +-------------------+
|   Android Phone   | ---------------------------------------> |  Windows Desktop  |
|   (TTL Scanner)   | <--------------------------------------- | (IssueSlipManager)|
+-------------------+       Encrypted HTTPS / Bearer Token     +-------------------+
```

### Step 1: Launch Desktop App
1. Extract `IssueSlipManager-v1.0.0-Windows-x64.zip`.
2. Run `IssueSlipManager.exe`.
3. Click the **Connect Phone** button in the top navigation bar. A 6-digit pairing code and QR code will appear.

### Step 2: Install & Pair Mobile App
1. Install `TTL-Scanner-1.0.0.apk` on your Android device (ensure "Install unknown apps" permission is enabled).
2. Open **TTL Scanner**.
3. Tap **Scan Setup QR** and scan the QR code displayed on your desktop screen.
4. The device exchanges cryptographic tokens and pairs instantly.

### Step 3: Scan Materials
- Switch between **Issue Mode** (deduct from open slip) and **Receive Mode** (plant inward).
- Aim camera at barcode or QR sticker. Scans beam directly into the desktop view in under 100 milliseconds.

---

## 🔐 Architecture & Hardened Security

- **Loopback Remote Listener**: Desktop remote listener binds strictly to `127.0.0.1:8444`. Only authenticated reverse-proxy traffic can reach it.
- **Sliding-Window Rate Limiting**: Max 60 requests/minute per IP, rejecting brute-force or malicious scanning.
- **Payload Restrictions**: Hard 64 KB maximum request body prevents memory exhaustion.
- **Strict Bearer Tokens**: Cryptographically secure 32-byte hexadecimal device tokens stored in SQLite on desktop and Android `EncryptedSharedPreferences` on mobile.
- **Clean Distribution Integrity**: Windows release zip is pre-initialized with a pristine empty SQLite database (10 tables, 0 records, 0 private certificates, 0 logs).

---

## 🛠️ Building From Source

### Desktop (Python 3.11)
```powershell
# Clone repo
git clone https://github.com/sameerrout/time.git
cd time

# Install dependencies
pip install -r requirements.txt

# Run desktop app
python main.py

# Run test suite (84 tests)
python -m unittest discover -s tests -t .
```

### Android Scanner App
```powershell
cd android
./gradlew testReleaseUnitTest
./gradlew assembleRelease
```

### Automated Release Packaging
```powershell
# Produces clean release ZIP, signed APK, and updates web/releases.json
powershell -ExecutionPolicy Bypass -File scripts\release.ps1
```

---

## 📄 License
Proprietary &copy; 2026. All rights reserved. Built with Python, PySide6, Kotlin, Jetpack Compose, and SQLite.
