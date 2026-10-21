/**
 * TTL Scanner Mobile Terminal PWA
 * Offline-first warehouse scanner for Issue Slip and Plant Inward receiving.
 */

(function () {
  'use strict';

  // --- State ---
  let currentMode = 'ISSUE'; // 'ISSUE' or 'RECEIVE'
  let activeMaterial = null;
  let materialsMap = new Map(); // code -> material dict
  let offlineQueue = [];
  let recentScans = [];
  let scanDebounceTimer = null;
  let lastScannedCode = '';
  let lastScanTime = 0;
  let isScanningActive = true;

  // Camera & Scanner handles
  let videoStream = null;
  let barcodeDetector = null;
  let html5QrScanner = null;
  let isTorchOn = false;
  let videoTrack = null;

  // DOM Elements
  const appHeader = document.getElementById('appHeader');
  const modeBadge = document.getElementById('modeBadge');
  const connStatus = document.getElementById('connStatus');
  const connText = document.getElementById('connText');
  const syncBanner = document.getElementById('syncBanner');
  const syncCount = document.getElementById('syncCount');
  const btnTorch = document.getElementById('btnTorch');
  const btnManualEntry = document.getElementById('btnManualEntry');
  const alertUnknown = document.getElementById('alertUnknown');
  const alertUnknownText = document.getElementById('alertUnknownText');
  const btnDismissAlert = document.getElementById('btnDismissAlert');

  // Confirmation Sheet
  const confirmSheet = document.getElementById('confirmSheet');
  const sheetCode = document.getElementById('sheetCode');
  const sheetName = document.getElementById('sheetName');
  const sheetStockTag = document.getElementById('sheetStockTag');
  const warnStockLimit = document.getElementById('warnStockLimit');
  const fieldsIssue = document.getElementById('fieldsIssue');
  const fieldsReceive = document.getElementById('fieldsReceive');
  const inputIssueQty = document.getElementById('inputIssueQty');
  const inputRequiredQty = document.getElementById('inputRequiredQty');
  const inputPurpose = document.getElementById('inputPurpose');
  const inputReceiveQty = document.getElementById('inputReceiveQty');
  const inputUnitPrice = document.getElementById('inputUnitPrice');
  const selectGst = document.getElementById('selectGst');
  const lblRecTotal = document.getElementById('lblRecTotal');
  const btnAddScan = document.getElementById('btnAddScan');
  const btnAddAndNext = document.getElementById('btnAddAndNext');

  // Steppers
  const btnDecIssue = document.getElementById('btnDecIssue');
  const btnIncIssue = document.getElementById('btnIncIssue');
  const btnDecRec = document.getElementById('btnDecRec');
  const btnIncRec = document.getElementById('btnIncRec');

  // Tabs
  const tabIssue = document.getElementById('tabIssue');
  const tabReceive = document.getElementById('tabReceive');

  // Modals
  const modalSettings = document.getElementById('modalSettings');
  const btnOpenSettings = document.getElementById('btnOpenSettings');
  const btnCloseSettings = document.getElementById('btnCloseSettings');
  const pairingForm = document.getElementById('pairingForm');
  const pairedInfo = document.getElementById('pairedInfo');
  const inputServerUrl = document.getElementById('inputServerUrl');
  const inputPairingCode = document.getElementById('inputPairingCode');
  const inputDeviceName = document.getElementById('inputDeviceName');
  const btnSubmitPair = document.getElementById('btnSubmitPair');
  const pairErrorMsg = document.getElementById('pairErrorMsg');
  const lblPairedName = document.getElementById('lblPairedName');
  const lblCatalogCount = document.getElementById('lblCatalogCount');
  const btnSyncCatalog = document.getElementById('btnSyncCatalog');
  const btnUnpair = document.getElementById('btnUnpair');

  const modalManual = document.getElementById('modalManual');
  const btnCloseManual = document.getElementById('btnCloseManual');
  const inputManualSearch = document.getElementById('inputManualSearch');
  const manualResults = document.getElementById('manualResults');

  const modalHistory = document.getElementById('modalHistory');
  const btnOpenHistory = document.getElementById('btnOpenHistory');
  const btnCloseHistory = document.getElementById('btnCloseHistory');
  const historyListContainer = document.getElementById('historyListContainer');
  const btnClearHistory = document.getElementById('btnClearHistory');

  // Audio Context for synthetic warehouse beeps
  let audioCtx = null;
  function playBeep(freq = 880, duration = 0.12, type = 'sine') {
    try {
      if (!audioCtx) {
        audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      }
      if (audioCtx.state === 'suspended') {
        audioCtx.resume();
      }
      const osc = audioCtx.createOscillator();
      const gain = audioCtx.createGain();
      osc.type = type;
      osc.frequency.setValueAtTime(freq, audioCtx.currentTime);
      gain.gain.setValueAtTime(0.3, audioCtx.currentTime);
      gain.gain.exponentialRampToValueAtTime(0.01, audioCtx.currentTime + duration);
      osc.connect(gain);
      gain.connect(audioCtx.destination);
      osc.start();
      osc.stop(audioCtx.currentTime + duration);
    } catch (e) {
      // Audio not supported
    }
  }

  function vibrate(ms = 80) {
    if ('vibrate' in navigator) {
      try { navigator.vibrate(ms); } catch (e) {}
    }
  }

  // --- Configuration & Local Storage ---
  function getStoredConfig() {
    return {
      token: localStorage.getItem('ttl_device_token') || '',
      deviceName: localStorage.getItem('ttl_device_name') || 'Floor Phone',
      serverUrl: localStorage.getItem('ttl_server_url') || window.location.origin
    };
  }

  function saveConfig(token, deviceName, serverUrl) {
    localStorage.setItem('ttl_device_token', token);
    localStorage.setItem('ttl_device_name', deviceName);
    localStorage.setItem('ttl_server_url', serverUrl);
  }

  function loadOfflineQueue() {
    try {
      const q = localStorage.getItem('ttl_offline_queue');
      offlineQueue = q ? JSON.parse(q) : [];
    } catch (e) {
      offlineQueue = [];
    }
    updateSyncBadge();
  }

  function saveOfflineQueue() {
    try {
      localStorage.setItem('ttl_offline_queue', JSON.stringify(offlineQueue));
    } catch (e) {}
    updateSyncBadge();
  }

  function updateSyncBadge() {
    if (offlineQueue.length > 0) {
      syncBanner.style.display = 'block';
      syncCount.innerText = offlineQueue.length;
    } else {
      syncBanner.style.display = 'none';
    }
  }

  function loadRecentScans() {
    try {
      const h = localStorage.getItem('ttl_recent_scans');
      recentScans = h ? JSON.parse(h) : [];
    } catch (e) {
      recentScans = [];
    }
  }

  function addRecentScan(item) {
    recentScans.unshift(item);
    if (recentScans.length > 15) recentScans.pop();
    try {
      localStorage.setItem('ttl_recent_scans', JSON.stringify(recentScans));
    } catch (e) {}
  }

  // --- Scan status helpers ---
  // Lifecycle: sent (delivered, waiting for desktop) -> applied | rejected
  function setScanStatus(eventId, status, reason) {
    const idx = recentScans.findIndex(s => s.event_id === eventId);
    if (idx === -1) return;
    recentScans[idx].status = status;
    if (reason) recentScans[idx].reject_reason = reason;
    try { localStorage.setItem('ttl_recent_scans', JSON.stringify(recentScans)); } catch (e) {}
  }

  async function readScanReply(resp) {
    try { return await resp.json(); } catch (e) { return {}; }
  }

  // Ask the desktop what became of scans that were delivered but not yet confirmed
  let refreshingStatuses = false;
  async function refreshSentStatuses() {
    if (refreshingStatuses || !navigator.onLine) return;
    const config = getStoredConfig();
    if (!config.token) return;
    const waiting = recentScans.filter(s => s.status === 'sent');
    if (waiting.length === 0) return;
    refreshingStatuses = true;
    try {
      for (const sc of waiting) {
        try {
          const r = await fetch(`${config.serverUrl}/api/scan/${encodeURIComponent(sc.event_id)}`, {
            headers: { 'Authorization': `Bearer ${config.token}` }
          });
          if (!r.ok) continue;
          const body = await r.json();
          const st = body && body.data && body.data.status;
          if (st === 'applied' || st === 'rejected') {
            setScanStatus(sc.event_id, st, body.data.reject_reason || '');
          }
        } catch (e) {}
      }
    } finally {
      refreshingStatuses = false;
    }
  }

  // --- Service Worker ---
  if ('serviceWorker' in navigator) {
    navigator.serviceWorker.register('sw.js').catch(err => console.log('SW reg error:', err));
  }

  // --- Initialization ---
  async function initApp() {
    loadOfflineQueue();
    loadRecentScans();
    loadCachedMaterials();

    setupUIEventListeners();
    checkConnectionStatus();
    setInterval(checkConnectionStatus, 4000);
    setInterval(flushOfflineQueue, 5000);
    setInterval(refreshSentStatuses, 4000);
    setInterval(fetchMaterialsCatalog, 60000);  // keep stock/prices fresh

    const config = getStoredConfig();
    inputServerUrl.value = config.serverUrl;
    inputDeviceName.value = config.deviceName;

    const headerDeviceName = document.getElementById('headerDeviceName');
    if (headerDeviceName) {
      headerDeviceName.innerText = config.deviceName || 'Mobile';
    }

    const urlParams = new URLSearchParams(window.location.search);
    if (urlParams.has('code')) {
      inputPairingCode.value = urlParams.get('code');
      if (!config.token) {
        openPairingModal();
      }
    }

    if (!config.token) {
      openPairingModal();
    } else {
      updatePairedUI(true);
      fetchMaterialsCatalog();
    }

    startCamera();
  }

  // --- UI Event Listeners ---
  function setupUIEventListeners() {
    // Mode Switching
    tabIssue.addEventListener('click', () => setMode('ISSUE'));
    tabReceive.addEventListener('click', () => setMode('RECEIVE'));

    // Modals
    btnOpenSettings.addEventListener('click', () => {
      const cfg = getStoredConfig();
      updatePairedUI(!!cfg.token);
      modalSettings.classList.add('open');
    });
    btnCloseSettings.addEventListener('click', () => modalSettings.classList.remove('open'));

    btnManualEntry.addEventListener('click', () => {
      modalManual.classList.add('open');
      inputManualSearch.value = '';
      renderManualResults('');
      inputManualSearch.focus();
    });
    btnCloseManual.addEventListener('click', () => modalManual.classList.remove('open'));

    btnOpenHistory.addEventListener('click', async () => {
      await refreshSentStatuses();
      renderHistoryModal();
      modalHistory.classList.add('open');
    });
    btnCloseHistory.addEventListener('click', () => modalHistory.classList.remove('open'));
    btnClearHistory.addEventListener('click', () => {
      recentScans = [];
      localStorage.removeItem('ttl_recent_scans');
      renderHistoryModal();
    });

    // Pairing Submit
    btnSubmitPair.addEventListener('click', handlePairingSubmit);
    btnUnpair.addEventListener('click', handleUnpair);
    btnSyncCatalog.addEventListener('click', fetchMaterialsCatalog);

    // Alert Dismiss
    btnDismissAlert.addEventListener('click', () => {
      alertUnknown.classList.remove('open');
      resumeScanning();
    });

    // Confirmation Sheet Buttons
    btnAddScan.addEventListener('click', () => submitScan(false));
    btnAddAndNext.addEventListener('click', () => submitScan(true));

    // Steppers - Issue
    btnDecIssue.addEventListener('click', () => {
      let v = parseFloat(inputIssueQty.value) || 1;
      if (v > 1) inputIssueQty.value = v - 1;
      checkStockWarning();
    });
    btnIncIssue.addEventListener('click', () => {
      let v = parseFloat(inputIssueQty.value) || 0;
      inputIssueQty.value = v + 1;
      checkStockWarning();
    });
    inputIssueQty.addEventListener('input', checkStockWarning);

    // Steppers - Receive
    btnDecRec.addEventListener('click', () => {
      let v = parseFloat(inputReceiveQty.value) || 1;
      if (v > 1) inputReceiveQty.value = v - 1;
      calculateReceiveTotal();
    });
    btnIncRec.addEventListener('click', () => {
      let v = parseFloat(inputReceiveQty.value) || 0;
      inputReceiveQty.value = v + 1;
      calculateReceiveTotal();
    });
    inputReceiveQty.addEventListener('input', calculateReceiveTotal);
    inputUnitPrice.addEventListener('input', calculateReceiveTotal);
    selectGst.addEventListener('change', calculateReceiveTotal);

    // Manual Search input
    inputManualSearch.addEventListener('input', (e) => {
      renderManualResults(e.target.value);
    });

    // Torch button
    btnTorch.addEventListener('click', toggleTorch);
  }

  // --- Mode Switching ---
  function setMode(mode) {
    currentMode = mode;
    if (mode === 'ISSUE') {
      tabIssue.classList.add('active');
      tabReceive.classList.remove('active');
      document.body.className = 'mode-issue';
      appHeader.className = 'app-header mode-issue';
      modeBadge.innerText = 'ISSUE';
      fieldsIssue.style.display = 'block';
      fieldsReceive.style.display = 'none';
    } else {
      tabReceive.classList.add('active');
      tabIssue.classList.remove('active');
      document.body.className = 'mode-receive';
      appHeader.className = 'app-header mode-receive';
      modeBadge.innerText = 'RECEIVE';
      fieldsIssue.style.display = 'none';
      fieldsReceive.style.display = 'block';
      calculateReceiveTotal();
    }
    checkStockWarning();
  }

  // --- Material Catalog & Cache ---
  function loadCachedMaterials() {
    try {
      const data = localStorage.getItem('ttl_materials_catalog');
      if (data) {
        const list = JSON.parse(data);
        materialsMap.clear();
        for (const it of list) {
          materialsMap.set(it.code.toUpperCase(), it);
        }
        lblCatalogCount.innerText = list.length;
      }
    } catch (e) {}
  }

  async function fetchMaterialsCatalog() {
    const config = getStoredConfig();
    if (!config.token) return;

    try {
      const resp = await fetch(`${config.serverUrl}/api/materials`, {
        headers: { 'Authorization': `Bearer ${config.token}` }
      });
      if (resp.ok) {
        const body = await resp.json();
        // Server sends {version, count, materials:[...]}; also accept a bare array.
        const list = Array.isArray(body) ? body : (Array.isArray(body.materials) ? body.materials : []);
        materialsMap.clear();
        for (const it of list) {
          materialsMap.set(it.code.toUpperCase(), it);
        }
        localStorage.setItem('ttl_materials_catalog', JSON.stringify(list));
        lblCatalogCount.innerText = list.length;
        console.log(`Cached ${list.length} materials on phone terminal.`);
      }
    } catch (e) {
      console.warn('Could not sync materials catalog:', e);
    }
  }

  function resolveMaterial(rawText) {
    const clean = String(rawText).trim();
    if (!clean) return null;

    let code = clean;
    if (clean.includes('|')) {
      code = clean.split('|')[0].trim();
    }
    code = code.toUpperCase();

    if (materialsMap.has(code)) {
      return materialsMap.get(code);
    }
    return null;
  }

  // --- Camera & Scanner Logic ---
  async function startCamera() {
    const video = document.getElementById('camera-video');

    // 1. Try Native BarcodeDetector API (fastest, zero CPU)
    if ('BarcodeDetector' in window) {
      try {
        barcodeDetector = new window.BarcodeDetector({ formats: ['qr_code', 'code_128', 'ean_13'] });
      } catch (e) {
        barcodeDetector = null;
      }
    }

    try {
      const constraints = {
        video: {
          facingMode: { ideal: 'environment' },
          width: { ideal: 1280 },
          height: { ideal: 720 }
        },
        audio: false
      };
      videoStream = await navigator.mediaDevices.getUserMedia(constraints);
      video.srcObject = videoStream;
      await video.play();

      videoTrack = videoStream.getVideoTracks()[0];
      const capabilities = videoTrack.getCapabilities ? videoTrack.getCapabilities() : {};
      if (capabilities.torch) {
        btnTorch.style.display = 'flex';
      }

      if (barcodeDetector) {
        runNativeScanLoop(video);
      } else {
        // Fallback to Html5Qrcode
        startHtml5QrFallback();
      }
    } catch (err) {
      console.warn('Native getUserMedia failed, trying Html5Qrcode fallback:', err);
      startHtml5QrFallback();
    }
  }

  async function toggleTorch() {
    if (!videoTrack) return;
    try {
      isTorchOn = !isTorchOn;
      await videoTrack.applyConstraints({
        advanced: [{ torch: isTorchOn }]
      });
      btnTorch.innerHTML = isTorchOn ? '⚡ <span>On</span>' : '🔦 <span>Torch</span>';
    } catch (e) {
      console.warn('Torch error:', e);
    }
  }

  function runNativeScanLoop(video) {
    let active = true;
    async function checkFrame() {
      if (!active) return;
      if (isScanningActive && video.readyState === video.HAVE_ENOUGH_DATA) {
        try {
          const barcodes = await barcodeDetector.detect(video);
          if (barcodes && barcodes.length > 0) {
            const rawVal = barcodes[0].rawValue;
            handleDetectedCode(rawVal);
          }
        } catch (e) {}
      }
      requestAnimationFrame(checkFrame);
    }
    requestAnimationFrame(checkFrame);
  }

  function startHtml5QrFallback() {
    if (typeof Html5Qrcode === 'undefined') return;
    const qrDiv = document.getElementById('html5-qr-reader');
    qrDiv.style.display = 'block';

    html5QrScanner = new Html5Qrcode("html5-qr-reader");
    html5QrScanner.start(
      { facingMode: "environment" },
      { fps: 15, qrbox: { width: 250, height: 250 } },
      (decodedText) => {
        handleDetectedCode(decodedText);
      },
      (error) => {}
    ).catch(err => console.warn('Html5Qr start error:', err));
  }

  function handleDetectedCode(rawCode) {
    if (!isScanningActive) return;

    const now = Date.now();
    // 2-second debounce for identical codes
    if (rawCode === lastScannedCode && (now - lastScanTime) < 2000) {
      return;
    }

    lastScannedCode = rawCode;
    lastScanTime = now;

    // Resolve material
    const mat = resolveMaterial(rawCode);
    if (!mat) {
      // Reject unknown code with visual red alert + vibration
      playBeep(320, 0.25, 'sawtooth');
      vibrate(250);
      isScanningActive = false;
      alertUnknownText.innerText = `QR Code: "${rawCode}" is not recognized in the plant master catalog.`;
      alertUnknown.classList.add('open');
      return;
    }

    // Success scan
    playBeep(880, 0.12, 'sine');
    vibrate(80);
    isScanningActive = false;
    openConfirmSheet(mat);
  }

  function openConfirmSheet(mat) {
    activeMaterial = mat;
    sheetCode.innerText = mat.code;
    sheetName.innerText = mat.name;
    const stock = Number(mat.stock || 0);
    sheetStockTag.innerText = `Stock: ${stock} ${mat.uom}`;

    // Reset inputs
    inputIssueQty.value = 1;
    inputRequiredQty.value = '';
    inputPurpose.value = '';
    inputReceiveQty.value = 1;
    inputUnitPrice.value = Number(mat.unit_price || 0).toFixed(2);
    selectGst.value = "18";

    checkStockWarning();
    calculateReceiveTotal();

    confirmSheet.classList.add('open');
  }

  function checkStockWarning() {
    if (!activeMaterial || currentMode !== 'ISSUE') {
      warnStockLimit.style.display = 'none';
      return;
    }
    const entered = parseFloat(inputIssueQty.value) || 0;
    const available = Number(activeMaterial.stock || 0);
    if (entered > available) {
      warnStockLimit.innerText = `⚠️ Warning: Issued Qty (${entered}) exceeds warehouse stock (${available} ${activeMaterial.uom})!`;
      warnStockLimit.style.display = 'block';
    } else {
      warnStockLimit.style.display = 'none';
    }
  }

  function calculateReceiveTotal() {
    if (currentMode !== 'RECEIVE') return;
    const qty = parseFloat(inputReceiveQty.value) || 0;
    const price = parseFloat(inputUnitPrice.value) || 0;
    const gstPct = parseFloat(selectGst.value) || 0;
    const sub = qty * price;
    const tot = sub + (sub * gstPct / 100);
    lblRecTotal.innerText = `₹ ${tot.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function resumeScanning() {
    confirmSheet.classList.remove('open');
    activeMaterial = null;
    isScanningActive = true;
  }

  // --- Submitting Scans ---
  async function submitScan(scanNext = false) {
    if (!activeMaterial) return;

    const eventId = generateUUID();
    const isIssue = (currentMode === 'ISSUE');
    const qty = isIssue ? (parseFloat(inputIssueQty.value) || 1) : (parseFloat(inputReceiveQty.value) || 1);
    const requiredQty = isIssue ? (parseFloat(inputRequiredQty.value) || 0) : 0;
    const purpose = isIssue ? inputPurpose.value.trim() : '';
    const unitPrice = !isIssue ? (parseFloat(inputUnitPrice.value) || 0) : 0;
    const gstParsed = parseFloat(selectGst.value);
    const gstPct = !isIssue ? (Number.isNaN(gstParsed) ? 18 : gstParsed) : 18;
    const totPrice = !isIssue ? (qty * unitPrice * (1 + gstPct / 100)) : 0;

    const scanPayload = {
      event_id: eventId,
      mode: currentMode,
      material_code: activeMaterial.code,
      material_name: activeMaterial.name,
      uom: activeMaterial.uom,
      qty: qty,
      required_qty: requiredQty,
      purpose: purpose,
      unit_price: unitPrice,
      gst_pct: gstPct,
      total_price: totPrice,
      timestamp: new Date().toISOString()
    };

    // Close sheet immediately if user chose Add & Scan Next
    if (scanNext) {
      resumeScanning();
    } else {
      confirmSheet.classList.remove('open');
      isScanningActive = false;
    }

    // Attempt Send
    const config = getStoredConfig();
    let sentOk = false;
    if (navigator.onLine && config.token) {
      try {
        const resp = await fetch(`${config.serverUrl}/api/scan`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${config.token}`
          },
          body: JSON.stringify(scanPayload)
        });
        if (resp.ok) {
          sentOk = true;
          const reply = await readScanReply(resp);
          const st = reply && reply.data && reply.data.status === 'applied' ? 'applied' : 'sent';
          addRecentScan({ ...scanPayload, status: st });
          playBeep(1200, 0.08, 'sine');
        } else if (resp.status === 400) {
          // The server gave a definitive "no" (unknown material, insufficient stock, ...).
          // Do NOT queue it for retry - it would be rejected forever.
          sentOk = true;
          const reply = await readScanReply(resp);
          addRecentScan({ ...scanPayload, status: 'rejected', reject_reason: reply.message || 'Rejected by server' });
          playBeep(300, 0.3, 'sawtooth');
          try { alert('Scan rejected: ' + (reply.message || 'Rejected by server')); } catch (e) {}
        }
      } catch (e) {
        sentOk = false;
      }
    }

    if (!sentOk) {
      // Store in offline queue for auto-retry
      offlineQueue.push(scanPayload);
      saveOfflineQueue();
      addRecentScan({ ...scanPayload, status: 'pending' });
      playBeep(600, 0.15, 'triangle');
    }

    if (!scanNext) {
      resumeScanning();
    }
  }

  // --- Offline Queue Sync ---
  async function flushOfflineQueue() {
    if (offlineQueue.length === 0) return;
    const config = getStoredConfig();
    if (!navigator.onLine || !config.token) return;

    const remaining = [];
    for (const item of offlineQueue) {
      try {
        const resp = await fetch(`${config.serverUrl}/api/scan`, {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${config.token}`
          },
          body: JSON.stringify(item)
        });
        if (resp.ok) {
          const reply = await readScanReply(resp);
          setScanStatus(item.event_id, reply && reply.data && reply.data.status === 'applied' ? 'applied' : 'sent');
        } else if (resp.status === 400) {
          const reply = await readScanReply(resp);
          setScanStatus(item.event_id, 'rejected', reply.message || 'Rejected by server');
        } else {
          remaining.push(item);
        }
      } catch (e) {
        remaining.push(item);
      }
    }
    offlineQueue = remaining;
    saveOfflineQueue();
  }

  // --- Connection Status Check ---
  async function checkConnectionStatus() {
    const config = getStoredConfig();
    if (!navigator.onLine || !config.serverUrl) {
      setConnectionPill(false);
      return;
    }

    try {
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);
      const resp = await fetch(`${config.serverUrl}/api/health`, {
        signal: controller.signal
      });
      clearTimeout(timeoutId);
      setConnectionPill(resp.ok);
    } catch (e) {
      setConnectionPill(false);
    }
  }

  function setConnectionPill(isOnline) {
    if (isOnline) {
      connStatus.className = 'status-pill online';
      connText.innerText = 'Connected';
    } else {
      connStatus.className = 'status-pill offline';
      connText.innerText = 'Offline';
    }
  }

  // --- Pairing Flow ---
  function openPairingModal() {
    modalSettings.classList.add('open');
    updatePairedUI(false);
  }

  function updatePairedUI(isPaired) {
    const cfg = getStoredConfig();
    if (isPaired) {
      pairingForm.style.display = 'none';
      pairedInfo.style.display = 'block';
      lblPairedName.innerText = cfg.deviceName;
    } else {
      pairingForm.style.display = 'block';
      pairedInfo.style.display = 'none';
    }
  }

  async function handlePairingSubmit() {
    const sUrl = inputServerUrl.value.trim().replace(/\/+$/, '');
    const code = inputPairingCode.value.trim();
    const name = inputDeviceName.value.trim() || 'Floor Terminal';

    pairErrorMsg.style.display = 'none';
    if (!code || code.length < 4) {
      pairErrorMsg.innerText = 'Please enter a valid pairing code from desktop.';
      pairErrorMsg.style.display = 'block';
      return;
    }

    btnSubmitPair.disabled = true;
    btnSubmitPair.innerText = 'Connecting & Pairing...';

    try {
      const resp = await fetch(`${sUrl}/api/pair`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ code: code, pairing_code: code, device_name: name })
      });
      const data = await resp.json();

      if (resp.ok && data.success && data.token) {
        saveConfig(data.token, name, sUrl);
        updatePairedUI(true);
        const headerDeviceName = document.getElementById('headerDeviceName');
        if (headerDeviceName) headerDeviceName.innerText = name;
        pairErrorMsg.style.display = 'none';
        modalSettings.classList.remove('open');
        playBeep(980, 0.15, 'sine');
        fetchMaterialsCatalog();
      } else {
        pairErrorMsg.innerText = data.error || data.message || 'Pairing rejected. Check code.';
        pairErrorMsg.style.display = 'block';
      }
    } catch (err) {
      pairErrorMsg.innerText = `Connection failed: ${err.message}. If using self-signed cert, tap certificate accept link first.`;
      pairErrorMsg.style.display = 'block';
    } finally {
      btnSubmitPair.disabled = false;
      btnSubmitPair.innerText = 'Pair with Desktop App';
    }
  }

  function handleUnpair() {
    if (confirm('Unpair this device? You will need a new pairing code from desktop.')) {
      localStorage.removeItem('ttl_device_token');
      updatePairedUI(false);
    }
  }

  // --- Manual Search UI ---
  function renderManualResults(query) {
    manualResults.innerHTML = '';
    const q = query.trim().toUpperCase();
    if (!q) {
      manualResults.innerHTML = '<div style="color:#64748b; font-size:12px; padding:8px;">Start typing material code or description...</div>';
      return;
    }

    let matches = [];
    for (const [code, mat] of materialsMap) {
      if (code.includes(q) || mat.name.toUpperCase().includes(q)) {
        matches.push(mat);
        if (matches.length >= 10) break;
      }
    }

    if (matches.length === 0) {
      manualResults.innerHTML = '<div style="color:#ef4444; font-size:12px; padding:8px;">No matching materials found.</div>';
      return;
    }

    for (const m of matches) {
      const row = document.createElement('div');
      row.style.cssText = 'background:#0f172a; padding:10px 12px; border-radius:6px; cursor:pointer; border:1px solid #334155;';
      row.innerHTML = `<div style="font-size:14px; font-weight:700; color:#38bdf8;">${m.code}</div>
                       <div style="font-size:12px; color:#94a3b8; margin-top:2px;">${m.name} (${m.uom})</div>`;
      row.addEventListener('click', () => {
        modalManual.classList.remove('open');
        handleDetectedCode(m.code);
      });
      manualResults.appendChild(row);
    }
  }

  // --- Scan History UI ---
  function renderHistoryModal() {
    historyListContainer.innerHTML = '';
    if (recentScans.length === 0) {
      historyListContainer.innerHTML = '<div style="color:#64748b; text-align:center; padding:18px;">No scans recorded yet.</div>';
      return;
    }

    for (const s of recentScans) {
      const item = document.createElement('div');
      const isIssue = (s.mode === 'ISSUE');
      item.className = `history-item ${isIssue ? 'issue' : 'receive'}`;

      const timeStr = s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : '';
      const badgeCls = s.status === 'applied' ? 'applied' : (s.status === 'rejected' ? 'rejected' : 'pending');

      item.innerHTML = `
        <div class="history-meta">
          <div class="history-code">[${s.mode}] ${s.material_code} x ${s.qty}</div>
          <div class="history-time">${timeStr} • ${s.material_name ? s.material_name.slice(0, 24) : ''}</div>
        </div>
        <span class="history-badge ${badgeCls}" title="${(s.reject_reason || '').replace(/"/g, '&quot;')}">${s.status}</span>
      `;
      historyListContainer.appendChild(item);
    }
  }

  // --- Helper: UUID generator ---
  function generateUUID() {
    if (typeof crypto !== 'undefined' && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      const r = Math.random() * 16 | 0;
      const v = c === 'x' ? r : (r & 0x3 | 0x8);
      return v.toString(16);
    });
  }

  // Start app on DOM load
  window.addEventListener('DOMContentLoaded', initApp);

})();
