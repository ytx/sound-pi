import { execFile } from 'child_process';
import { logger } from '../utils/logger';

interface WiFiNetwork {
  ssid: string;
  signal: number;
  security: string;
  connected: boolean;
}

function exec(cmd: string, args: string[], timeoutMs = 15000): Promise<string> {
  return new Promise((resolve, reject) => {
    execFile(cmd, args, { timeout: timeoutMs }, (err, stdout) => {
      if (err) reject(err);
      else resolve(stdout);
    });
  });
}

function parseTerseLine(line: string): string[] {
  const fields: string[] = [];
  let current = '';
  for (let i = 0; i < line.length; i++) {
    if (line[i] === '\\' && i + 1 < line.length && line[i + 1] === ':') {
      current += ':';
      i++;
    } else if (line[i] === ':') {
      fields.push(current);
      current = '';
    } else {
      current += line[i];
    }
  }
  fields.push(current);
  return fields;
}

export class WiFiManager {
  async scan(): Promise<WiFiNetwork[]> {
    try {
      try { await exec('nmcli', ['device', 'wifi', 'rescan'], 10000); } catch { /* ignore */ }
      await new Promise((r) => setTimeout(r, 2000));
      const output = await exec('nmcli', ['-t', '-f', 'SSID,SIGNAL,SECURITY,ACTIVE', 'device', 'wifi', 'list']);
      return this.parseWifiList(output);
    } catch (e) {
      logger.error('wifi', `Scan failed: ${e}`);
      return [];
    }
  }

  async connect(ssid: string, password: string): Promise<boolean> {
    try {
      const args = ['device', 'wifi', 'connect', ssid];
      if (password) {
        args.push('password', password);
      }
      await exec('nmcli', args, 30000);
      return true;
    } catch (e) {
      logger.error('wifi', `Connect failed: ${e}`);
      return false;
    }
  }

  async disconnect(): Promise<boolean> {
    try {
      const dev = await this.getWifiDevice();
      if (!dev) return false;
      await exec('nmcli', ['device', 'disconnect', dev]);
      return true;
    } catch (e) {
      logger.error('wifi', `Disconnect failed: ${e}`);
      return false;
    }
  }

  async getCurrentSsid(): Promise<string | null> {
    try {
      const output = await exec('nmcli', ['-t', '-f', 'ACTIVE,SSID', 'device', 'wifi']);
      for (const line of output.trim().split('\n')) {
        const fields = parseTerseLine(line);
        if (fields[0] === 'yes' && fields[1]) {
          return fields[1];
        }
      }
      return null;
    } catch {
      return null;
    }
  }

  private async getWifiDevice(): Promise<string | null> {
    try {
      const output = await exec('nmcli', ['-t', '-f', 'DEVICE,TYPE', 'device']);
      for (const line of output.trim().split('\n')) {
        const fields = parseTerseLine(line);
        if (fields[1] === 'wifi') return fields[0];
      }
      return null;
    } catch {
      return null;
    }
  }

  private parseWifiList(output: string): WiFiNetwork[] {
    const seen = new Map<string, WiFiNetwork>();
    for (const line of output.trim().split('\n')) {
      if (!line) continue;
      const fields = parseTerseLine(line);
      const ssid = fields[0];
      if (!ssid) continue;
      const signal = parseInt(fields[1], 10) || 0;
      const security = fields[2] || '';
      const connected = fields[3] === 'yes';
      const existing = seen.get(ssid);
      if (!existing || signal > existing.signal) {
        seen.set(ssid, { ssid, signal, security, connected });
      }
    }
    return Array.from(seen.values()).sort((a, b) => b.signal - a.signal);
  }
}
