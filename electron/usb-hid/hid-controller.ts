import fs from 'fs';
import { logger } from '../utils/logger';

// USB HID Consumer Control usage IDs
// Report format: [reportId, usageLow, usageHigh]
const HID_DEVICE = '/dev/hidg0';

// Consumer Control Usage IDs (HID Usage Tables)
const USAGE_PLAY_PAUSE = 0xcd;
const USAGE_NEXT_TRACK = 0xb5;
const USAGE_PREV_TRACK = 0xb6;

export class HidController {
  private available: boolean;

  constructor() {
    this.available = fs.existsSync(HID_DEVICE);
    if (!this.available) {
      logger.warn('hid', `${HID_DEVICE} not found — USB HID disabled`);
    }
  }

  sendPlayPause(): void {
    this.sendConsumerControl(USAGE_PLAY_PAUSE);
  }

  sendNext(): void {
    this.sendConsumerControl(USAGE_NEXT_TRACK);
  }

  sendPrev(): void {
    this.sendConsumerControl(USAGE_PREV_TRACK);
  }

  private sendConsumerControl(usage: number): void {
    if (!this.available) return;

    try {
      // Send key press (2-byte LE usage ID)
      const press = Buffer.alloc(2);
      press.writeUInt16LE(usage, 0);
      fs.writeFileSync(HID_DEVICE, press);

      // Send key release (all zeros)
      const release = Buffer.alloc(2);
      fs.writeFileSync(HID_DEVICE, release);
    } catch (e) {
      logger.error('hid', `Failed to send consumer control 0x${usage.toString(16)}: ${e}`);
    }
  }
}
