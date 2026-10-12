import React from 'react';
import type { SettingsState } from '../../types/call';

interface RuleEditorProps {
  settings: SettingsState;
  onToggleManual: (enabled: boolean) => Promise<void>;
  disabled?: boolean;
}

export default function RuleEditor({ settings, onToggleManual, disabled }: RuleEditorProps) {
  return (
    <div className="panel rule-editor-panel" aria-labelledby="preferences-heading">
      <div className="panel-header">
        <div>
          <h2 id="preferences-heading">Agent Mode & Screening Policies</h2>
          <p className="muted">
            Control manual mode override, fraud defense parameters, and autonomous handling behaviors.
          </p>
        </div>
      </div>

      <div className="preferences-grid">
        <div className="preference-card highlight-card">
          <div className="preference-card-header">
            <div>
              <h3>Manual Agent Mode</h3>
              <p className="subtle">
                When ON, the AI assistant immediately handles and screens all incoming calls, overriding schedules.
              </p>
            </div>
            <label className="switch-toggle" aria-label="Toggle Manual Agent Mode">
              <input
                type="checkbox"
                checked={settings.manual_enabled}
                onChange={(e) => void onToggleManual(e.target.checked)}
                disabled={disabled}
              />
              <span className="slider round" />
            </label>
          </div>
          <div className="status-indicator-row">
            <span className={`status-dot ${settings.manual_enabled ? 'dot-active' : 'dot-idle'}`} />
            <strong>{settings.manual_enabled ? 'Agent Active (Screening All Calls)' : 'Manual Mode Off (Following Schedule / Ringing Phone)'}</strong>
          </div>
        </div>

        <div className="preference-card">
          <h3>Spam & Fraud Defense Rules</h3>
          <ul className="policy-list">
            <li>
              <span className="policy-badge shield-badge">🛡️ Credential Phishing Block</span>
              <p className="subtle">Never collect, verify, or transfer calls requesting OTP, 2FA, or bank credentials.</p>
            </li>
            <li>
              <span className="policy-badge shield-badge">🚫 Telemarketing & Robocall Filter</span>
              <p className="subtle">Auto-detects automated warranty pitches, pre-approved loans, and cold sales pitches.</p>
            </li>
            <li>
              <span className="policy-badge shield-badge">⚠️ Pressure Tactic Interception</span>
              <p className="subtle">Arrest warrant and urgent legal threats are flagged and prevented from transferring.</p>
            </li>
          </ul>
        </div>

        <div className="preference-card">
          <h3>Autonomous Resolution Behaviors</h3>
          <ul className="policy-list">
            <li>
              <strong>📦 Delivery Handling:</strong>
              <p className="subtle">Directs couriers to leave packages at the doorstep and takes carrier note.</p>
            </li>
            <li>
              <strong>🚨 Urgent Escalation:</strong>
              <p className="subtle">Emergencies and verified VIPs dial the owner phone via native telephony.</p>
            </li>
            <li>
              <strong>📝 Structured Messaging:</strong>
              <p className="subtle">Summarizes routine calls with caller identity, purpose, and callback request.</p>
            </li>
          </ul>
        </div>
      </div>
    </div>
  );
}
