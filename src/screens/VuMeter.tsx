import React, { useRef, useEffect } from 'react';
import { useAudioData } from '../hooks/useAudioData';

const WIDTH = 480;
const HEIGHT = 320;

// VU meter needle parameters
const CENTER_X = WIDTH / 2;
const CENTER_Y = HEIGHT + 60; // Below screen for arc effect
const NEEDLE_LENGTH = 300;
const MIN_ANGLE = -Math.PI * 0.7; // ~-126 degrees
const MAX_ANGLE = -Math.PI * 0.3; // ~-54 degrees

// Needle physics
const ATTACK = 0.3;
const RELEASE = 0.08;

export const VuMeter: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const { audioDataRef } = useAudioData();
  const needleAngleRef = useRef(MIN_ANGLE);
  const peakRef = useRef(0);
  const peakHoldRef = useRef(0);
  const animRef = useRef<number>(0);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d')!;

    const draw = () => {
      const data = audioDataRef.current;
      // Average L+R for mono VU
      const level = (data.levels[0] + data.levels[1]) / 2;

      // Smooth needle movement (attack/release)
      const targetAngle = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * Math.min(level * 1.5, 1);
      const currentAngle = needleAngleRef.current;

      if (targetAngle > currentAngle) {
        needleAngleRef.current += (targetAngle - currentAngle) * ATTACK;
      } else {
        needleAngleRef.current += (targetAngle - currentAngle) * RELEASE;
      }

      // Peak hold
      if (level > peakRef.current) {
        peakRef.current = level;
        peakHoldRef.current = 60; // frames
      } else if (peakHoldRef.current > 0) {
        peakHoldRef.current--;
      } else {
        peakRef.current *= 0.98;
      }

      // Clear
      ctx.fillStyle = '#0a0a0a';
      ctx.fillRect(0, 0, WIDTH, HEIGHT);

      // Draw scale arc
      ctx.strokeStyle = '#333';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(CENTER_X, CENTER_Y, NEEDLE_LENGTH - 20, MIN_ANGLE, MAX_ANGLE);
      ctx.stroke();

      // Draw scale markings
      const markings = [
        { pos: 0, label: '-20' },
        { pos: 0.25, label: '-10' },
        { pos: 0.5, label: '-7' },
        { pos: 0.65, label: '-5' },
        { pos: 0.75, label: '-3' },
        { pos: 0.85, label: '0' },
        { pos: 0.93, label: '+1' },
        { pos: 1, label: '+3' },
      ];

      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';

      for (const mark of markings) {
        const angle = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * mark.pos;
        const innerR = NEEDLE_LENGTH - 30;
        const outerR = NEEDLE_LENGTH - 10;
        const textR = NEEDLE_LENGTH - 50;

        // Tick mark
        ctx.strokeStyle = mark.pos >= 0.85 ? '#ef4444' : '#666';
        ctx.lineWidth = mark.pos >= 0.85 ? 2 : 1;
        ctx.beginPath();
        ctx.moveTo(
          CENTER_X + innerR * Math.cos(angle),
          CENTER_Y + innerR * Math.sin(angle),
        );
        ctx.lineTo(
          CENTER_X + outerR * Math.cos(angle),
          CENTER_Y + outerR * Math.sin(angle),
        );
        ctx.stroke();

        // Label
        ctx.font = '11px monospace';
        ctx.fillStyle = mark.pos >= 0.85 ? '#ef4444' : '#999';
        ctx.fillText(
          mark.label,
          CENTER_X + textR * Math.cos(angle),
          CENTER_Y + textR * Math.sin(angle),
        );
      }

      // Red zone arc
      const redStart = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * 0.85;
      ctx.strokeStyle = '#ef4444';
      ctx.lineWidth = 3;
      ctx.beginPath();
      ctx.arc(CENTER_X, CENTER_Y, NEEDLE_LENGTH - 20, redStart, MAX_ANGLE);
      ctx.stroke();

      // Draw VU text
      ctx.font = 'bold 24px serif';
      ctx.fillStyle = '#666';
      ctx.textAlign = 'center';
      ctx.fillText('VU', CENTER_X, 60);

      // Peak hold indicator
      if (peakRef.current > 0.01) {
        const peakAngle = MIN_ANGLE + (MAX_ANGLE - MIN_ANGLE) * Math.min(peakRef.current * 1.5, 1);
        const pr = NEEDLE_LENGTH - 15;
        ctx.fillStyle = '#eab308';
        ctx.beginPath();
        ctx.arc(
          CENTER_X + pr * Math.cos(peakAngle),
          CENTER_Y + pr * Math.sin(peakAngle),
          3, 0, Math.PI * 2,
        );
        ctx.fill();
      }

      // Draw needle
      const angle = needleAngleRef.current;
      ctx.strokeStyle = '#fff';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.moveTo(CENTER_X, CENTER_Y);
      ctx.lineTo(
        CENTER_X + NEEDLE_LENGTH * Math.cos(angle),
        CENTER_Y + NEEDLE_LENGTH * Math.sin(angle),
      );
      ctx.stroke();

      // Needle pivot
      ctx.fillStyle = '#333';
      ctx.beginPath();
      ctx.arc(CENTER_X, CENTER_Y, 8, 0, Math.PI * 2);
      ctx.fill();
      ctx.strokeStyle = '#555';
      ctx.lineWidth = 1;
      ctx.stroke();

      // Level bar at bottom
      const barY = HEIGHT - 20;
      const barW = WIDTH - 40;
      ctx.fillStyle = '#111';
      ctx.fillRect(20, barY, barW, 10);
      const levelW = barW * Math.min(level, 1);
      const gradient = ctx.createLinearGradient(20, 0, 20 + barW, 0);
      gradient.addColorStop(0, '#22c55e');
      gradient.addColorStop(0.7, '#eab308');
      gradient.addColorStop(1, '#ef4444');
      ctx.fillStyle = gradient;
      ctx.fillRect(20, barY, levelW, 10);

      animRef.current = requestAnimationFrame(draw);
    };

    animRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(animRef.current);
  }, [audioDataRef]);

  return <canvas ref={canvasRef} width={WIDTH} height={HEIGHT} />;
};
