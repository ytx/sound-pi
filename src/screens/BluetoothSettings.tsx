import React, { useState, useCallback } from 'react';
import type { BTDevice } from '../types/api';

export const BluetoothSettings: React.FC = () => {
  const [devices, setDevices] = useState<BTDevice[]>([]);
  const [scanning, setScanning] = useState(false);
  const [status, setStatus] = useState('');

  const handleScan = useCallback(async () => {
    setScanning(true);
    setStatus('Scanning...');
    try {
      const result = await window.soundPiAPI.btScan();
      setDevices(result);
      setStatus(`Found ${result.length} devices`);
    } catch {
      setStatus('Scan failed');
    }
    setScanning(false);
  }, []);

  const handleConnect = useCallback(async (address: string) => {
    setStatus('Connecting...');
    const result = await window.soundPiAPI.btConnect(address);
    if (result.success) {
      setStatus('Connected');
      const updated = await window.soundPiAPI.btGetDevices();
      setDevices(updated);
    } else {
      setStatus(result.error || 'Connect failed');
    }
  }, []);

  const handleDisconnect = useCallback(async (address: string) => {
    setStatus('Disconnecting...');
    const result = await window.soundPiAPI.btDisconnect(address);
    if (result.success) {
      setStatus('Disconnected');
      const updated = await window.soundPiAPI.btGetDevices();
      setDevices(updated);
    } else {
      setStatus(result.error || 'Disconnect failed');
    }
  }, []);

  const handlePair = useCallback(async (address: string) => {
    setStatus('Pairing...');
    const result = await window.soundPiAPI.btPair(address);
    if (result.success) {
      setStatus('Paired');
      const updated = await window.soundPiAPI.btGetDevices();
      setDevices(updated);
    } else {
      setStatus(result.error || 'Pair failed');
    }
  }, []);

  const handleRemove = useCallback(async (address: string) => {
    setStatus('Removing...');
    const result = await window.soundPiAPI.btRemove(address);
    if (result.success) {
      setStatus('Removed');
      const updated = await window.soundPiAPI.btGetDevices();
      setDevices(updated);
    } else {
      setStatus(result.error || 'Remove failed');
    }
  }, []);

  return (
    <div className="flex flex-col h-full p-3" style={{ width: 480, height: 320 }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-bold text-gray-400">BLUETOOTH</div>
        <button
          className="px-3 py-1 text-xs rounded bg-blue-600 disabled:bg-gray-700"
          onClick={handleScan}
          disabled={scanning}
        >
          {scanning ? 'Scanning...' : 'Scan'}
        </button>
      </div>

      {status && (
        <div className="text-xs text-gray-500 mb-2">{status}</div>
      )}

      <div className="flex-1 overflow-y-auto space-y-1">
        {devices.map((device) => (
          <div
            key={device.address}
            className="flex items-center justify-between p-2 rounded"
            style={{ background: '#111' }}
          >
            <div className="flex-1 min-w-0">
              <div className="text-xs truncate">{device.name}</div>
              <div className="text-xs text-gray-600 font-mono">{device.address}</div>
            </div>
            <div className="flex items-center gap-1 ml-2">
              {device.connected ? (
                <span className="w-2 h-2 rounded-full bg-green-500 mr-1" />
              ) : device.paired ? (
                <span className="w-2 h-2 rounded-full bg-yellow-500 mr-1" />
              ) : null}

              {device.connected ? (
                <button
                  className="px-2 py-1 text-xs rounded bg-red-700"
                  onClick={() => handleDisconnect(device.address)}
                >
                  Disconnect
                </button>
              ) : device.paired ? (
                <>
                  <button
                    className="px-2 py-1 text-xs rounded bg-blue-700"
                    onClick={() => handleConnect(device.address)}
                  >
                    Connect
                  </button>
                  <button
                    className="px-2 py-1 text-xs rounded bg-gray-700"
                    onClick={() => handleRemove(device.address)}
                  >
                    Remove
                  </button>
                </>
              ) : (
                <button
                  className="px-2 py-1 text-xs rounded bg-blue-700"
                  onClick={() => handlePair(device.address)}
                >
                  Pair
                </button>
              )}
            </div>
          </div>
        ))}
        {devices.length === 0 && !scanning && (
          <div className="text-xs text-gray-600 text-center py-8">
            Tap Scan to find devices
          </div>
        )}
      </div>
    </div>
  );
};
