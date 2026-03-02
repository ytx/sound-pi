import { contextBridge, ipcRenderer } from 'electron';

const soundPiAPI = {
  // ── Audio ──────────────────────────────────────────────────
  getOutputDevices: (): Promise<{ id: string; name: string; volume: number }[]> =>
    ipcRenderer.invoke('audio:get-output-devices'),
  setOutputVolume: (deviceId: string, volume: number): Promise<void> =>
    ipcRenderer.invoke('audio:set-output-volume', deviceId, volume),
  setMasterVolume: (volume: number): Promise<void> =>
    ipcRenderer.invoke('audio:set-master-volume', volume),
  getMasterVolume: (): Promise<number> =>
    ipcRenderer.invoke('audio:get-master-volume'),
  setMute: (muted: boolean): Promise<void> =>
    ipcRenderer.invoke('audio:set-mute', muted),
  getMute: (): Promise<boolean> =>
    ipcRenderer.invoke('audio:get-mute'),
  setInputMix: (usbVolume: number, browserVolume: number): Promise<void> =>
    ipcRenderer.invoke('audio:set-input-mix', usbVolume, browserVolume),
  onAudioData: (callback: (data: { levels: [number, number]; spectrum: number[] }) => void) => {
    ipcRenderer.on('audio:data', (_event, data) => callback(data));
  },
  onOutputDevicesChanged: (callback: (devices: { id: string; name: string; volume: number }[]) => void) => {
    ipcRenderer.on('audio:devices-changed', (_event, devices) => callback(devices));
  },

  // ── Transport (USB HID) ────────────────────────────────────
  sendPlayPause: (): void => { ipcRenderer.send('hid:play-pause'); },
  sendNext: (): void => { ipcRenderer.send('hid:next'); },
  sendPrev: (): void => { ipcRenderer.send('hid:prev'); },

  // ── Bluetooth ──────────────────────────────────────────────
  btScan: (): Promise<{ address: string; name: string; paired: boolean; connected: boolean; rssi?: number }[]> =>
    ipcRenderer.invoke('bt:scan'),
  btPair: (address: string): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke('bt:pair', address),
  btConnect: (address: string): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke('bt:connect', address),
  btDisconnect: (address: string): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke('bt:disconnect', address),
  btRemove: (address: string): Promise<{ success: boolean; error?: string }> =>
    ipcRenderer.invoke('bt:remove', address),
  btGetDevices: (): Promise<{ address: string; name: string; paired: boolean; connected: boolean }[]> =>
    ipcRenderer.invoke('bt:get-devices'),
  onBtDeviceChanged: (callback: (devices: { address: string; name: string; paired: boolean; connected: boolean }[]) => void) => {
    ipcRenderer.on('bt:device-changed', (_event, devices) => callback(devices));
  },

  // ── WiFi ───────────────────────────────────────────────────
  wifiScan: (): Promise<{ ssid: string; signal: number; security: string; connected: boolean }[]> =>
    ipcRenderer.invoke('wifi:scan'),
  wifiConnect: (ssid: string, password: string): Promise<boolean> =>
    ipcRenderer.invoke('wifi:connect', ssid, password),
  wifiDisconnect: (): Promise<boolean> =>
    ipcRenderer.invoke('wifi:disconnect'),
  wifiGetStatus: (): Promise<{ connected: boolean; ssid: string | null }> =>
    ipcRenderer.invoke('wifi:get-status'),
  onWifiStatusChanged: (callback: (status: { connected: boolean; ssid: string | null }) => void) => {
    ipcRenderer.on('wifi:status-changed', (_event, status) => callback(status));
  },

  // ── GPIO (Rotary Encoder) ─────────────────────────────────
  onRotaryTurn: (callback: (direction: 'cw' | 'ccw') => void) => {
    ipcRenderer.on('gpio:rotary-turn', (_event, direction) => callback(direction));
  },
  onRotaryPress: (callback: () => void) => {
    ipcRenderer.on('gpio:rotary-press', () => callback());
  },
  onRotaryLongPress: (callback: () => void) => {
    ipcRenderer.on('gpio:rotary-long-press', () => callback());
  },
  setLedBrightness: (value: number): void => {
    ipcRenderer.send('gpio:set-led-brightness', value);
  },
  setLedPattern: (pattern: string): void => {
    ipcRenderer.send('gpio:set-led-pattern', pattern);
  },

  // ── System ─────────────────────────────────────────────────
  shutdown: (): Promise<void> => ipcRenderer.invoke('system:shutdown'),
  reboot: (): Promise<void> => ipcRenderer.invoke('system:reboot'),
  getSystemInfo: (): Promise<{ cpuPercent: number; loadAvg: string; memAvailableMB: number; cpuTempC: number }> =>
    ipcRenderer.invoke('system:get-info'),

  // ── Logging ────────────────────────────────────────────────
  logToMain: (level: string, ...args: unknown[]) => {
    ipcRenderer.send('renderer-log', level, ...args);
  },

  // ── Listener cleanup ──────────────────────────────────────
  removeAllListeners: () => {
    ipcRenderer.removeAllListeners('audio:data');
    ipcRenderer.removeAllListeners('audio:devices-changed');
    ipcRenderer.removeAllListeners('bt:device-changed');
    ipcRenderer.removeAllListeners('wifi:status-changed');
    ipcRenderer.removeAllListeners('gpio:rotary-turn');
    ipcRenderer.removeAllListeners('gpio:rotary-press');
    ipcRenderer.removeAllListeners('gpio:rotary-long-press');
  },
};

contextBridge.exposeInMainWorld('soundPiAPI', soundPiAPI);

declare global {
  interface Window {
    soundPiAPI: typeof soundPiAPI;
  }
}
