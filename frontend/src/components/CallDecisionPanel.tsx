import React from 'react';
import type { CallRecord } from '../types/call';

interface CallDecisionPanelProps {
  call: Partial<CallRecord> | null;
  className?: string;
}

export default function CallDecisionPanel({ call, className = '' }: CallDecisionPanelProps) {
  if (!call) {
    return (
      <div className={`panel call-decision-empty ${className}`}>
        <p className="muted">No call active. Start a call or select from history to review judging focus.</p>
      </div>
    );
  }

  const {
    caller_name = 'Unknown Caller',
    caller_phone = 'Unknown Number',
    caller_known = false,
    intent = 'general',
    urgency = 'low',
    risk = 'low',
    confidence = 0.5,
    action = 'take_message',
    risk_reasons = [],
    summary = 'No summary generated yet.',
    inferred_caller,
    inferred_organization,
    identity_note,
  } = call;

  const actionLabels: Record<string, { label: string; badgeClass: string }> = {
    transfer: { label: 'Transfer to Owner', badgeClass: 'badge-transfer' },
    take_message: { label: 'Take Structured Message', badgeClass: 'badge-message' },
    clarify: { label: 'Clarify Identity / Purpose', badgeClass: 'badge-clarify' },
    agent_off: { label: 'Agent Off (Direct Pass)', badgeClass: 'badge-neutral' },
  };

  const actionMeta = actionLabels[action] || { label: action, badgeClass: 'badge-neutral' };

  return (
    <div className={`call-decision-panel ${className}`} aria-label="Call Assessment & Judging Focus">
      <div className="decision-header-row">
        <div>
          <span className="eyebrow-tag">Judging Focus: Intent + Risk Assessment</span>
          <h3 className="caller-heading">
            {caller_name}
            {inferred_caller && !caller_known && (
              <span className="unverified-pill" title="Self-declared by caller; unverified">
                Self-Declared
              </span>
            )}
          </h3>
          <p className="subtle">{caller_phone} {caller_known ? '· Verified Contact' : '· Unknown Number'}</p>
        </div>
        <div className="decision-badges">
          <span className={`risk-badge risk-${risk}`}>{risk.replace('_', ' ').toUpperCase()}</span>
          <span className={`action-pill ${actionMeta.badgeClass}`}>{actionMeta.label}</span>
        </div>
      </div>

      <div className="decision-grid-cards">
        <div className="decision-card">
          <span className="card-label">Detected Intent</span>
          <strong className="card-value intent-value">{intent.toUpperCase()}</strong>
          <small className="subtle">Urgency: {urgency.toUpperCase()}</small>
        </div>

        <div className="decision-card">
          <span className="card-label">Classification Confidence</span>
          <strong className="card-value">{Math.round((confidence || 0) * 100)}%</strong>
          <div className="confidence-meter-bg">
            <div
              className="confidence-meter-fill"
              style={{ width: `${Math.min(100, Math.max(10, Math.round((confidence || 0) * 100)))}%` }}
            />
          </div>
        </div>

        <div className="decision-card">
          <span className="card-label">Identity Recognition</span>
          <strong className="card-value">
            {caller_known
              ? 'Address Book Match'
              : inferred_caller
              ? `${inferred_caller}${inferred_organization ? ` (${inferred_organization})` : ''}`
              : 'Unverified Unknown'}
          </strong>
          <small className="subtle">{identity_note || (caller_known ? 'Verified against local contacts.' : 'Caller identity uncertain.')}</small>
        </div>
      </div>

      {summary && (
        <div className="decision-summary-box">
          <strong>Autonomous Assessment Summary:</strong>
          <p>{summary}</p>
        </div>
      )}

      {risk_reasons && risk_reasons.length > 0 && (
        <div className="decision-signals-box">
          <strong>Decision Signals & Fraud Rationale:</strong>
          <ul>
            {risk_reasons.map((reason, idx) => (
              <li key={idx}>{reason}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
