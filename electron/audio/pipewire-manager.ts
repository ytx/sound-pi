import { execFile } from 'child_process';
import { logger } from '../utils/logger';

interface OutputDevice {
  id: string;
  name: string;
  volume: number;
}

function exec(cmd: string, args: string[], timeoutMs = 5000): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, { timeout: timeoutMs }, (err, stdout, stderr) => {
      if (err) {
        const detail = stderr?.trim() || stdout?.trim() || err.message;
        reject(new Error(detail));
      } else {
        resolve(stdout);
      }
    });
  });
}

export class PipeWireManager {
  async getOutputDevices(): Promise<OutputDevice[]> {
    try {
      // List sinks via wpctl
      const output = await exec('wpctl', ['status']);
      const devices: OutputDevice[] = [];

      // Parse the Audio > Sinks section
      const lines = output.split('\n');
      let inSinks = false;

      for (const line of lines) {
        if (/Sinks:/.test(line)) {
          inSinks = true;
          continue;
        }
        if (inSinks && /^\s*\S.*:/.test(line) && !/^\s*[│├└*]/.test(line)) {
          // New section header — stop
          break;
        }
        if (!inSinks) continue;

        // Lines like: " *  47. alsa_output.usb-... [vol: 0.80]"
        //             "    48. alsa_output.pci-... [vol: 1.00]"
        const match = line.match(/[*\s]\s+(\d+)\.\s+(.+?)(?:\s+\[vol:\s+([\d.]+)\])?$/);
        if (match) {
          devices.push({
            id: match[1],
            name: match[2].trim(),
            volume: match[3] ? Math.round(parseFloat(match[3]) * 100) : 100,
          });
        }
      }

      return devices;
    } catch (e) {
      logger.error('pipewire', `getOutputDevices failed: ${e}`);
      return [];
    }
  }

  async setOutputVolume(deviceId: string, volume: number): Promise<void> {
    const vol = Math.max(0, Math.min(150, volume)) / 100;
    try {
      await exec('wpctl', ['set-volume', deviceId, vol.toFixed(2)]);
    } catch (e) {
      logger.error('pipewire', `setOutputVolume(${deviceId}, ${volume}) failed: ${e}`);
    }
  }

  async setMasterVolume(volume: number): Promise<void> {
    const vol = Math.max(0, Math.min(150, volume)) / 100;
    try {
      await exec('wpctl', ['set-volume', '@DEFAULT_AUDIO_SINK@', vol.toFixed(2)]);
    } catch (e) {
      logger.error('pipewire', `setMasterVolume(${volume}) failed: ${e}`);
    }
  }

  async getMasterVolume(): Promise<number> {
    try {
      const output = await exec('wpctl', ['get-volume', '@DEFAULT_AUDIO_SINK@']);
      // Output: "Volume: 0.80" or "Volume: 0.80 [MUTED]"
      const match = output.match(/Volume:\s+([\d.]+)/);
      if (match) return Math.round(parseFloat(match[1]) * 100);
    } catch (e) {
      logger.error('pipewire', `getMasterVolume failed: ${e}`);
    }
    return 100;
  }

  async setMute(muted: boolean): Promise<void> {
    try {
      await exec('wpctl', ['set-mute', '@DEFAULT_AUDIO_SINK@', muted ? '1' : '0']);
    } catch (e) {
      logger.error('pipewire', `setMute(${muted}) failed: ${e}`);
    }
  }

  async getMute(): Promise<boolean> {
    try {
      const output = await exec('wpctl', ['get-volume', '@DEFAULT_AUDIO_SINK@']);
      return /\[MUTED\]/.test(output);
    } catch {
      return false;
    }
  }

  async setInputMix(usbVolume: number, browserVolume: number): Promise<void> {
    try {
      // Find USB audio input source and set its volume
      const devices = await this.getInputSources();
      for (const dev of devices) {
        if (/usb/i.test(dev.name)) {
          const vol = Math.max(0, Math.min(150, usbVolume)) / 100;
          await exec('wpctl', ['set-volume', dev.id, vol.toFixed(2)]);
        }
      }
      // Browser volume is typically controlled via the application's own volume
      // which PipeWire handles per-stream
      logger.info('pipewire', `Input mix: USB=${usbVolume}%, Browser=${browserVolume}%`);
    } catch (e) {
      logger.error('pipewire', `setInputMix failed: ${e}`);
    }
  }

  private async getInputSources(): Promise<{ id: string; name: string }[]> {
    try {
      const output = await exec('wpctl', ['status']);
      const sources: { id: string; name: string }[] = [];
      const lines = output.split('\n');
      let inSources = false;

      for (const line of lines) {
        if (/Sources:/.test(line)) {
          inSources = true;
          continue;
        }
        if (inSources && /^\s*\S.*:/.test(line) && !/^\s*[│├└*]/.test(line)) {
          break;
        }
        if (!inSources) continue;

        const match = line.match(/[*\s]\s+(\d+)\.\s+(.+?)(?:\s+\[.*\])?$/);
        if (match) {
          sources.push({ id: match[1], name: match[2].trim() });
        }
      }
      return sources;
    } catch {
      return [];
    }
  }
}
