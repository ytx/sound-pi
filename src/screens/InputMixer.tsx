import React, { useState, useEffect, useCallback } from 'react';
import type { OutputDevice } from '../types/api';

export const InputMixer: React.FC = () => {
  const [usbVolume, setUsbVolume] = useState(100);
  const [browserVolume, setBrowserVolume] = useState(100);
  const [outputDevices, setOutputDevices] = useState<OutputDevice[]>([]);

  useEffect(() => {
    window.soundPiAPI.getOutputDevices().then(setOutputDevices);
    window.soundPiAPI.onOutputDevicesChanged(setOutputDevices);
    return () => { window.soundPiAPI.removeAllListeners(); };
  }, []);

  const handleUsbChange = useCallback((value: number) => {
    setUsbVolume(value);
    window.soundPiAPI.setInputMix(value, browserVolume);
  }, [browserVolume]);

  const handleBrowserChange = useCallback((value: number) => {
    setBrowserVolume(value);
    window.soundPiAPI.setInputMix(usbVolume, value);
  }, [usbVolume]);

  const handleOutputVolume = useCallback((deviceId: string, volume: number) => {
    window.soundPiAPI.setOutputVolume(deviceId, volume);
    setOutputDevices((prev) =>
      prev.map((d) => d.id === deviceId ? { ...d, volume } : d),
    );
  }, []);

  return (
    <div className="flex flex-col h-full p-3" style={{ width: 480, height: 320 }}>
      <div className="text-xs font-bold text-gray-400 mb-2">INPUT MIXER</div>

      {/* Input channels */}
      <div className="flex gap-4 mb-3">
        <div className="flex-1">
          <div className="text-xs text-gray-500 mb-1">USB Audio</div>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={150}
              value={usbVolume}
              onChange={(e) => handleUsbChange(Number(e.target.value))}
              className="flex-1 h-2 appearance-none bg-gray-700 rounded-full"
            />
            <span className="text-xs font-mono w-8 text-right">{usbVolume}</span>
          </div>
        </div>
        <div className="flex-1">
          <div className="text-xs text-gray-500 mb-1">Browser</div>
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={150}
              value={browserVolume}
              onChange={(e) => handleBrowserChange(Number(e.target.value))}
              className="flex-1 h-2 appearance-none bg-gray-700 rounded-full"
            />
            <span className="text-xs font-mono w-8 text-right">{browserVolume}</span>
          </div>
        </div>
      </div>

      {/* Output devices */}
      <div className="text-xs font-bold text-gray-400 mb-2">OUTPUTS</div>
      <div className="flex-1 overflow-y-auto space-y-2">
        {outputDevices.length === 0 && (
          <div className="text-xs text-gray-600 text-center py-4">No output devices</div>
        )}
        {outputDevices.map((device) => (
          <div key={device.id} className="flex items-center gap-2">
            <div className="text-xs text-gray-400 truncate" style={{ width: 120 }}>
              {device.name}
            </div>
            <input
              type="range"
              min={0}
              max={150}
              value={device.volume}
              onChange={(e) => handleOutputVolume(device.id, Number(e.target.value))}
              className="flex-1 h-2 appearance-none bg-gray-700 rounded-full"
            />
            <span className="text-xs font-mono w-8 text-right">{device.volume}</span>
          </div>
        ))}
      </div>
    </div>
  );
};
