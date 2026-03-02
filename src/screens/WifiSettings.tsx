import React, { useState, useCallback, useEffect } from 'react';
import type { WiFiNetwork, WiFiStatus } from '../types/api';

export const WifiSettings: React.FC = () => {
  const [networks, setNetworks] = useState<WiFiNetwork[]>([]);
  const [scanning, setScanning] = useState(false);
  const [status, setStatus] = useState<WiFiStatus>({ connected: false, ssid: null });
  const [passwordInput, setPasswordInput] = useState('');
  const [selectedSsid, setSelectedSsid] = useState<string | null>(null);
  const [statusText, setStatusText] = useState('');

  useEffect(() => {
    window.soundPiAPI.wifiGetStatus().then(setStatus);
  }, []);

  const handleScan = useCallback(async () => {
    setScanning(true);
    setStatusText('Scanning...');
    try {
      const result = await window.soundPiAPI.wifiScan();
      setNetworks(result);
      setStatusText(`Found ${result.length} networks`);
    } catch {
      setStatusText('Scan failed');
    }
    setScanning(false);
  }, []);

  const handleConnect = useCallback(async () => {
    if (!selectedSsid) return;
    setStatusText('Connecting...');
    const success = await window.soundPiAPI.wifiConnect(selectedSsid, passwordInput);
    if (success) {
      setStatusText('Connected');
      setSelectedSsid(null);
      setPasswordInput('');
      const st = await window.soundPiAPI.wifiGetStatus();
      setStatus(st);
    } else {
      setStatusText('Connection failed');
    }
  }, [selectedSsid, passwordInput]);

  const handleDisconnect = useCallback(async () => {
    setStatusText('Disconnecting...');
    await window.soundPiAPI.wifiDisconnect();
    setStatus({ connected: false, ssid: null });
    setStatusText('Disconnected');
  }, []);

  const signalBars = (signal: number) => {
    if (signal >= 75) return '▂▄▆█';
    if (signal >= 50) return '▂▄▆░';
    if (signal >= 25) return '▂▄░░';
    return '▂░░░';
  };

  return (
    <div className="flex flex-col h-full p-3" style={{ width: 480, height: 320 }}>
      <div className="flex items-center justify-between mb-2">
        <div className="text-xs font-bold text-gray-400">WIFI</div>
        <div className="flex items-center gap-2">
          {status.connected && (
            <button
              className="px-2 py-1 text-xs rounded bg-red-700"
              onClick={handleDisconnect}
            >
              Disconnect
            </button>
          )}
          <button
            className="px-3 py-1 text-xs rounded bg-blue-600 disabled:bg-gray-700"
            onClick={handleScan}
            disabled={scanning}
          >
            {scanning ? 'Scanning...' : 'Scan'}
          </button>
        </div>
      </div>

      {status.connected && (
        <div className="text-xs text-green-400 mb-1">
          Connected: {status.ssid}
        </div>
      )}
      {statusText && (
        <div className="text-xs text-gray-500 mb-1">{statusText}</div>
      )}

      {/* Password input for selected network */}
      {selectedSsid && (
        <div className="flex items-center gap-2 mb-2 p-2 rounded" style={{ background: '#1a1a2e' }}>
          <div className="text-xs text-gray-400 truncate" style={{ maxWidth: 100 }}>{selectedSsid}</div>
          <input
            type="password"
            placeholder="Password"
            value={passwordInput}
            onChange={(e) => setPasswordInput(e.target.value)}
            className="flex-1 px-2 py-1 text-xs rounded bg-gray-800 text-white border border-gray-600"
          />
          <button
            className="px-2 py-1 text-xs rounded bg-blue-600"
            onClick={handleConnect}
          >
            Join
          </button>
          <button
            className="px-2 py-1 text-xs rounded bg-gray-700"
            onClick={() => { setSelectedSsid(null); setPasswordInput(''); }}
          >
            X
          </button>
        </div>
      )}

      <div className="flex-1 overflow-y-auto space-y-1">
        {networks.map((net) => (
          <div
            key={net.ssid}
            className="flex items-center justify-between p-2 rounded cursor-pointer"
            style={{ background: net.connected ? '#0a2e1a' : '#111' }}
            onClick={() => {
              if (!net.connected) {
                setSelectedSsid(net.ssid);
                setPasswordInput('');
              }
            }}
          >
            <div className="flex-1 min-w-0">
              <div className="text-xs truncate">
                {net.connected && <span className="text-green-400 mr-1">●</span>}
                {net.ssid}
              </div>
              <div className="text-xs text-gray-600">{net.security || 'Open'}</div>
            </div>
            <div className="text-xs text-gray-500 font-mono ml-2">
              {signalBars(net.signal)}
            </div>
          </div>
        ))}
        {networks.length === 0 && !scanning && (
          <div className="text-xs text-gray-600 text-center py-8">
            Tap Scan to find networks
          </div>
        )}
      </div>
    </div>
  );
};
