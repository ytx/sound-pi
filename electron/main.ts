import { app, BrowserWindow, dialog, ipcMain, screen } from 'electron';
import path from 'path';
import fs from 'fs';
import { execSync } from 'child_process';
import Store from 'electron-store';
import { GIT_COMMIT } from './git-version';
import { logger } from './utils/logger';
import { PipeWireManager } from './audio/pipewire-manager';
import { AudioCapture } from './audio/audio-capture';
import { HidController } from './usb-hid/hid-controller';
import { BluetoothManager } from './bluetooth/bluetooth-manager';
import { WiFiManager } from './network/wifi-manager';
import { GpioManager } from './gpio/gpio-manager';

// Suppress default error dialogs
dialog.showErrorBox = (title: string, content: string) => {
  logger.error('dialog', `${title}: ${content}`);
};

process.on('uncaughtException', (err) => {
  logger.error('main', `uncaughtException: ${err.message}`);
});

process.on('unhandledRejection', (reason) => {
  logger.error('main', `unhandledRejection: ${reason}`);
});

let mainWindow: BrowserWindow | null = null;

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;

// Persistent settings
const store = new Store({
  defaults: {
    masterVolume: 80,
    muted: false,
    inputMix: { usbVolume: 100, browserVolume: 100 },
    ledBrightness: 128,
  },
});

// Manager instances
let pipewireManager: PipeWireManager;
let audioCapture: AudioCapture;
let hidController: HidController;
let bluetoothManager: BluetoothManager;
let wifiManager: WiFiManager;
let gpioManager: GpioManager;

// CPU usage tracking
let prevCpuIdle = 0;
let prevCpuTotal = 0;

function getCpuUsagePercent(): number {
  try {
    const stat = fs.readFileSync('/proc/stat', 'utf-8');
    const line = stat.split('\n')[0];
    const parts = line.split(/\s+/).slice(1).map(Number);
    const idle = parts[3];
    const total = parts.reduce((a, b) => a + b, 0);
    const diffIdle = idle - prevCpuIdle;
    const diffTotal = total - prevCpuTotal;
    prevCpuIdle = idle;
    prevCpuTotal = total;
    if (diffTotal === 0) return 0;
    return Math.round((1 - diffIdle / diffTotal) * 100);
  } catch {
    return 0;
  }
}

function getCpuTempC(): number {
  try {
    const temp = fs.readFileSync('/sys/class/thermal/thermal_zone0/temp', 'utf-8');
    return Math.round(parseInt(temp, 10) / 1000);
  } catch {
    return 0;
  }
}

function getLoadAvg(): string {
  try {
    return fs.readFileSync('/proc/loadavg', 'utf-8').split(' ')[0];
  } catch {
    return '0.00';
  }
}

function getAvailableMemoryMB(): number {
  try {
    const meminfo = fs.readFileSync('/proc/meminfo', 'utf-8');
    const match = meminfo.match(/MemAvailable:\s+(\d+)\s+kB/);
    if (match) return parseInt(match[1], 10) / 1024;
  } catch {}
  return Infinity;
}

function createWindow() {
  const primaryDisplay = screen.getPrimaryDisplay();
  const { width, height } = primaryDisplay.size;

  mainWindow = new BrowserWindow({
    width: isDev ? 480 : width,
    height: isDev ? 320 : height,
    fullscreen: !isDev,
    kiosk: !isDev,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  if (isDev) {
    mainWindow.loadURL('http://localhost:5173');
    mainWindow.webContents.openDevTools();
  } else {
    mainWindow.loadFile(path.join(__dirname, '../dist/index.html'));
    mainWindow.setFullScreen(true);
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

function setupManagers() {
  pipewireManager = new PipeWireManager();
  audioCapture = new AudioCapture();
  hidController = new HidController();
  bluetoothManager = new BluetoothManager();
  wifiManager = new WiFiManager();
  gpioManager = new GpioManager();

  // GPIO rotary encoder events → renderer
  gpioManager.onRotaryTurn((direction) => {
    mainWindow?.webContents.send('gpio:rotary-turn', direction);
  });
  gpioManager.onPress(() => {
    mainWindow?.webContents.send('gpio:rotary-press');
  });
  gpioManager.onLongPress(() => {
    mainWindow?.webContents.send('gpio:rotary-long-press');
  });

  // Audio capture data → renderer
  audioCapture.onData((data) => {
    mainWindow?.webContents.send('audio:data', data);
  });

  // Initialize GPIO
  gpioManager.setup();

  // Start audio capture
  audioCapture.start();

  // Restore saved LED brightness
  const brightness = store.get('ledBrightness') as number;
  gpioManager.setLedBrightness(brightness);

  logger.info('main', `Sound-Pi started (git: ${GIT_COMMIT}, dev: ${isDev})`);
}

function registerIpcHandlers() {
  // ── Renderer logging ─────────────────────────────────────
  ipcMain.on('renderer-log', (_event, level: string, ...args: unknown[]) => {
    const message = args.map((a) => (typeof a === 'string' ? a : String(a))).join(' ');
    if (level === 'error') {
      logger.error('renderer', message);
    } else if (level === 'warn') {
      logger.warn('renderer', message);
    } else {
      logger.info('renderer', message);
    }
  });

  // ── Audio ────────────────────────────────────────────────
  ipcMain.handle('audio:get-output-devices', async () => {
    return await pipewireManager.getOutputDevices();
  });

  ipcMain.handle('audio:set-output-volume', async (_event, deviceId: string, volume: number) => {
    await pipewireManager.setOutputVolume(deviceId, volume);
  });

  ipcMain.handle('audio:set-master-volume', async (_event, volume: number) => {
    await pipewireManager.setMasterVolume(volume);
    store.set('masterVolume', volume);
  });

  ipcMain.handle('audio:get-master-volume', async () => {
    return store.get('masterVolume') as number;
  });

  ipcMain.handle('audio:set-mute', async (_event, muted: boolean) => {
    await pipewireManager.setMute(muted);
    store.set('muted', muted);
  });

  ipcMain.handle('audio:get-mute', async () => {
    return store.get('muted') as boolean;
  });

  ipcMain.handle('audio:set-input-mix', async (_event, usbVolume: number, browserVolume: number) => {
    await pipewireManager.setInputMix(usbVolume, browserVolume);
    store.set('inputMix', { usbVolume, browserVolume });
  });

  // ── USB HID Transport ────────────────────────────────────
  ipcMain.on('hid:play-pause', () => {
    hidController.sendPlayPause();
  });

  ipcMain.on('hid:next', () => {
    hidController.sendNext();
  });

  ipcMain.on('hid:prev', () => {
    hidController.sendPrev();
  });

  // ── Bluetooth ────────────────────────────────────────────
  ipcMain.handle('bt:scan', async () => {
    return await bluetoothManager.scan();
  });

  ipcMain.handle('bt:pair', async (_event, address: string) => {
    return await bluetoothManager.pair(address);
  });

  ipcMain.handle('bt:connect', async (_event, address: string) => {
    return await bluetoothManager.connect(address);
  });

  ipcMain.handle('bt:disconnect', async (_event, address: string) => {
    return await bluetoothManager.disconnect(address);
  });

  ipcMain.handle('bt:remove', async (_event, address: string) => {
    return await bluetoothManager.remove(address);
  });

  ipcMain.handle('bt:get-devices', async () => {
    return await bluetoothManager.getDevices();
  });

  // ── WiFi ─────────────────────────────────────────────────
  ipcMain.handle('wifi:scan', async () => {
    return await wifiManager.scan();
  });

  ipcMain.handle('wifi:connect', async (_event, ssid: string, password: string) => {
    return await wifiManager.connect(ssid, password);
  });

  ipcMain.handle('wifi:disconnect', async () => {
    return await wifiManager.disconnect();
  });

  ipcMain.handle('wifi:get-status', async () => {
    const ssid = await wifiManager.getCurrentSsid();
    return { connected: ssid !== null, ssid };
  });

  // ── GPIO ─────────────────────────────────────────────────
  ipcMain.on('gpio:set-led-brightness', (_event, value: number) => {
    gpioManager.setLedBrightness(value);
    store.set('ledBrightness', value);
  });

  ipcMain.on('gpio:set-led-pattern', (_event, pattern: string) => {
    gpioManager.setLedPattern(pattern);
  });

  // ── System ───────────────────────────────────────────────
  ipcMain.handle('system:shutdown', async () => {
    logger.info('main', 'Shutdown requested');
    try { execSync('sudo shutdown -h now'); } catch { /* ignore */ }
  });

  ipcMain.handle('system:reboot', async () => {
    logger.info('main', 'Reboot requested');
    try { execSync('sudo reboot'); } catch { /* ignore */ }
  });

  ipcMain.handle('system:get-info', async () => {
    return {
      cpuPercent: getCpuUsagePercent(),
      loadAvg: getLoadAvg(),
      memAvailableMB: Math.round(getAvailableMemoryMB()),
      cpuTempC: getCpuTempC(),
    };
  });
}

// ── App lifecycle ────────────────────────────────────────────
app.whenReady().then(() => {
  createWindow();
  setupManagers();
  registerIpcHandlers();
});

app.on('window-all-closed', () => {
  gpioManager?.dispose();
  audioCapture?.stop();
  app.quit();
});

app.on('activate', () => {
  if (BrowserWindow.getAllWindows().length === 0) {
    createWindow();
  }
});
