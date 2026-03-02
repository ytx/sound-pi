import React from 'react';

interface VolumeOverlayProps {
  volume: number;
  visible: boolean;
}

export const VolumeOverlay: React.FC<VolumeOverlayProps> = ({ volume, visible }) => {
  if (!visible) return null;

  const barWidth = Math.round((volume / 100) * 200);

  return (
    <div
      className="absolute z-30 flex items-center gap-3 px-4 py-2 rounded-lg"
      style={{
        bottom: 20,
        left: '50%',
        transform: 'translateX(-50%)',
        background: 'rgba(0, 0, 0, 0.8)',
        border: '1px solid #334155',
        minWidth: 260,
      }}
    >
      <span className="text-sm font-mono w-8 text-right">{volume}</span>
      <div
        className="relative rounded-full overflow-hidden"
        style={{ width: 200, height: 8, background: '#1e293b' }}
      >
        <div
          className="absolute top-0 left-0 h-full rounded-full transition-all duration-100"
          style={{
            width: barWidth,
            background: volume > 80 ? '#ef4444' : volume > 50 ? '#eab308' : '#22c55e',
          }}
        />
      </div>
    </div>
  );
};
