import React from 'react';

interface MenuTriggerProps {
  onTap: () => void;
}

export const MenuTrigger: React.FC<MenuTriggerProps> = ({ onTap }) => {
  return (
    <div
      className="absolute top-0 left-0 z-40"
      style={{ width: 100, height: 100 }}
      onClick={onTap}
    />
  );
};
