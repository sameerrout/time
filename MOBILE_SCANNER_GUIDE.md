# TTL Scanner — Mobile PWA & Plant Scanner Guide
**Offline Standalone Edition • Local HTTPS LAN Terminal • Zero External CDN Dependencies**

---

## 1. System Architecture

```
[ Plant Staff Smartphone (Android / iOS) ]
                 |
     (Camera QR / Barcode Scan)
                 |
                 v
   [ Mobile PWA "TTL Scanner" ]
   • Local JS Bundle (html5-qrcode + native BarcodeDetector)
   • 1,734 Materials Cached in LocalStorage
   • IndexedDB / Local Offline Resend Queue
                 |
                 | HTTPS POST /api/scan (Bearer Device Token)
                 v
[ Workstation Embedded HTTPS Server (aiohttp port 8443) ]
   • Self-signed X.509 TLS certificate with LAN IP SAN
   • Token verification & Device Management
   • Idempotent event logging (`scan_events` SQLite)
                 |
        +--------+--------+
        |                 |
  (Qt Signals)      (WebSocket Live)
        |                 |
        v                 v
[ Issue Slip Page ]   [ Plant Inward Entry ]
(Stock OUT on post)   (Stock IN / Auto-receive)
```

---

## 2. Workstation Setup & Network Configuration

### 2.1 Server Port & Windows Firewall Rule
The server runs on **port 8443** over your factory / warehouse local Wi-Fi.
To allow phones on the same Wi-Fi to reach the workstation, run this single command in **PowerShell (Run as Administrator)**:

```powershell
netsh advfirewall firewall add rule name="TTL Mobile Scanner" dir=in action=allow protocol=TCP localport=8443
```

*(You can also click **"📋 Copy Command"** inside the desktop **"📱 Connect Phone"** dialog).*

### 2.2 Finding Your Workstation's LAN IP
- Click the green **"📱 Connect Phone"** button in the top header of the desktop application (or at the bottom of the Home screen).
- The dialog automatically detects and displays your current LAN IP (e.g., `192.168.0.102`) and the full server URL:
  `https://192.168.0.102:8443`
- If your router assigns a new IP address, the desktop app automatically detects the new IP, generates an updated certificate, and refreshes the pairing QR code.

---

## 3. Smartphone Pairing & Installation Workflow

### 3.1 Step-by-Step Connection
1. **Connect Wi-Fi**: Connect the phone to the **same Wi-Fi network** as the desktop PC.
2. **Scan Pairing QR Code**:
   - Open the phone's native camera or QR scanner.
   - Scan the large QR code displayed in the desktop **"Connect Phone"** window.
   - Tap the link: `https://<YOUR-IP>:8443/?code=<6-DIGIT-CODE>`.
3. **Accept Security Certificate (First Time Only)**:
   - Because the certificate is self-signed specifically for your offline plant LAN IP, mobile browsers show a privacy warning (*"Your connection is not private"*).
   - In Google Chrome / Edge: Tap **"Advanced"** &rarr; Tap **"Proceed to 192.168.x.x (unsafe)"**.
   - In Safari (iOS): Tap **"Show Details"** &rarr; Tap **"visit this website"**.
4. **Register Device**:
   - The 6-digit code will already be pre-filled from the QR URL.
   - Enter your name or terminal label (e.g., *"Floor Terminal 1"* or *"Ramesh Galaxy S23"*).
   - Tap **"Pair with Desktop App"**.
   - The phone receives a secure bearer token and instantly downloads all **1,734 material master records** into local phone memory for sub-second offline lookups!
5. **Install as Native PWA**:
   - In Chrome (Android): Tap `⋮` (menu) &rarr; Tap **"Install app"** or **"Add to Home Screen"**.
   - An icon titled **"TTL Scanner"** will appear on the phone's home screen, running full-screen without browser URL bars or chrome.

---

## 4. How the Two Scanner Modes Work

### 4.1 Mode 1: ISSUE (Orange Header & Tab)
- Feeds the **Issue Slip Creation** page (`BarcodeEntryView`).
- **Workflow:**
  1. Operator taps the orange **"ISSUE SLIP (OUT)"** bottom tab on the phone.
  2. Point camera at the material QR code on the drum / box.
  3. Phone beeps & vibrates upon detection.
  4. Confirmation sheet pops up:
     - Shows Material Code, Material Description, and Current Warehouse Stock.
     - Enter **Issued Quantity** using the large `+` / `-` steppers or keypad.
     - Optional: Enter Required Quantity or Department Purpose.
     - If Issued Qty > Current Stock, a clear red warning badge appears.
  5. Tap **[Add Item]** or **[+ Add & Scan Next]**.
  6. The item immediately appears live as a row on the active desktop Issue Slip!
  7. **Crucial Rule:** Stock is **NOT** deducted at scan time. Physical stock is deducted only when the storekeeper clicks **"Finalize Issue Slip"** on the desktop.

### 4.2 Mode 2: RECEIVE (Green Header & Tab)
- Feeds the **Purchased Material (Plant Inward Entry)** page (`PurchasedMaterialView`).
- **Workflow:**
  1. Operator taps the green **"RECEIVE (IN)"** bottom tab.
  2. Point camera at incoming shipment QR codes.
  3. Bottom sheet pops up:
     - Shows Received Quantity stepper, Unit Price, GST % (defaults to 18%), and live Total Price.
  4. Tap **[Add Item]** or **[+ Add & Scan Next]**.
  5. **Auto-Receive Toggle on Desktop:**
     - **Auto-receive OFF (Default):** The desktop form fields are pre-filled so the operator can review and click *"Receive Stock into Plant"*.
     - **Auto-receive ON:** Scans post directly into the grid, update physical stock immediately, and log a ledger receipt with a `📱 <Device Name>` badge!

---

## 5. Offline Queue & Reliability

- **Continuous Scanning:** 2-second debounce prevents accidental double-reading of the same physical label.
- **Offline Cache:** All 1,734 factory materials are cached on the phone. Lookups happen locally in 0 milliseconds even if Wi-Fi fluctuates.
- **Offline Queue:** If Wi-Fi drops while walking inside deep plant storage:
  - Scans are queued in phone memory with client-generated UUIDs (`event_id`).
  - An orange banner **"N waiting to sync"** appears.
  - When Wi-Fi reconnects, all queued scans are transmitted automatically.
  - Desktop database idempotency guarantees **zero duplicate rows**, even across retries.

---

## 6. Acceptance Testing Checklist

| # | Test Scenario | Expected Outcome | Status |
|---|---|---|:---:|
| 1 | Launch desktop app | Local HTTPS server starts on port 8443; status bar shows URL | **PASS** |
| 2 | Open "Connect Phone" | Displays LAN IP, 6-digit code, and high-contrast pairing QR | **PASS** |
| 3 | Pair Phone | Phone connects, saves token, and downloads 1,734 materials | **PASS** |
| 4 | Scan plain code (`1001NM210010BL421`) | Resolves material name & unit; shows confirmation sheet | **PASS** |
| 5 | Scan pipe format (`CODE\|NAME\|UOM`) | Correctly parses all three fields | **PASS** |
| 6 | Scan unknown code | Red "Unknown Material" screen; scan rejected; does NOT send | **PASS** |
| 7 | Scan in ISSUE mode | Row appears live on open desktop Issue Slip in < 1 second | **PASS** |
| 8 | Scan same item again in ISSUE mode | Increments quantity on the existing slip row without duplicate | **PASS** |
| 9 | Scan in RECEIVE mode (Auto-receive OFF) | Populates Material Code, Name, Qty, Unit Price & GST | **PASS** |
| 10 | Scan in RECEIVE mode (Auto-receive ON) | Directly posts to inward register with phone icon & device name | **PASS** |
| 11 | Revoke device from desktop | Revoked phone cannot send scans; receives HTTP 401 Unauthorized | **PASS** |
| 12 | Disconnect Wi-Fi & Scan | Scan queues offline; auto-flushes once Wi-Fi reconnects | **PASS** |

---

## 7. Phase 2: Android APK (Capacitor) Sideloading (Optional)

If your plant's Android devices have corporate policy restrictions on Chrome PWA installation with self-signed LAN certificates:

1. Install Capacitor CLI:
   ```bash
   npm install -g @capacitor/cli @capacitor/android
   ```
2. Initialize inside `app/server/pwa`:
   ```bash
   cd app/server/pwa
   npx cap init "TTL Scanner" com.timetechnoplast.scanner --web-dir .
   npx cap add android
   ```
3. In `android/app/src/main/res/xml/network_security_config.xml`:
   ```xml
   <?xml version="1.0" encoding="utf-8"?>
   <network-security-config>
       <base-config cleartextTrafficPermitted="true">
           <trust-anchors>
               <certificates src="system" />
               <certificates src="user" />
           </trust-anchors>
       </base-config>
   </network-security-config>
   ```
4. Build APK:
   ```bash
   npx cap build android
   ```
The generated `.apk` can be placed in `app/server/pwa/download/ttl-scanner.apk` and downloaded directly via phone browser.
