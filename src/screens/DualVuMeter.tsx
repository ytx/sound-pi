import React, { useRef, useEffect } from 'react';
import { useAudioData } from '../hooks/useAudioData';

const WIDTH = 480;
const HEIGHT = 320;
const HALF_W = WIDTH / 2;

// Needle parameters for each meter
const NEEDLE_LENGTH = 180;
const MIN_ANGLE = -Math.PI * 0.7;
const MAX_ANGLE = -Math.PI * 0.3;

const ATTACK = 0.3;
const RELEASE = 0.08;

export const DualVuMeter: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { audioDataRef } = useAudioData();
  const needleL = useRef(MIN_ANGLE);
  const needleR = useRef(MIN_ANGLE);
  const peakL = useRef(0);
  const peakR = useRef(0);
  const peakHoldL = useRef(0);
  const peakHoldR = useRef(0);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    function drawMeter(
      cx: number, cy: number,
      level: number,
      needleRef: React.MutableRefObject<number>,
      peakRefVal: React.MutableRefObject<number>,
      peakHoldRefVal: React.MutableRefObject<number>,
      label: string,
    ) {
      const targetAngle = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * Math.min(level * 1.5, 1);
      const current = needleRef.current;

      if (targetAngle > current) {
        needleRef.current += (targetAngle - current) * ATTACK;
      } else {
        needleRef.current += (targetAngle - current) * RELEASE;
      }

      if (level > peakRefVal.current) {
        peakRefVal.current = level;
        peakHoldRefVal.current = 60;
      } else if (peakHoldRefVal.current > 0) {
        peakHoldRefVal.current--;
      } else {
        peakRefVal.current *= 0.98;
      }

      // Scale arc
      ctx.strokeStyle = '#333';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.arc(cx, cy, NEEDLE_LENGTH - 15, MIN_ANGLE, MAX_ANGLE);
      ctx.stroke();

      // Red zone
      const redStart = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * 0.85;
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(cx, cy, NEEDLE_LENGTH - 15, redStart, MAX_ANGLE);
      ctx.stroke();

      // Scale ticks
      const ticks = [0, 0.25, 0.5, 0.65, 0.75, 0.85, 0.93, 1];
      for (const pos of ticks) {
        const angle = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * pos;
        const r1 = NEEDLE_LENGTH - 22;
        const r2 = NEEDLE_LENGTH - 8;
        ctx.strokeStyle = pos >= 0.85 ? '#ef4444' : '#555';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(cx + r1 * Math.cos(angle), cy + r1 * Math.sin(angle));
        ctx.lineTo(cx + r2 * Math.cos(angle), cy + r2 * Math.sin(angle));
        ctx.stroke();
      }

      // Label
      ctx.font = 'bold 14px serif';
      ctx.fillStyle = '#555';
      ctx.textAlign = 'center';
      ctx.fillText(label, cx, 30);

      // Peak indicator
      if (peakRefVal.current > 0.01) {
        const peakAngle = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * Math.min(peakRefVal.current * 1.5, 1);
        const pr = NEEDLE_LENGTH - 10;
        ctx.fillStyle = '#eab308';
        ctx.beginPath();
        ctx.arc(cx + pr * Math.cos(peakAngle), cy + pr * Math.sin(peakAngle), 2, 0, Math.PI * 2);
        ctx.fill();
      }

      // Needle
      const angle = needleRef.current;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.moveTo(cx, cy);
      ctx.lineTo(cx + NEEDLE_LENGTH * Math.cos(angle), cy + NEEDLE_LENGTH * Math.sin(angle));
      ctx.stroke();

      // Pivot
      ctx.fillStyle = '#333';
      ctx.beginPath();
      ctx.arc(cx, cy, 5, 0, Math.PI * 2);
      ctx.fill();
    }

    const draw = () => {
      const data = audioDataRef.current;

      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      // Separator line
      ctx.strokeStyle = '#222';
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(HALF_W, 10);
      ctx.lineTo(HALF_W, HEIGHT - 10);
      ctx.stroke();

      // Left meter
      const lcx = HALF_W / 2;
      const lcy = HEIGHT + 20;
      drawMeter(lcx, lcy, data.levels[0], needleL, peakL, peakHoldL, 'L');

      // Right meter
      const rcx = HALF_W + HALF_W / 2;
      const rcy = HEIGHT + 20;
      drawMeter(rcx, rcy, data.levels[1], needleR, peakR, peakHoldR, 'R');

      // Level bars at bottom
      const barY = HEIGHT - 15;
      const barW = HALF_W - 30;

      // Left bar
      ctx.fillStyle = '#111';
      ctx.fillRect(15, barY, barW, 6);
      const lw = barW * Math.min(data.levels[0], 1);
      ctx.fillStyle = data.levels[0] > 0.85 ? '#ef4444' : data.levels[0] > 0.5 ? '#eab308' : '#22c55e';
      ctx.fillRect(15, barY, lw, 6);

      // Right bar
      ctx.fillStyle = '#111';
      ctx.fillRect(HALF_W + 15, barY, barW, 6);
      const rw = barW * Math.min(data.levels[1], 1);
      ctx.fillStyle = data.levels[1] > 0.85 ? '#ef4444' : data.levels[1] > 0.5 ? '#eab308' : '#22c55e';
      ctx.fillRect(HALF_W + 15, barY, rw, 6);

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [audioDataRef]);

  return <canvas ref={canvasRef} width={WIDTH} height={HEIGHT} />;
};
