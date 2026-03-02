export interface OutputDevice {
  id: string;
  name: string;
  volume: number;
}

export interface BTDevice {
  address: string;
  name: string;
  paired: boolean;
  connected: boolean;
  rssi?: number;
}

export interface WiFiNetwork {
  ssid: string;
  signal: number;
  security: string;
  connected: boolean;
}

export interface WiFiStatus {
  connected: boolean;
  ssid: string | null;
}

export interface AudioData {
  levels: [number, number];
  spectrum: number[];
}

export interface SystemInfo {
  cpuPercent: number;
  loadAvg: string;
  memAvailableMB: number;
  cpuTempC: number;
}

export type ScreenId =
  | 'vu-meter'
  | 'dual-vu-meter'
  | 'spectrum'
  | 'input-mixer'
  | 'bluetooth'
  | 'wifi';

export interface SoundPiAPI {
  // Audio
  getOutputDevices(): Promise<OutputDevice[]>;
  setOutputVolume(deviceId: string, volume: number): Promise<void>;
  setMasterVolume(volume: number): Promise<void>;
  getMasterVolume(): Promise<number>;
  setMute(muted: boolean): Promise<void>;
  getMute(): Promise<boolean>;
  setInputMix(usbVolume: number, browserVolume: number): Promise<void>;
  onAudioData(callback: (data: AudioData) => void): void;
  onOutputDevicesChanged(callback: (devices: OutputDevice[]) => void): void;

  // Transport (USB HID)
  sendPlayPause(): void;
  sendNext(): void;
  sendPrev(): void;

  // Bluetooth
  btScan(): Promise<BTDevice[]>;
  btPair(address: string): Promise<{ success: boolean; error?: string }>;
  btConnect(address: string): Promise<{ success: boolean; error?: string }>;
  btDisconnect(address: string): Promise<{ success: boolean; error?: string }>;
  btRemove(address: string): Promise<{ success: boolean; error?: string }>;
  btGetDevices(): Promise<BTDevice[]>;
  onBtDeviceChanged(callback: (devices: BTDevice[]) => void): void;

  // WiFi
  wifiScan(): Promise<WiFiNetwork[]>;
  wifiConnect(ssid: string, password: string): Promise<boolean>;
  wifiDisconnect(): Promise<boolean>;
  wifiGetStatus(): Promise<WiFiStatus>;
  onWifiStatusChanged(callback: (status: WiFiStatus) => void): void;

  // GPIO
  onRotaryTurn(callback: (direction: 'cw' | 'ccw') => void): void;
  onRotaryPress(callback: () => void): void;
  onRotaryLongPress(callback: () => void): void;
  setLedBrightness(value: number): void;
  setLedPattern(pattern: string): void;

  // System
  shutdown(): Promise<void>;
  reboot(): Promise<void>;
  getSystemInfo(): Promise<SystemInfo>;

  // Logging
  logToMain(level: string, ...args: unknown[]): void;

  // Cleanup
  removeAllListeners(): void;
}

declare global {
  const __GIT_COMMIT__: string;
  interface Window {
    soundPiAPI: SoundPiAPI;
  }
}
