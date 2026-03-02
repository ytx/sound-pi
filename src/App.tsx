import { useState, useCallback } from 'react';
import type { ScreenId } from './types/api';
import { useVolume } from './hooks/useVolume';
import { useRotaryEncoder } from './hooks/useRotaryEncoder';
import { MenuTrigger } from './components/MenuTrigger';
import { Menu } from './components/Menu';
import { VolumeOverlay } from './components/VolumeOverlay';
import { MuteOverlay } from './components/MuteOverlay';
import { VuMeter } from './screens/VuMeter';
import { DualVuMeter } from './screens/DualVuMeter';
import { SpectrumAnalyzer } from './screens/SpectrumAnalyzer';
import { InputMixer } from './screens/InputMixer';
import { BluetoothSettings } from './screens/BluetoothSettings';
import { WifiSettings } from './screens/WifiSettings';

const VOLUME_STEP = 5;

function App() {
  const [currentScreen, setCurrentScreen] = useState<ScreenId>('vu-meter');
  const [menuOpen, setMenuOpen] = useState(false);

  const { volume, muted, showVolumeOverlay, showMuteOverlay, changeVolume, toggleMute } = useVolume();

  const handleRotaryTurn = useCallback((direction: 'cw' | 'ccw') => {
    changeVolume(direction === 'cw' ? VOLUME_STEP : -VOLUME_STEP);
  }, [changeVolume]);

  const handleRotaryPress = useCallback(() => {
    // Short press → Play/Pause
    window.soundPiAPI.sendPlayPause();
  }, []);

  const handleRotaryLongPress = useCallback(() => {
    toggleMute();
  }, [toggleMute]);

  useRotaryEncoder({
    onTurn: handleRotaryTurn,
    onPress: handleRotaryPress,
    onLongPress: handleRotaryLongPress,
  });

  const handleMenuSelect = useCallback((screen: ScreenId) => {
    setCurrentScreen(screen);
    setMenuOpen(false);
  }, []);

  const renderScreen = () => {
    switch (currentScreen) {
      case 'vu-meter':
        return <VuMeter />;
      case 'dual-vu-meter':
        return <DualVuMeter />;
      case 'spectrum':
        return <SpectrumAnalyzer />;
      case 'input-mixer':
        return <InputMixer />;
      case 'bluetooth':
        return <BluetoothSettings />;
      case 'wifi':
        return <WifiSettings />;
      default:
        return <VuMeter />;
    }
  };

  return (
    <div className="relative" style={{ width: 480, height: 320 }}>
      {renderScreen()}

      <MenuTrigger onTap={() => setMenuOpen(!menuOpen)} />

      {menuOpen && (
        <Menu
          currentScreen={currentScreen}
          onSelect={handleMenuSelect}
          onClose={() => setMenuOpen(false)}
        />
      )}

      <VolumeOverlay volume={volume} visible={showVolumeOverlay && !menuOpen} />
      <MuteOverlay muted={muted} visible={showMuteOverlay && !menuOpen} />
    </div>
  );
}

export default App;
