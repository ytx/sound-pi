import React from 'react';
import type { ScreenId } from '../types/api';

interface MenuItem {
  id: ScreenId;
  label: string;
  icon: string;
}

const MENU_ITEMS: MenuItem[] = [
  { id: 'vu-meter', label: 'VU Meter', icon: '🎵' },
  { id: 'dual-vu-meter', label: 'Dual VU', icon: '🎶' },
  { id: 'spectrum', label: 'Spectrum', icon: '📊' },
  { id: 'input-mixer', label: 'Mixer', icon: '🎛' },
  { id: 'bluetooth', label: 'Bluetooth', icon: '📶' },
  { id: 'wifi', label: 'WiFi', icon: '📡' },
];

interface MenuProps {
  currentScreen: ScreenId;
  onSelect: (screen: ScreenId) => void;
  onClose: () => void;
}

export const Menu: React.FC<MenuProps> = ({ currentScreen, onSelect, onClose }) => {
  return (
    <div
      className="absolute inset-0 z-50 flex items-center justify-center"
      style={{ background: 'rgba(0, 0, 0, 0.85)' }}
      onClick={onClose}
    >
      <div
        className="grid gap-2 p-3"
        style={{
          gridTemplateColumns: 'repeat(3, 1fr)',
          gridTemplateRows: 'repeat(2, 1fr)',
          width: 420,
          height: 260,
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {MENU_ITEMS.map((item) => (
          <button
            key={item.id}
            className="flex flex-col items-center justify-center rounded-lg transition-colors"
            style={{
              background: currentScreen === item.id ? '#2563eb' : '#1e293b',
              border: currentScreen === item.id ? '2px solid #3b82f6' : '2px solid #334155',
            }}
            onClick={() => onSelect(item.id)}
          >
            <span className="text-2xl mb-1">{item.icon}</span>
            <span className="text-xs font-medium">{item.label}</span>
          </button>
        ))}
      </div>
    </div>
  );
};
