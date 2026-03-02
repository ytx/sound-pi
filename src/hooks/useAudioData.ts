import { useState, useEffect, useRef } from 'react';
import type { AudioData } from '../types/api';

export function useAudioData() {
  const [audioData, setAudioData] = useState<AudioData>({
    levels: [0, 0],
    spectrum: [],
  });
  const dataRef = useRef(audioData);

  useEffect(() => {
    window.soundPiAPI.onAudioData((data: AudioData) => {
      dataRef.current = data;
      setAudioData(data);
    });

    return () => {
      window.soundPiAPI.removeAllListeners();
    };
  }, []);

  return { audioData, audioDataRef: dataRef };
}
