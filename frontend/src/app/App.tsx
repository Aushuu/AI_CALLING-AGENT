import { type ChangeEvent, type FormEvent, useEffect, useRef, useState } from 'react';
import CallList from '../features/calls/CallList';
import DemoCallSimulator from '../features/calls/DemoCallSimulator';
import CellularDialpad from '../features/calls/CellularDialpad';
import CallerProfile from '../features/contacts/CallerProfile';
import AgentSchedule from '../features/schedules/AgentSchedule';
import RuleEditor from '../features/preferences/RuleEditor';
import SetupChecklist from '../components/SetupChecklist';
import {
  createContact,
  deleteContact,
  getCalls,
  getContacts,
  getHealth,
  getSettings,
  getAccessToken,
  getPushPublicKey,
  clearAccessToken,
  deletePushSubscription,
  loginOwner,
  saveSettings,
  savePushSubscription,
  simulateCall,
} from '../services/apiClient';
import type { CallRecord, ContactRecord, ContactRule, HealthStatus, SettingsState } from '../types/call';

const defaultForm = {
  caller_phone: '+15550000000',
  transcript: 'I need help with a package delivery and I am waiting for a confirmation.',
};

const weekdayOptions = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

function decodeVCardValue(value: string): string {
  return value.replace(/\\[nN]/g, ' ').replace(/\\([,;\\])/g, '$1').trim();
}

function decodeVapidPublicKey(key: string): ArrayBuffer {
  const padding = '='.repeat((4 - (key.length % 4)) % 4);
  const base64 = (key + padding).replace(/-/g, '+').replace(/_/g, '/');
  const raw = window.atob(base64);
  const bytes = new Uint8Array(raw.length);
  for (let index = 0; index < raw.length; index += 1) {
    bytes[index] = raw.charCodeAt(index);
  }
  return bytes.buffer;
}

function parseVCardContacts(contents: string): Array<{ name: string; phone: string }> {
  const cards = [...contents.matchAll(/BEGIN:VCARD([\s\S]*?)END:VCARD/gi)];
  return cards.flatMap((card) => {
    const body = card[1].replace(/\r?\n[ \t]/g, '');
    const nameLine = body.match(/^FN(?:;[^:]*)?:(.*)$/im);
    const nameParts = body.match(/^N(?:;[^:]*)?:(.*)$/im)?.[1]?.split(';') ?? [];
    const fallbackName = [nameParts[1], nameParts[0]].filter(Boolean).join(' ');
    const name = decodeVCardValue(nameLine?.[1] ?? fallbackName ?? '') || 'Saved contact';
    const phones = [...body.matchAll(/^TEL(?:;[^:]*)?:(.+)$/gim)]
      .map((match) => decodeVCardValue(match[1]))
      .filter((phone) => (phone.match(/\d/g) ?? []).length >= 7);
    return phones.map((phone) => ({ name, phone }));
  });
}

async function showCallRecordNotification(callSid: string): Promise<void> {
  try {
    const options = {
      body: 'A call record is ready in call history.',
      icon: '/app-icon.svg',
      tag: `call-record-${callSid}`,
    };
    if ('serviceWorker' in navigator) {
      const registration = await navigator.serviceWorker.getRegistration();
      if (registration) {
        await registration.showNotification('Call update', options);
        return;
      }
    }
    const notice = new Notification('Call update', options);
    notice.onclick = () => {
      window.focus();
      document.getElementById('recent-calls')?.scrollIntoView({ behavior: 'smooth' });
      notice.close();
    };
  } catch {
    // Browser notification support varies
  }
}

interface DeviceContactPicker {
  select(
    properties: Array<'name' | 'tel'>,
    options?: { multiple?: boolean },
  ): Promise<Array<{ name?: string[]; tel?: string[] }>>;
}

function getDayNameInTimeZone(timeZone: string): string {
  return new Intl.DateTimeFormat('en-US', { timeZone, weekday: 'long' }).format(new Date());
}

function getTimeInZone(timeZone: string): string {
  const formatter = new Intl.DateTimeFormat('en-GB', {
    timeZone,
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
  return formatter.format(new Date());
}

function isWithinSchedule(start: string, end: string, timeInZone: string): boolean {
  const toMinutes = (time: string): number => {
    const [hours, minutes] = time.split(':').map(Number);
    return hours * 60 + minutes;
  };
  const nowMinutes = toMinutes(timeInZone);
  const startMinutes = toMinutes(start);
  const endMinutes = toMinutes(end);

  if (startMinutes < endMinutes) {
    return startMinutes <= nowMinutes && nowMinutes < endMinutes;
  }
  return nowMinutes >= startMinutes || nowMinutes < endMinutes;
}

type TabType = 'voice' | 'schedule' | 'contacts' | 'dialer' | 'history' | 'setup';

export default function App() {
  const [activeTab, setActiveTab] = useState<TabType>('voice');
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [settings, setSettings] = useState<SettingsState | null>(null);
  const [contacts, setContacts] = useState<ContactRecord[]>([]);
  const [calls, setCalls] = useState<CallRecord[]>([]);
  const [form, setForm] = useState(defaultForm);
  const [settingsDraft, setSettingsDraft] = useState<SettingsState | null>(null);
  const [loading, setLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState('');
  const [authChecked, setAuthChecked] = useState(false);
  const [authenticated, setAuthenticated] = useState(false);
  const [callAlertsEnabled, setCallAlertsEnabled] = useState(
    typeof Notification !== 'undefined' && Notification.permission === 'granted',
  );
  const [pushSubscribed, setPushSubscribed] = useState(false);
  const [loginUsername, setLoginUsername] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loggingIn, setLoggingIn] = useState(false);
  const [notificationMessage, setNotificationMessage] = useState('');
  const seenLiveCallStatuses = useRef<Map<string, string> | null>(null);

  const deviceContactsAvailable =
    typeof navigator !== 'undefined' &&
    Boolean((navigator as Navigator & { contacts?: DeviceContactPicker }).contacts);

  const availabilityLabel = (() => {
    if (!settingsDraft) return 'Loading availability…';
    if (settingsDraft.manual_enabled) return 'Manual Mode: Active (Screening All Calls)';
    if (!settingsDraft.schedule_enabled) return 'Schedule is Off (Agent Inactive)';

    const timeInZone = getTimeInZone(settingsDraft.timezone);
    const dayName = getDayNameInTimeZone(settingsDraft.timezone);
    const allowedDays = settingsDraft.schedule_days ?? weekdayOptions;
    const currentDayIndex = weekdayOptions.indexOf(dayName);
    const scheduledDay =
      settingsDraft.schedule_start > settingsDraft.schedule_end && timeInZone < settingsDraft.schedule_end
        ? weekdayOptions[(currentDayIndex + weekdayOptions.length - 1) % weekdayOptions.length]
        : dayName;
    const scheduleActive =
      allowedDays.includes(scheduledDay) &&
      isWithinSchedule(settingsDraft.schedule_start, settingsDraft.schedule_end, timeInZone);

    return scheduleActive
      ? `Schedule Active (${timeInZone} on ${dayName}, ${settingsDraft.timezone})`
      : `Off-Hours (${timeInZone} on ${dayName}, ${settingsDraft.timezone})`;
  })();

  useEffect(() => {
    let mounted = true;
    void getHealth()
      .then((status) => {
        if (!mounted) return;
        setHealth(status);
        setAuthenticated(!status.auth_required || Boolean(getAccessToken()));
      })
      .catch((loadError) => {
        if (mounted) setError(loadError instanceof Error ? loadError.message : 'Unable to check access.');
      })
      .finally(() => {
        if (mounted) setAuthChecked(true);
      });
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    if (authenticated) void refreshData();
  }, [authenticated]);

  useEffect(() => {
    if (!authenticated || !('serviceWorker' in navigator)) return;
    let active = true;
    void navigator.serviceWorker.ready
      .then((registration) => registration.pushManager.getSubscription())
      .then((subscription) => {
        if (!active) return;
        setPushSubscribed(Boolean(subscription));
        if (subscription && typeof Notification !== 'undefined' && Notification.permission === 'granted') {
          setCallAlertsEnabled(true);
        }
      })
      .catch(() => undefined);
    return () => {
      active = false;
    };
  }, [authenticated]);

  useEffect(() => {
    const expireSession = () => {
      setAuthenticated(false);
      setError('Your owner session expired. Sign in again.');
    };
    window.addEventListener('owner-session-expired', expireSession);
    return () => window.removeEventListener('owner-session-expired', expireSession);
  }, []);

  useEffect(() => {
    if (!authenticated) {
      seenLiveCallStatuses.current = null;
      return;
    }

    let active = true;
    const pollForCalls = async () => {
      try {
        const latestCalls = await getCalls(30);
        if (!active) return;
        const liveCalls = latestCalls.filter((call) => !call.simulated && call.call_sid);
        const liveCallStatuses = new Map<string, string>(
          liveCalls.map((call): [string, string] => [String(call.call_sid), call.call_status ?? 'unknown']),
        );
        const previousCallStatuses = seenLiveCallStatuses.current;
        if (
          previousCallStatuses &&
          document.visibilityState !== 'visible' &&
          callAlertsEnabled &&
          typeof Notification !== 'undefined' &&
          Notification.permission === 'granted'
        ) {
          const terminalStatuses = new Set(['completed', 'busy', 'failed', 'no-answer', 'canceled']);
          const updatedCalls = liveCalls.filter(
            (call) =>
              call.call_sid &&
              terminalStatuses.has(call.call_status ?? '') &&
              previousCallStatuses.get(String(call.call_sid)) !== call.call_status,
          );
          updatedCalls.slice(0, 5).forEach((call) => {
            if (call.call_sid) void showCallRecordNotification(String(call.call_sid));
          });
        }
        seenLiveCallStatuses.current = liveCallStatuses;
        setCalls(latestCalls);
      } catch {
        // Keep dashboard usable
      }
    };

    void pollForCalls();
    const timer = window.setInterval(() => {
      void pollForCalls();
    }, 15000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, [authenticated, callAlertsEnabled]);

  const refreshData = async () => {
    setRefreshing(true);
    try {
      const [healthData, settingsData, callData, contactData] = await Promise.all([
        getHealth(),
        getSettings(),
        getCalls(30),
        getContacts(),
      ]);
      setHealth(healthData);
      setSettings(settingsData);
      setSettingsDraft(settingsData);
      setCalls(callData);
      setContacts(contactData);
    } catch (loadError) {
      setError(loadError instanceof Error ? loadError.message : 'Unable to load data.');
    } finally {
      setRefreshing(false);
    }
  };

  const handleToggleManual = async (manualEnabled: boolean) => {
    if (!settingsDraft) return;
    try {
      const updated = await saveSettings({ ...settingsDraft, manual_enabled: manualEnabled });
      setSettings(updated);
      setSettingsDraft(updated);
      await refreshData();
    } catch (saveErr) {
      setError(saveErr instanceof Error ? saveErr.message : 'Failed to update manual mode.');
    }
  };

  const handleSaveSchedule = async (updated: SettingsState) => {
    const saved = await saveSettings(updated);
    setSettings(saved);
    setSettingsDraft(saved);
    await refreshData();
  };

  const handleAddContact = async (contact: { name: string; phone: string; rule: ContactRule }) => {
    const created = await createContact(contact);
    setContacts((current) => [created, ...current]);
    await refreshData();
  };

  const handleDeleteContact = async (id: number) => {
    await deleteContact(id);
    setContacts((current) => current.filter((c) => c.id !== id));
    await refreshData();
  };

  const handleImportVCard = async (file: File) => {
    const contents = await file.text();
    const parsed = parseVCardContacts(contents);
    if (parsed.length === 0) {
      setError('No valid phone numbers found in this vCard file.');
      return;
    }
    for (const c of parsed) {
      try {
        await createContact({ ...c, rule: 'always_screen' });
      } catch {
        // Skip duplicates
      }
    }
    await refreshData();
  };

  const handleDeviceContactSelect = async () => {
    const picker = (navigator as Navigator & { contacts?: DeviceContactPicker }).contacts;
    if (!picker) return;
    try {
      const [selected] = await picker.select(['name', 'tel'], { multiple: false });
      if (!selected) return;
      const name = selected.name?.[0]?.trim() ?? 'Saved Contact';
      const phone = selected.tel?.[0]?.trim() ?? '';
      if (phone) {
        await createContact({ name, phone, rule: 'always_screen' });
        await refreshData();
      }
    } catch {
      // Picker cancelled
    }
  };

  const handleQuickSimulate = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await simulateCall(form);
      setCalls((prev) => [res, ...prev]);
      setForm(defaultForm);
      await refreshData();
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Simulation failed.');
    } finally {
      setLoading(false);
    }
  };

  const handleOwnerLogin = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setLoggingIn(true);
    setError('');
    try {
      await loginOwner(loginUsername, loginPassword);
      setLoginPassword('');
      setAuthenticated(true);
    } catch (loginError) {
      setError(loginError instanceof Error ? loginError.message : 'Unable to sign in.');
    } finally {
      setLoggingIn(false);
    }
  };

  const handleOwnerLogout = async () => {
    clearAccessToken();
    setAuthenticated(false);
    setSettings(null);
    setSettingsDraft(null);
    setContacts([]);
    setCalls([]);
  };

  const handleEnableCallAlerts = async () => {
    if (typeof Notification === 'undefined') {
      setNotificationMessage('This browser does not support call notifications.');
      return;
    }
    try {
      const permission = await Notification.requestPermission();
      if (permission !== 'granted') {
        setCallAlertsEnabled(false);
        setNotificationMessage('Notification permission was denied.');
        return;
      }
      setCallAlertsEnabled(true);
      const pushConfig = await getPushPublicKey();
      if (!pushConfig.enabled || !pushConfig.public_key || !('serviceWorker' in navigator)) {
        setNotificationMessage('In-browser alerts are active while the tab is open.');
        return;
      }
      const registration = await navigator.serviceWorker.ready;
      let subscription = await registration.pushManager.getSubscription();
      if (!subscription) {
        subscription = await registration.pushManager.subscribe({
          userVisibleOnly: true,
          applicationServerKey: decodeVapidPublicKey(pushConfig.public_key),
        });
      }
      const rawSubscription = subscription.toJSON();
      if (rawSubscription.endpoint && rawSubscription.keys?.p256dh && rawSubscription.keys?.auth) {
        await savePushSubscription({
          endpoint: rawSubscription.endpoint,
          keys: { p256dh: rawSubscription.keys.p256dh, auth: rawSubscription.keys.auth },
        });
        setPushSubscribed(true);
        setNotificationMessage('Background push alerts are active.');
      }
    } catch (err) {
      setNotificationMessage(err instanceof Error ? err.message : 'Failed to enable notifications.');
    }
  };

  if (!authChecked) {
    return (
      <main className="app-shell auth-shell">
        <section className="panel auth-panel">
          <h1>Checking access…</h1>
          <p className="muted">Connecting to your personal call agent service.</p>
        </section>
      </main>
    );
  }

  if (health?.auth_required && !authenticated) {
    return (
      <main className="app-shell auth-shell">
        <section className="panel auth-panel" aria-labelledby="owner-login-title">
          <h1 id="owner-login-title">Personal Call Agent</h1>
          <p className="muted">Enter your account credentials to access agent settings and call records.</p>
          <form onSubmit={handleOwnerLogin} className="form-grid">
            <label>
              Username
              <input value={loginUsername} onChange={(e) => setLoginUsername(e.target.value)} required />
            </label>
            <label>
              Password
              <input type="password" value={loginPassword} onChange={(e) => setLoginPassword(e.target.value)} required />
            </label>
            <button type="submit" disabled={loggingIn}>
              {loggingIn ? 'Signing in…' : 'Sign in'}
            </button>
          </form>
          {error && <p className="status-warn" role="alert">{error}</p>}
        </section>
      </main>
    );
  }

  return (
    <main className="app-shell">
      <header className="header">
        <div>
          <h1>AI-Powered Personal Call Agent</h1>
          <div className="availability-panel" style={{ margin: '6px 0 0', padding: '6px 12px' }}>
            <span className="status-dot dot-active" />
            <strong>{availabilityLabel}</strong>
          </div>
        </div>

        <div className="header-actions">
          <button type="button" className="secondary" onClick={() => void refreshData()} disabled={refreshing}>
            {refreshing ? 'Syncing…' : '↻ Sync Data'}
          </button>
          {typeof Notification !== 'undefined' && (
            <button
              type="button"
              className={callAlertsEnabled ? 'secondary' : ''}
              onClick={() => void handleEnableCallAlerts()}
            >
              {callAlertsEnabled ? '🔔 Alerts On' : 'Enable Alerts'}
            </button>
          )}
          {health?.auth_required && (
            <button type="button" className="secondary" onClick={() => void handleOwnerLogout()}>
              Sign Out
            </button>
          )}
        </div>
      </header>

      {notificationMessage && <p className="muted" role="status">{notificationMessage}</p>}
      {error && <p className="status-warn" role="alert">{error}</p>}

      {/* Tab Navigation Bar */}
      <nav className="app-nav" aria-label="Main Navigation">
        <button
          type="button"
          className={`nav-tab ${activeTab === 'voice' ? 'active' : ''}`}
          onClick={() => setActiveTab('voice')}
        >
          🎙️ Voice Call Center
        </button>
        <button
          type="button"
          className={`nav-tab ${activeTab === 'schedule' ? 'active' : ''}`}
          onClick={() => setActiveTab('schedule')}
        >
          ⚙️ Agent Mode & Schedule
        </button>
        <button
          type="button"
          className={`nav-tab ${activeTab === 'contacts' ? 'active' : ''}`}
          onClick={() => setActiveTab('contacts')}
        >
          👥 Known Contacts ({contacts.length})
        </button>
        <button
          type="button"
          className={`nav-tab ${activeTab === 'dialer' ? 'active' : ''}`}
          onClick={() => setActiveTab('dialer')}
        >
          📶 Cellular Dialer
        </button>
        <button
          type="button"
          className={`nav-tab ${activeTab === 'history' ? 'active' : ''}`}
          onClick={() => setActiveTab('history')}
        >
          📜 Call History ({calls.length})
        </button>
        <button
          type="button"
          className={`nav-tab ${activeTab === 'setup' ? 'active' : ''}`}
          onClick={() => setActiveTab('setup')}
        >
          🔧 Setup Guide
        </button>
      </nav>

      {/* Tab 1: Live Voice Call Center */}
      {activeTab === 'voice' && (
        <section>
          <DemoCallSimulator onSaved={() => void refreshData()} />
        </section>
      )}

      {/* Tab 2: Agent Mode & Schedule */}
      {activeTab === 'schedule' && settingsDraft && (
        <section className="grid" style={{ gridTemplateColumns: '1fr', gap: '20px' }}>
          <RuleEditor settings={settingsDraft} onToggleManual={handleToggleManual} />
          <AgentSchedule settings={settingsDraft} onSave={handleSaveSchedule} />
        </section>
      )}

      {/* Tab 3: Known Contacts & Personalized Rules */}
      {activeTab === 'contacts' && (
        <section>
          <CallerProfile
            contacts={contacts}
            onAddContact={handleAddContact}
            onDeleteContact={handleDeleteContact}
            onImportVCard={handleImportVCard}
            onPickDeviceContacts={handleDeviceContactSelect}
            deviceContactsAvailable={deviceContactsAvailable}
          />
        </section>
      )}

      {/* Tab 4: Native Cellular Calling */}
      {activeTab === 'dialer' && (
        <section>
          <CellularDialpad initialNumber={settingsDraft?.owner_phone || ''} />
        </section>
      )}

      {/* Tab 5: Call History & Quick Simulation */}
      {activeTab === 'history' && (
        <section>
          <div id="recent-calls" style={{ marginBottom: 20 }}>
            <CallList calls={calls} />
          </div>

          <div className="panel" style={{ marginTop: 20 }}>
            <h2>Deterministic Text Simulation</h2>
            <p className="muted">Test deterministic rule analysis on custom transcript text.</p>
            <form onSubmit={handleQuickSimulate} className="form-grid compact-form">
              <input
                value={form.caller_phone}
                onChange={(e) => setForm((c) => ({ ...c, caller_phone: e.target.value }))}
                placeholder="Caller phone"
                required
              />
              <input
                value={form.transcript}
                onChange={(e) => setForm((c) => ({ ...c, transcript: e.target.value }))}
                placeholder="Spoken caller transcript"
                required
              />
              <button type="submit" disabled={loading}>{loading ? 'Screening…' : 'Run Simulation'}</button>
            </form>
          </div>
        </section>
      )}

      {/* Tab 6: Setup & Carrier Configuration */}
      {activeTab === 'setup' && (
        <section>
          <SetupChecklist health={health} settings={settingsDraft} />
        </section>
      )}
    </main>
  );
}
