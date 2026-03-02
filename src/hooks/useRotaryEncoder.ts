import { useEffect } from 'react';

interface RotaryHandlers {
  onTurn?: (direction: 'cw' | 'ccw') => void;
  onPress?: () => void;
  onLongPress?: () => void;
}

export function useRotaryEncoder({ onTurn, onPress, onLongPress }: RotaryHandlers) {
  useEffect(() => {
    if (onTurn) {
      window.soundPiAPI.onRotaryTurn(onTurn);
    }
    if (onPress) {
      window.soundPiAPI.onRotaryPress(onPress);
    }
    if (onLongPress) {
      window.soundPiAPI.onRotaryLongPress(onLongPress);
    }

    return () => {
      window.soundPiAPI.removeAllListeners();
    };
  }, [onTurn, onPress, onLongPress]);
}
