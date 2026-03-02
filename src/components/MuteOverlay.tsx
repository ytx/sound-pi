import React from 'react';

interface MuteOverlayProps {
  muted: boolean;
  visible: boolean;
}

export const MuteOverlay: React.FC<MuteOverlayProps> = ({ muted, visible }) => {
  if (!visible) return null;

  return (
    <div
      className="absolute z-30 flex items-center justify-center px-6 py-3 rounded-lg"
      style={{
        top: '50%',
        left: '50%',
        transform: 'translate(-50%, -50%)',
        background: muted ? 'rgba(239, 68, 68, 0.9)' : 'rgba(34, 197, 94, 0.9)',
        border: '1px solid rgba(255, 255, 255, 0.2)',
      }}
    >
      <span className="text-lg font-bold">
        {muted ? 'MUTED' : 'UNMUTED'}
      </span>
    </div>
  );
};
