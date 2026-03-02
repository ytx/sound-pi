import { execSync, spawn, ChildProcess } from 'child_process';
import fs from 'fs';
import { logger } from '../utils/logger';

// GPIO pin assignments
const GPIO_CHIP = 'gpiochip0';
const PIN_CLK = 19;  // Rotary encoder CLK
const PIN_DT = 20;   // Rotary encoder DT
const PIN_SW = 26;   // Rotary encoder switch

// Hardware PWM via sysfs (requires dtoverlay=pwm,pin=13,func=4)
const PWM_CHIP = '/sys/class/pwm/pwmchip0';
const PWM_CHANNEL = '1';  // GPIO13 = PWM1
const PWM_PERIOD_NS = 1000000; // 1kHz

const LONG_PRESS_MS = 800;
const SHORT_PRESS_MAX_MS = 300;

type RotaryCallback = (direction: 'cw' | 'ccw') => void;
type PressCallback = () => void;

function hasGpiomon(): boolean {
  try {
    execSync('which gpiomon', { stdio: 'pipe' });
    return true;
  } catch {
    return false;
  }
}

export class GpioManager {
  private accessible: boolean;
  private monProcess: ChildProcess | null = null;
  private rotaryCallbacks: RotaryCallback[] = [];
  private pressCallbacks: PressCallback[] = [];
  private longPressCallbacks: PressCallback[] = [];
  private pwmExported = false;

  // Rotary encoder state
  private lastClk = 1;

  // Switch state
  private switchPressedAt = 0;
  private longPressTimer: ReturnType<typeof setTimeout> | null = null;
  private longPressFired = false;

  constructor() {
    this.accessible = hasGpiomon();
    if (!this.accessible) {
      logger.warn('gpio', 'gpiomon not found — GPIO disabled');
    }
  }

  setup(): void {
    if (!this.accessible) {
      logger.info('gpio', 'GPIO setup skipped (stub mode)');
      return;
    }

    // Read initial CLK state
    try {
      const val = execSync(`gpioget -c ${GPIO_CHIP} ${PIN_CLK}`, { encoding: 'utf-8', stdio: ['pipe', 'pipe', 'pipe'] });
      this.lastClk = parseInt(val.trim(), 10) || 1;
    } catch {
      this.lastClk = 1;
    }

    // Start gpiomon for encoder + switch
    this.startMonitor();

    // Setup hardware PWM for LED
    this.setupPwm();

    logger.info('gpio', `GPIO setup complete (CLK=${PIN_CLK}, DT=${PIN_DT}, SW=${PIN_SW}, PWM=${PWM_CHANNEL})`);
  }

  private startMonitor(): void {
    // gpiomon -c gpiochip0 -e both --debounce-period 2ms <CLK> <DT> <SW>
    const args = [
      '-c', GPIO_CHIP,
      '-e', 'both',
      '--debounce-period', '2ms',
      String(PIN_CLK), String(PIN_DT), String(PIN_SW),
    ];
    logger.info('gpio', `Starting: gpiomon ${args.join(' ')}`);

    const proc = spawn('gpiomon', args, { stdio: ['ignore', 'pipe', 'pipe'] });
    this.monProcess = proc;

    proc.stdout?.on('data', (chunk: Buffer) => {
      const lines = chunk.toString().split('\n');
      for (const line of lines) {
        // gpiomon v2 output: "<timestamp>\t<edge>\t<chip> <offset>"
        const match = line.match(/\t(rising|falling)\t\S+\s+(\d+)/);
        if (!match) continue;
        const value = match[1] === 'rising' ? 1 : 0;
        const pin = parseInt(match[2], 10);

        if (pin === PIN_CLK) {
          this.handleClkEdge(value);
        } else if (pin === PIN_SW) {
          this.handleSwitch(value);
        }
        // PIN_DT edges are ignored; DT is read on-demand when CLK fires
      }
    });

    proc.stderr?.on('data', (chunk: Buffer) => {
      logger.error('gpio', `gpiomon stderr: ${chunk.toString().trim()}`);
    });

    proc.on('exit', (code) => {
      if (this.monProcess === proc) {
        logger.warn('gpio', `gpiomon exited with code ${code}`);
        this.monProcess = null;
      }
    });
  }

  private handleClkEdge(clkValue: number): void {
    // On CLK falling edge, read DT to determine direction
    if (clkValue === 0 && this.lastClk === 1) {
      let dt = 1;
      try {
        const val = execSync(`gpioget -c ${GPIO_CHIP} ${PIN_DT}`, {
          encoding: 'utf-8',
          stdio: ['pipe', 'pipe', 'pipe'],
        });
        dt = parseInt(val.trim(), 10) || 1;
      } catch { /* default dt=1 */ }

      const direction: 'cw' | 'ccw' = dt === 1 ? 'cw' : 'ccw';
      for (const cb of this.rotaryCallbacks) cb(direction);
    }
    this.lastClk = clkValue;
  }

  private handleSwitch(value: number): void {
    if (value === 0) {
      // Button pressed (active low)
      this.switchPressedAt = Date.now();
      this.longPressFired = false;
      this.longPressTimer = setTimeout(() => {
        this.longPressFired = true;
        for (const cb of this.longPressCallbacks) cb();
      }, LONG_PRESS_MS);
    } else {
      // Button released
      if (this.longPressTimer) {
        clearTimeout(this.longPressTimer);
        this.longPressTimer = null;
      }
      if (!this.longPressFired && this.switchPressedAt > 0) {
        const duration = Date.now() - this.switchPressedAt;
        if (duration < SHORT_PRESS_MAX_MS) {
          for (const cb of this.pressCallbacks) cb();
        }
      }
      this.switchPressedAt = 0;
    }
  }

  // ── Hardware PWM via sysfs ─────────────────────────────────

  private setupPwm(): void {
    const channelPath = `${PWM_CHIP}/pwm${PWM_CHANNEL}`;

    // Export PWM channel if not already exported
    if (!fs.existsSync(channelPath)) {
      try {
        fs.writeFileSync(`${PWM_CHIP}/export`, PWM_CHANNEL);
        // Wait briefly for sysfs to create the directory
        for (let i = 0; i < 10; i++) {
          if (fs.existsSync(channelPath)) break;
          execSync('sleep 0.05', { stdio: 'pipe' });
        }
      } catch (e) {
        logger.warn('gpio', `PWM export failed (dtoverlay=pwm may not be configured): ${e}`);
        return;
      }
    }

    try {
      fs.writeFileSync(`${channelPath}/period`, String(PWM_PERIOD_NS));
      fs.writeFileSync(`${channelPath}/duty_cycle`, '0');
      fs.writeFileSync(`${channelPath}/enable`, '1');
      this.pwmExported = true;
      logger.info('gpio', 'Hardware PWM initialized');
    } catch (e) {
      logger.warn('gpio', `PWM setup failed: ${e}`);
    }
  }

  setLedBrightness(value: number): void {
    if (!this.pwmExported) return;
    const clamped = Math.max(0, Math.min(255, Math.round(value)));
    const dutyCycle = Math.round((clamped / 255) * PWM_PERIOD_NS);
    const channelPath = `${PWM_CHIP}/pwm${PWM_CHANNEL}`;
    try {
      fs.writeFileSync(`${channelPath}/duty_cycle`, String(dutyCycle));
    } catch (e) {
      logger.error('gpio', `Failed to set LED brightness: ${e}`);
    }
  }

  setLedPattern(_pattern: string): void {
    // TODO: implement breathe/pulse patterns via timer
    logger.info('gpio', `LED pattern: ${_pattern} (not yet implemented)`);
  }

  // ── Callbacks ──────────────────────────────────────────────

  onRotaryTurn(callback: RotaryCallback): () => void {
    this.rotaryCallbacks.push(callback);
    return () => { this.rotaryCallbacks = this.rotaryCallbacks.filter((cb) => cb !== callback); };
  }

  onPress(callback: PressCallback): () => void {
    this.pressCallbacks.push(callback);
    return () => { this.pressCallbacks = this.pressCallbacks.filter((cb) => cb !== callback); };
  }

  onLongPress(callback: PressCallback): () => void {
    this.longPressCallbacks.push(callback);
    return () => { this.longPressCallbacks = this.longPressCallbacks.filter((cb) => cb !== callback); };
  }

  dispose(): void {
    if (this.monProcess) {
      this.monProcess.kill();
      this.monProcess = null;
    }
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
    }
    // Disable PWM
    if (this.pwmExported) {
      const channelPath = `${PWM_CHIP}/pwm${PWM_CHANNEL}`;
      try { fs.writeFileSync(`${channelPath}/enable`, '0'); } catch { /* ignore */ }
    }
    this.rotaryCallbacks = [];
    this.pressCallbacks = [];
    this.longPressCallbacks = [];
    logger.info('gpio', 'GPIO disposed');
  }
}
