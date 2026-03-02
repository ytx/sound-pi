import React, { useRef, useEffect } from 'react';
import { useAudioData } from '../hooks/useAudioData';

const WIDTH = 480;
const HEIGHT = 320;
const BAR_COUNT = 32;
const BAR_GAP = 2;
const BAR_WIDTH = Math.floor((WIDTH - 20 - BAR_GAP * (BAR_COUNT - 1)) / BAR_COUNT);
const BASE_Y = HEIGHT - 30;
const MAX_BAR_HEIGHT = HEIGHT - 60;

const PEAK_FALL_RATE = 0.02;

export const SpectrumAnalyzer: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { audioDataRef } = useAudioData();
  const peaksRef = useRef<number[]>(new Array(BAR_COUNT).fill(0));
  const smoothRef = useRef<number[]>(new Array(BAR_COUNT).fill(0));
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    const draw = () => {
      const data = audioDataRef.current;
      const spectrum = data.spectrum;
      const peaks = peaksRef.current;
      const smooth = smoothRef.current;

      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      // Title
      ctx.font = '10px monospace';
      ctx.fillStyle = '#444';
      ctx.textAlign = 'center';
      ctx.fillText('SPECTRUM ANALYZER', WIDTH / 2, 15);

      // Map spectrum data to bars
      const startX = 10;

      for (let i = 0; i < BAR_COUNT; i++) {
        // Map spectrum index (may have fewer bins than bars)
        const specIdx = Math.floor((i / BAR_COUNT) * spectrum.length);
        const rawValue = spectrum[specIdx] || 0;

        // Scale to visible range (spectrum values are typically 0-0.5)
        const value = Math.min(rawValue * 4, 1);

        // Smooth
        smooth[i] += (value - smooth[i]) * 0.4;

        const barHeight = smooth[i] * MAX_BAR_HEIGHT;
        const x = startX + i * (BAR_WIDTH + BAR_GAP);

        // Bar gradient
        const gradient = ctx.createLinearGradient(0, BASE_Y, 0, BASE_Y - MAX_BAR_HEIGHT);
        gradient.addColorStop(0, '#22c55e');
        gradient.addColorStop(0.6, '#eab308');
        gradient.addColorStop(1, '#ef4444');
        ctx.fillStyle = gradient;
        ctx.fillRect(x, BASE_Y - barHeight, BAR_WIDTH, barHeight);

        // Peak hold
        if (smooth[i] > peaks[i]) {
          peaks[i] = smooth[i];
        } else {
          peaks[i] = Math.max(0, peaks[i] - PEAK_FALL_RATE);
        }

        const peakY = BASE_Y - peaks[i] * MAX_BAR_HEIGHT;
        ctx.fillStyle = '#fff';
        ctx.fillRect(x, peakY - 2, BAR_WIDTH, 2);
      }

      // Frequency labels
      ctx.font = '9px monospace';
      ctx.fillStyle = '#555';
      ctx.textAlign = 'center';
      const freqLabels = ['50', '100', '200', '500', '1k', '2k', '5k', '10k', '20k'];
      const labelPositions = [0, 0.1, 0.2, 0.35, 0.5, 0.6, 0.75, 0.88, 1];
      for (let i = 0; i < freqLabels.length; i++) {
        const x = startX + labelPositions[i] * (BAR_COUNT * (BAR_WIDTH + BAR_GAP) - BAR_GAP);
        ctx.fillText(freqLabels[i], x, BASE_Y + 15);
      }

      // dB scale on left
      ctx.textAlign = 'right';
      ctx.fillStyle = '#333';
      const dbLabels = ['0', '-6', '-12', '-18', '-24'];
      for (let i = 0; i < dbLabels.length; i++) {
        const y = 30 + i * (MAX_BAR_HEIGHT / (dbLabels.length - 1));
        ctx.fillText(dbLabels[i], startX - 3, y + 3);
        // Grid line
        ctx.strokeStyle = '#1a1a1a';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(startX, y);
        ctx.lineTo(WIDTH - 10, y);
        ctx.stroke();
      }

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [audioDataRef]);

  return <canvas ref={canvasRef} width={WIDTH} height={HEIGHT} />;
};
