import type { HealthStatus, SettingsState } from '../types/call';

interface SetupChecklistProps {
  health: HealthStatus | null;
  settings: SettingsState | null;
}

export default function SetupChecklist({ health, settings }: SetupChecklistProps) {
  const voiceReady = health?.twilio_enabled ?? false;
  const agentConfigured = Boolean(settings && (
    settings.manual_enabled || (settings.schedule_enabled && settings.schedule_days.length > 0)
  ));
  const webhookUrl = health?.twilio_webhook_url;
  const webhookSecure = health?.twilio_webhook_uses_public_https ?? false;

  const items = [
    {
      title: 'Configure the voice connection',
      detail: voiceReady
        ? 'Twilio credentials, inbound number, and public HTTPS URL are configured.'
        : `Add the missing server settings: ${(health?.twilio_missing_config ?? ['Checking configuration…']).join(', ')}.`,
      state: voiceReady ? 'ready' : 'todo',
      href: '#system-status',
      action: voiceReady ? 'Review voice settings' : 'View required settings',
    },
    {
      title: 'Point Twilio to the webhook',
      detail: webhookUrl
        ? `In Twilio Console, set the number or BYOC trunk “A call comes in” webhook to ${webhookUrl} with HTTP POST. Set the status callback to ${webhookUrl.replace('/voice', '/status')} with HTTP POST and enable initiated, ringing, answered, and completed events. This dashboard cannot verify the Console settings.`
        : 'After the backend has a public HTTPS URL, configure its voice and status callback URLs in Twilio Console.',
      state: 'manual',
      href: '#system-status',
      action: 'View webhook URL',
    },
    {
      title: 'Choose when the agent answers',
      detail: !settings
        ? 'Loading agent settings…'
        : agentConfigured
          ? settings.manual_enabled
            ? 'Manual mode is on, so the agent is available at all times.'
            : `A weekly schedule is set. The agent is ${health?.agent_available ? 'available now' : 'currently outside its scheduled hours'}; confirm the days, hours, and timezone below.`
          : 'Both manual mode and the weekly schedule are off, so calls will not be screened.',
      state: settings && agentConfigured ? 'ready' : 'todo',
      href: '#agent-settings',
      action: 'Edit agent settings',
    },
    {
      title: 'Optional: enable AI replies',
      detail: health?.ai_enabled
        ? 'Gemini is configured for call classification and natural replies.'
        : 'Add GEMINI_API_KEY on the server to enable AI classification and natural replies. Rules-based screening still works without it.',
      state: health?.ai_enabled ? 'ready' : 'optional',
      href: '#system-status',
      action: health?.ai_enabled ? 'View status' : 'Learn where status appears',
    },
    {
      title: 'Optional: background call alerts',
      detail: health?.push_notifications_enabled
        ? 'Server push is configured. Enable alerts on each device from the dashboard header.'
        : 'Configure VAPID_PUBLIC_KEY, VAPID_PRIVATE_KEY, and VAPID_SUBJECT to deliver alerts when the installed dashboard is closed.',
      state: 'optional',
      href: health?.push_notifications_enabled ? '#call-alert-controls' : '#system-status',
      action: health?.push_notifications_enabled ? 'Enable device alerts' : 'View server status',
    },
  ] as const;

  const requiredItems = items.filter((item) => item.state !== 'optional' && item.state !== 'manual');
  const readyCount = requiredItems.filter((item) => item.state === 'ready').length;
  const allReady = requiredItems.every((item) => item.state === 'ready');

  return (
    <section className="panel setup-checklist" aria-labelledby="setup-checklist-title">
      <div className="setup-heading">
        <div>
          <h2 id="setup-checklist-title">Get your call agent ready</h2>
          <p className="muted">Complete the required setup, then place a test call to your inbound number.</p>
        </div>
        <span className={`setup-progress ${allReady ? 'complete' : ''}`}>
          {readyCount} of {requiredItems.length} system checks ready
        </span>
      </div>
      <ol className="setup-list">
        {items.map((item) => (
          <li key={item.title} className={`setup-item setup-${item.state}`}>
            <span className="setup-marker" aria-hidden="true">
              {item.state === 'ready' ? '✓' : item.state === 'optional' ? '＋' : '•'}
            </span>
            <div className="setup-copy">
              <div className="setup-item-heading">
                <strong>{item.title}</strong>
                <span className="setup-state-label">
                  {item.state === 'ready' ? 'Ready' : item.state === 'optional' ? 'Optional' : item.state === 'manual' ? 'Manual step' : 'Needs attention'}
                </span>
              </div>
              <p>{item.detail}</p>
              <a href={item.href}>{item.action} →</a>
            </div>
          </li>
        ))}
      </ol>
      {webhookSecure && !voiceReady && (
        <p className="muted setup-note">Your webhook URL uses public HTTPS, but Twilio is not fully configured yet.</p>
      )}
    </section>
  );
}
