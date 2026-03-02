import { useState, useEffect, useCallback, useRef } from 'react';

export function useVolume() {
  const [volume, setVolume] = useState(80);
  const [muted, setMuted] = useState(false);
  const [showVolumeOverlay, setShowVolumeOverlay] = useState(false);
  const [showMuteOverlay, setShowMuteOverlay] = useState(false);
  const volumeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const muteTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Load initial state
    window.soundPiAPI.getMasterVolume().then(setVolume);
    window.soundPiAPI.getMute().then(setMuted);
  }, []);

  const changeVolume = useCallback((delta: number) => {
    setVolume((prev) => {
      const next = Math.max(0, Math.min(100, prev + delta));
      window.soundPiAPI.setMasterVolume(next);
      return next;
    });

    // Show overlay with auto-hide
    setShowVolumeOverlay(true);
    if (volumeTimerRef.current) clearTimeout(volumeTimerRef.current);
    volumeTimerRef.current = setTimeout(() => {
      setShowVolumeOverlay(false);
    }, 2000);
  }, []);

  const toggleMute = useCallback(() => {
    setMuted((prev) => {
      const next = !prev;
      window.soundPiAPI.setMute(next);

      // Show mute overlay briefly
      setShowMuteOverlay(true);
      if (muteTimerRef.current) clearTimeout(muteTimerRef.current);
      muteTimerRef.current = setTimeout(() => {
        setShowMuteOverlay(false);
      }, 2000);

      return next;
    });
  }, []);

  return {
    volume,
    muted,
    showVolumeOverlay,
    showMuteOverlay,
    changeVolume,
    toggleMute,
  };
}
