import { spawn, ChildProcess } from 'child_process';
import { logger } from '../utils/logger';

interface AudioData {
  levels: [number, number]; // L, R peak levels (0-1)
  spectrum: number[];       // FFT magnitude bins
}

type AudioDataCallback = (data: AudioData) => void;

const FFT_SIZE = 64; // 32 bands output
const SAMPLE_RATE = 48000;
const CAPTURE_FPS = 30;
const SAMPLES_PER_FRAME = Math.floor(SAMPLE_RATE / CAPTURE_FPS);

export class AudioCapture {
  private process: ChildProcess | null = null;
  private callbacks: AudioDataCallback[] = [];
  private running = false;

  start(): void {
    if (this.running) return;
    this.running = true;

    // Use pw-cat to capture monitor audio as raw PCM (signed 16-bit LE, stereo)
    // pw-cat --target @DEFAULT_AUDIO_SINK@ --record - captures the monitor/loopback
    this.process = spawn('pw-cat', [
      '--target', '@DEFAULT_AUDIO_SINK@',
      '--record',
      '--format', 's16',
      '--rate', String(SAMPLE_RATE),
      '--channels', '2',
      '-',
    ], {
      stdio: ['ignore', 'pipe', 'pipe'],
    });

    let buffer = Buffer.alloc(0);
    const frameBytes = SAMPLES_PER_FRAME * 2 * 2; // samples * channels * bytesPerSample

    this.process.stdout?.on('data', (chunk: Buffer) => {
      buffer = Buffer.concat([buffer, chunk]);

      while (buffer.length >= frameBytes) {
        const frame = buffer.subarray(0, frameBytes);
        buffer = buffer.subarray(frameBytes);
        this.processFrame(frame);
      }
    });

    this.process.stderr?.on('data', (chunk: Buffer) => {
      const msg = chunk.toString().trim();
      if (msg) logger.warn('audio-capture', msg);
    });

    this.process.on('exit', (code) => {
      logger.warn('audio-capture', `pw-cat exited with code ${code}`);
      this.process = null;
      // Restart if still supposed to be running
      if (this.running) {
        setTimeout(() => this.start(), 2000);
      }
    });

    this.process.on('error', (err) => {
      logger.error('audio-capture', `pw-cat error: ${err.message}`);
      this.process = null;
    });

    logger.info('audio-capture', 'Started audio capture');
  }

  stop(): void {
    this.running = false;
    if (this.process) {
      this.process.kill();
      this.process = null;
    }
  }

  onData(callback: AudioDataCallback): () => void {
    this.callbacks.push(callback);
    return () => {
      this.callbacks = this.callbacks.filter((cb) => cb !== callback);
    };
  }

  private processFrame(frame: Buffer): void {
    if (this.callbacks.length === 0) return;

    const samples = SAMPLES_PER_FRAME;
    const left = new Float32Array(samples);
    const right = new Float32Array(samples);

    // Deinterleave stereo S16LE → float
    for (let i = 0; i < samples; i++) {
      const offset = i * 4;
      left[i] = frame.readInt16LE(offset) / 32768;
      right[i] = frame.readInt16LE(offset + 2) / 32768;
    }

    // Peak levels
    let peakL = 0;
    let peakR = 0;
    for (let i = 0; i < samples; i++) {
      const absL = Math.abs(left[i]);
      const absR = Math.abs(right[i]);
      if (absL > peakL) peakL = absL;
      if (absR > peakR) peakR = absR;
    }

    // Simple FFT (DFT for small bin count)
    // Use mono mix for spectrum
    const mono = new Float32Array(FFT_SIZE);
    const step = Math.floor(samples / FFT_SIZE);
    for (let i = 0; i < FFT_SIZE; i++) {
      mono[i] = (left[i * step] + right[i * step]) / 2;
    }

    const spectrum = this.computeFFT(mono);

    const data: AudioData = {
      levels: [peakL, peakR],
      spectrum: Array.from(spectrum),
    };

    for (const cb of this.callbacks) {
      cb(data);
    }
  }

  private computeFFT(input: Float32Array): Float32Array {
    const N = input.length;
    const half = N / 2;
    const result = new Float32Array(half);

    // Apply Hann window
    const windowed = new Float32Array(N);
    for (let i = 0; i < N; i++) {
      windowed[i] = input[i] * (0.5 - 0.5 * Math.cos((2 * Math.PI * i) / N));
    }

    // Simple DFT (N is small enough)
    for (let k = 0; k < half; k++) {
      let re = 0;
      let im = 0;
      for (let n = 0; n < N; n++) {
        const angle = (2 * Math.PI * k * n) / N;
        re += windowed[n] * Math.cos(angle);
        im -= windowed[n] * Math.sin(angle);
      }
      // Magnitude in dB, normalized
      const mag = Math.sqrt(re * re + im * im) / N;
      result[k] = mag;
    }

    return result;
  }
}
