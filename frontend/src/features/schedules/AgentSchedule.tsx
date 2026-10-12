import React, { useState } from 'react';
import type { SettingsState } from '../../types/call';

interface AgentScheduleProps {
  settings: SettingsState;
  onSave: (updated: SettingsState) => Promise<void>;
  disabled?: boolean;
}

const weekdayOptions = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

const schedulePresets = [
  {
    name: 'Office Working Hours',
    days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
    start: '09:00',
    end: '17:00',
  },
  {
    name: 'Evening & Night Shield',
    days: weekdayOptions,
    start: '21:00',
    end: '07:00',
  },
  {
    name: 'Weekend Quiet Time',
    days: ['Saturday', 'Sunday'],
    start: '00:00',
    end: '23:59',
  },
  {
    name: '24/7 All-Day Screening',
    days: weekdayOptions,
    start: '00:00',
    end: '23:59',
  },
];

export default function AgentSchedule({ settings, onSave, disabled }: AgentScheduleProps) {
  const [draft, setDraft] = useState<SettingsState>(settings);
  const [saving, setSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState('');

  const handleDayToggle = (day: string) => {
    const current = draft.schedule_days || [];
    const nextDays = current.includes(day)
      ? current.filter((d) => d !== day)
      : [...current, day];
    setDraft({ ...draft, schedule_days: nextDays });
  };

  const handleApplyPreset = (preset: (typeof schedulePresets)[number]) => {
    setDraft({
      ...draft,
      schedule_enabled: true,
      schedule_days: preset.days,
      schedule_start: preset.start,
      schedule_end: preset.end,
    });
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setSaveMessage('');
    try {
      await onSave(draft);
      setSaveMessage('Schedule and agent preferences updated successfully.');
    } catch (err) {
      setSaveMessage(err instanceof Error ? err.message : 'Failed to save settings.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="panel agent-schedule-panel" aria-labelledby="schedule-heading">
      <div className="panel-header">
        <div>
          <h2 id="schedule-heading">Scheduled Agent Mode</h2>
          <p className="muted">
            Configure time windows when the AI assistant automatically screens calls without manual intervention.
          </p>
        </div>
      </div>

      <form onSubmit={handleSave} className="schedule-form">
        <div className="toggle-group-row">
          <label className="checkbox-toggle">
            <input
              type="checkbox"
              checked={draft.schedule_enabled}
              onChange={(e) => setDraft({ ...draft, schedule_enabled: e.target.checked })}
              disabled={disabled}
            />
            <span className="toggle-title">Enable Scheduled Mode</span>
          </label>
        </div>

        {draft.schedule_enabled && (
          <>
            <div className="presets-row">
              <span className="subtle">Quick Presets:</span>
              <div className="preset-chips">
                {schedulePresets.map((preset) => (
                  <button
                    key={preset.name}
                    type="button"
                    className="secondary chip-btn"
                    onClick={() => handleApplyPreset(preset)}
                    disabled={disabled}
                  >
                    {preset.name}
                  </button>
                ))}
              </div>
            </div>

            <div className="schedule-days-selector">
              <label className="section-subtitle">Active Screening Days</label>
              <div className="days-chip-grid">
                {weekdayOptions.map((day) => {
                  const isSelected = (draft.schedule_days || []).includes(day);
                  return (
                    <button
                      key={day}
                      type="button"
                      className={`day-pill ${isSelected ? 'selected' : ''}`}
                      onClick={() => handleDayToggle(day)}
                      disabled={disabled}
                    >
                      {day.slice(0, 3)}
                    </button>
                  );
                })}
              </div>
            </div>

            <div className="time-window-row">
              <label>
                Start Time
                <input
                  type="time"
                  value={draft.schedule_start}
                  onChange={(e) => setDraft({ ...draft, schedule_start: e.target.value })}
                  disabled={disabled}
                  required
                />
              </label>
              <label>
                End Time
                <input
                  type="time"
                  value={draft.schedule_end}
                  onChange={(e) => setDraft({ ...draft, schedule_end: e.target.value })}
                  disabled={disabled}
                  required
                />
              </label>
              <label>
                Timezone
                <select
                  value={draft.timezone}
                  onChange={(e) => setDraft({ ...draft, timezone: e.target.value })}
                  disabled={disabled}
                >
                  <option value="UTC">UTC</option>
                  <option value="America/New_York">America/New_York (ET)</option>
                  <option value="America/Chicago">America/Chicago (CT)</option>
                  <option value="America/Denver">America/Denver (MT)</option>
                  <option value="America/Los_Angeles">America/Los_Angeles (PT)</option>
                  <option value="Europe/London">Europe/London (GMT/BST)</option>
                  <option value="Europe/Paris">Europe/Paris (CET)</option>
                  <option value="Asia/Kolkata">Asia/Kolkata (IST)</option>
                  <option value="Asia/Tokyo">Asia/Tokyo (JST)</option>
                  <option value="Australia/Sydney">Australia/Sydney (AEST)</option>
                </select>
              </label>
            </div>
          </>
        )}

        <div className="owner-escalation-field">
          <label>
            Owner Phone Number for Intelligent Transfer
            <input
              type="tel"
              value={draft.owner_phone}
              onChange={(e) => setDraft({ ...draft, owner_phone: e.target.value })}
              placeholder="+15551234567 or +919876543210"
              disabled={disabled}
            />
            <small className="subtle">
              Important or emergency calls will be transferred directly to this cellular number via native telephony dial.
            </small>
          </label>
        </div>

        <div className="form-action-row">
          <button type="submit" disabled={disabled || saving}>
            {saving ? 'Saving...' : 'Save Screening Schedule'}
          </button>
          {saveMessage && <span className="status-note">{saveMessage}</span>}
        </div>
      </form>
    </div>
  );
}
