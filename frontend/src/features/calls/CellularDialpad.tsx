import React, { useState } from 'react';
import { soundEffects } from '../../services/soundEffects';

interface CellularDialpadProps {
  initialNumber?: string;
  onCallInitiated?: (phoneNumber: string) => void;
}

const dialpadKeys = [
  { key: '1', letters: '' },
  { key: '2', letters: 'ABC' },
  { key: '3', letters: 'DEF' },
  { key: '4', letters: 'GHI' },
  { key: '5', letters: 'JKL' },
  { key: '6', letters: 'MNO' },
  { key: '7', letters: 'PQRS' },
  { key: '8', letters: 'TUV' },
  { key: '9', letters: 'WXYZ' },
  { key: '*', letters: '' },
  { key: '0', letters: '+' },
  { key: '#', letters: '' },
];

export default function CellularDialpad({ initialNumber = '', onCallInitiated }: CellularDialpadProps) {
  const [phoneNumber, setPhoneNumber] = useState(initialNumber);

  const handleKeyPress = (digit: string) => {
    soundEffects.playDtmf(digit);
    setPhoneNumber((prev) => prev + digit);
  };

  const handleBackspace = () => {
    setPhoneNumber((prev) => prev.slice(0, -1));
  };

  const handleClear = () => {
    setPhoneNumber('');
  };

  const cleanDigits = phoneNumber.trim().replace(/[^\d+]/g, '');
  const isValid = /^\+?\d{7,15}$/.test(cleanDigits);

  const handleCellularCall = () => {
    if (isValid) {
      soundEffects.playCallConnected();
      onCallInitiated?.(cleanDigits);
      window.location.href = `tel:${encodeURIComponent(cleanDigits)}`;
    }
  };

  return (
    <div className="panel cellular-dialpad-panel" aria-labelledby="dialpad-heading">
      <div className="panel-header">
        <div>
          <h2 id="dialpad-heading">Native Cellular Calling Interface</h2>
          <p className="muted">
            Initiate standard cellular telephone calls using your device's native baseband dialer.
          </p>
        </div>
        <span className="offline-badge" title="Internet connectivity is not required for cellular calls">
          📶 100% Offline Calling
        </span>
      </div>

      <div className="dialpad-container">
        <div className="phone-display-container">
          <input
            type="tel"
            className="dialpad-number-display"
            value={phoneNumber}
            onChange={(e) => setPhoneNumber(e.target.value)}
            placeholder="Enter phone number..."
            aria-label="Phone number to call"
          />
          {phoneNumber && (
            <button
              type="button"
              className="backspace-btn"
              onClick={handleBackspace}
              title="Delete last digit"
              aria-label="Backspace"
            >
              ⌫
            </button>
          )}
        </div>

        <div className="dialpad-grid">
          {dialpadKeys.map(({ key, letters }) => (
            <button
              key={key}
              type="button"
              className="dialpad-btn"
              onClick={() => handleKeyPress(key)}
            >
              <span className="dialpad-key">{key}</span>
              {letters && <span className="dialpad-letters">{letters}</span>}
            </button>
          ))}
        </div>

        <div className="dialpad-actions">
          <button
            type="button"
            className={`cellular-call-btn ${isValid ? 'call-ready' : 'call-disabled'}`}
            onClick={handleCellularCall}
            disabled={!isValid}
            aria-label="Initiate native cellular call"
          >
            <span className="call-icon">📞</span> Call via Cellular
          </button>
          {phoneNumber && (
            <button type="button" className="secondary small-btn" onClick={handleClear}>
              Clear
            </button>
          )}
        </div>
      </div>

      <div className="carrier-forwarding-note">
        <strong>💡 Carrier Telephony Integration Note:</strong>
        <p className="subtle">
          Standard cellular calls connect through your mobile network SIM and do not consume data or internet bandwidth.
          To route unanswered cellular calls to this AI agent, configure conditional forwarding on your SIM:
          <br />
          <code>*67*&lt;DID&gt;#</code> (Forward when Busy) · <code>*61*&lt;DID&gt;#</code> (Forward when Unanswered).
        </p>
      </div>
    </div>
  );
}
