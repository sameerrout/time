// TTL Scanner & Issue Slip Manager Web Client Script
document.addEventListener('DOMContentLoaded', async () => {
  let releaseData = null;

  try {
    const res = await fetch('releases.json');
    if (res.ok) {
      releaseData = await res.json();
      populateReleases(releaseData);
    }
  } catch (e) {
    console.warn('Could not load releases.json, using fallback defaults', e);
  }

  setupCopyButtons();
  setupQrCode();
});

function populateReleases(data) {
  if (!data || !data.downloads) return;

  const android = data.downloads.android;
  const windows = data.downloads.windows;

  if (android) {
    document.getElementById('android-version').textContent = android.version || '1.0.0';
    document.getElementById('android-size').textContent = android.size || '~34 MB';
    document.getElementById('android-compat').textContent = android.platform || 'Android 7.0+';
    document.getElementById('android-hash').textContent = android.sha256 || 'N/A';
    
    const dlBtn = document.getElementById('android-download-btn');
    if (android.url) {
      dlBtn.href = android.url;
      dlBtn.setAttribute('download', android.filename || 'TTL-Scanner-1.0.0.apk');
    }
  }

  if (windows) {
    document.getElementById('windows-version').textContent = windows.version || '1.0.0';
    document.getElementById('windows-size').textContent = windows.size || '~95 MB';
    document.getElementById('windows-compat').textContent = windows.platform || 'Windows 10 / 11 (64-bit)';
    document.getElementById('windows-hash').textContent = windows.sha256 || 'N/A';
    
    const dlBtn = document.getElementById('windows-download-btn');
    if (windows.url) {
      dlBtn.href = windows.url;
      dlBtn.setAttribute('download', windows.filename || 'IssueSlipManager-v1.0.0-Windows-x64.zip');
    }
  }
}

function setupCopyButtons() {
  const copyAndroid = document.getElementById('copy-android-hash');
  const copyWindows = document.getElementById('copy-windows-hash');

  if (copyAndroid) {
    copyAndroid.addEventListener('click', () => {
      const hash = document.getElementById('android-hash').textContent;
      navigator.clipboard.writeText(hash).then(() => {
        copyAndroid.textContent = 'Copied!';
        setTimeout(() => { copyAndroid.textContent = 'Copy'; }, 2000);
      });
    });
  }

  if (copyWindows) {
    copyWindows.addEventListener('click', () => {
      const hash = document.getElementById('windows-hash').textContent;
      navigator.clipboard.writeText(hash).then(() => {
        copyWindows.textContent = 'Copied!';
        setTimeout(() => { copyWindows.textContent = 'Copy'; }, 2000);
      });
    });
  }
}

// Minimal QR Code visual rendering on Canvas
function setupQrCode() {
  const canvas = document.getElementById('apk-qr-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const size = canvas.width;

  // Clear canvas
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, size, size);

  // Fallback visual QR-like pattern if external library not loaded
  const currentUrl = window.location.href;
  renderVisualQr(ctx, currentUrl, size);
}

function renderVisualQr(ctx, text, size) {
  const modules = 25;
  const cellSize = size / modules;
  ctx.fillStyle = '#0a0e17';

  // Seeded pseudo-random bit pattern based on URL
  let hash = 0;
  for (let i = 0; i < text.length; i++) {
    hash = ((hash << 5) - hash) + text.charCodeAt(i);
    hash |= 0;
  }

  function drawFinderPattern(x, y) {
    ctx.fillRect(x * cellSize, y * cellSize, 7 * cellSize, 7 * cellSize);
    ctx.fillStyle = '#ffffff';
    ctx.fillRect((x + 1) * cellSize, (y + 1) * cellSize, 5 * cellSize, 5 * cellSize);
    ctx.fillStyle = '#0a0e17';
    ctx.fillRect((x + 2) * cellSize, (y + 2) * cellSize, 3 * cellSize, 3 * cellSize);
  }

  // Draw 3 corner finders
  drawFinderPattern(0, 0);
  drawFinderPattern(modules - 7, 0);
  drawFinderPattern(0, modules - 7);

  // Timing patterns
  for (let i = 8; i < modules - 8; i++) {
    if (i % 2 === 0) {
      ctx.fillRect(6 * cellSize, i * cellSize, cellSize, cellSize);
      ctx.fillRect(i * cellSize, 6 * cellSize, cellSize, cellSize);
    }
  }

  // Draw data modules
  for (let r = 0; r < modules; r++) {
    for (let c = 0; c < modules; c++) {
      // Skip finder areas
      if ((r < 8 && c < 8) || (r < 8 && c >= modules - 8) || (r >= modules - 8 && c < 8)) {
        continue;
      }
      if (r === 6 || c === 6) continue;

      const bit = ((hash ^ (r * 31 + c * 17)) & 1) === 0;
      if (bit) {
        ctx.fillRect(c * cellSize, r * cellSize, cellSize, cellSize);
      }
    }
  }
}
