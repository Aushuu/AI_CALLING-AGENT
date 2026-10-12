import React, { useState } from 'react';
import type { ContactRecord, ContactRule } from '../../types/call';
import { soundEffects } from '../../services/soundEffects';

interface CallerProfileProps {
  contacts: ContactRecord[];
  onAddContact: (contact: { name: string; phone: string; rule: ContactRule }) => Promise<void>;
  onDeleteContact: (id: number) => Promise<void>;
  onImportVCard?: (file: File) => Promise<void>;
  onPickDeviceContacts?: () => Promise<void>;
  deviceContactsAvailable?: boolean;
}

const ruleDescriptions: Record<ContactRule, { label: string; description: string; badge: string }> = {
  always_screen: {
    label: 'Standard Screen',
    description: 'AI holds conversation, assesses intent & risk, and decides whether to take a message or transfer.',
    badge: 'rule-screen',
  },
  always_transfer: {
    label: 'VIP (Always Transfer)',
    description: 'Immediately escalates and dials the owner phone if low risk.',
    badge: 'rule-vip',
  },
  always_message: {
    label: 'Always Take Message',
    description: 'Assistant politely takes a message and logs transcript without ringing owner.',
    badge: 'rule-message',
  },
  delivery_agent: {
    label: 'Delivery Instructions',
    description: 'Provides doorstep drop-off / parcel box instructions and collects delivery tracking details.',
    badge: 'rule-delivery',
  },
  block_reject: {
    label: 'Politely Decline',
    description: 'Informs caller owner is unavailable and immediately disconnects without ringing owner.',
    badge: 'rule-blocked',
  },
};

export default function CallerProfile({
  contacts,
  onAddContact,
  onDeleteContact,
  onImportVCard,
  onPickDeviceContacts,
  deviceContactsAvailable = false,
}: CallerProfileProps) {
  const [name, setName] = useState('');
  const [phone, setPhone] = useState('');
  const [rule, setRule] = useState<ContactRule>('always_screen');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!name.trim() || !phone.trim()) return;
    setSaving(true);
    setError('');
    try {
      await onAddContact({ name: name.trim(), phone: phone.trim(), rule });
      setName('');
      setPhone('');
      setRule('always_screen');
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to save contact.');
    } finally {
      setSaving(false);
    }
  };

  const handleVCardChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file && onImportVCard) {
      void onImportVCard(file);
      e.target.value = '';
    }
  };

  return (
    <div className="panel caller-profile-panel" aria-labelledby="contacts-heading">
      <div className="panel-header">
        <div>
          <h2 id="contacts-heading">Known Contacts & Personalized Rules</h2>
          <p className="muted">
            Recognize known callers from your address book and apply caller-specific handling rules.
          </p>
        </div>
        <div className="contact-import-actions">
          {deviceContactsAvailable && onPickDeviceContacts && (
            <button type="button" className="secondary" onClick={onPickDeviceContacts}>
              📇 Device Contacts
            </button>
          )}
          {onImportVCard && (
            <label className="secondary button-like-label">
              📥 Import .vcf
              <input type="file" accept=".vcf,text/vcard" onChange={handleVCardChange} style={{ display: 'none' }} />
            </label>
          )}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="contact-add-form">
        <div className="form-fields-grid">
          <label>
            Contact Name
            <input
              type="text"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="e.g. Dr. Sarah or Mom"
              required
            />
          </label>
          <label>
            Phone Number
            <input
              type="tel"
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="e.g. +15551234567"
              required
            />
          </label>
          <label>
            Personalized Rule
            <select value={rule} onChange={(e) => setRule(e.target.value as ContactRule)}>
              <option value="always_screen">Standard Screen (AI Assessment)</option>
              <option value="always_transfer">VIP (Immediate Transfer to Owner)</option>
              <option value="always_message">Take Message (Silent)</option>
              <option value="delivery_agent">Delivery Agent (Drop-off Instructions)</option>
              <option value="block_reject">Block / Politely Decline</option>
            </select>
          </label>
        </div>
        <button type="submit" disabled={saving}>
          {saving ? 'Adding...' : 'Save Contact Rule'}
        </button>
      </form>

      {error && <p className="status-warn" role="alert">{error}</p>}

      <div className="contact-cards-container">
        {contacts.length === 0 ? (
          <p className="subtle">No contacts configured. Unknown callers will receive standard cautious screening.</p>
        ) : (
          <ul className="contact-cards-list">
            {contacts.map((c) => {
              const ruleMeta = ruleDescriptions[c.rule] || ruleDescriptions.always_screen;
              return (
                <li key={c.id} className="contact-card-item">
                  <div className="contact-card-main">
                    <div className="contact-avatar">{c.name.charAt(0).toUpperCase()}</div>
                    <div>
                      <strong>{c.name}</strong>
                      <div className="subtle">{c.phone}</div>
                    </div>
                  </div>
                  <div className="contact-card-rule">
                    <span className={`rule-pill ${ruleMeta.badge}`}>{ruleMeta.label}</span>
                    <small className="subtle">{ruleMeta.description}</small>
                  </div>
                  <div className="contact-card-actions">
                    <a
                      href={`tel:${c.phone}`}
                      className="native-call-chip"
                      onClick={() => soundEffects.playDtmf('5')}
                      title="Initiate native cellular call without internet"
                    >
                      📞 Native Cellular Call
                    </a>
                    <button
                      type="button"
                      className="danger small-btn"
                      onClick={() => onDeleteContact(c.id)}
                      title="Delete contact"
                    >
                      Delete
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </div>
  );
}
