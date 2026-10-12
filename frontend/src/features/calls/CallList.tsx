import { useEffect, useMemo, useState } from 'react';
import type { CallRecord } from '../../types/call';

interface CallListProps {
  calls: CallRecord[];
}

const riskFilters = ['all', 'low', 'unknown', 'spam', 'suspicious', 'possible_scam'] as const;

const actionLabels: Record<string, string> = {
  agent_off: 'Agent off',
  take_message: 'Take message',
  transfer: 'Transfer',
  clarify: 'Clarify',
};

const callStatusLabels: Record<string, string> = {
  unknown: 'Status unavailable',
  simulated: 'Simulated',
  queued: 'Queued',
  ringing: 'Ringing',
  'in-progress': 'In progress',
  completed: 'Completed',
  busy: 'Busy',
  failed: 'Failed',
  'no-answer': 'No answer',
  canceled: 'Canceled',
};

function getCallKey(call: CallRecord): string {
  return String(call.id ?? call.call_sid ?? `${call.caller_phone}-${call.created_at}`);
}

export default function CallList({ calls }: CallListProps) {
  const [selectedRisk, setSelectedRisk] = useState<(typeof riskFilters)[number]>('all');
  const [selectedCallKey, setSelectedCallKey] = useState<string | null>(null);

  const filteredCalls = useMemo(() => {
    if (selectedRisk === 'all') return calls;
    return calls.filter((call) => call.risk === selectedRisk);
  }, [calls, selectedRisk]);

  useEffect(() => {
    if (filteredCalls.length === 0) {
      setSelectedCallKey(null);
      return;
    }

    if (!selectedCallKey || !filteredCalls.some((call) => getCallKey(call) === selectedCallKey)) {
      setSelectedCallKey(getCallKey(filteredCalls[0]));
    }
  }, [filteredCalls, selectedCallKey]);

  const selectedCall = filteredCalls.find((call) => getCallKey(call) === selectedCallKey) ?? filteredCalls[0] ?? null;

  return (
    <div className="panel">
      <div className="panel-header">
        <h2>Recent calls</h2>
        <div className="filter-row" aria-label="Filter calls by risk level">
          {riskFilters.map((risk) => (
            <button
              key={risk}
              type="button"
              className={`filter-button ${selectedRisk === risk ? 'active' : ''}`}
              onClick={() => setSelectedRisk(risk)}
            >
              {risk === 'all' ? 'All' : risk.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {filteredCalls.length === 0 ? (
        <p>No calls match this filter yet.</p>
      ) : (
        <>
          <ul className="call-list">
            {filteredCalls.map((call) => {
              const callKey = getCallKey(call);
              const isSelected = callKey === selectedCallKey;

              return (
                <li
                  key={callKey}
                  className={`call-item ${isSelected ? 'selected' : ''}`}
                  onClick={() => setSelectedCallKey(callKey)}
                >
                  <div className="call-header">
                    <div>
                      <strong>{call.caller_name}</strong>
                      <div className="subtle">{call.caller_phone}</div>
                    </div>
                    <span className={`risk-badge risk-${call.risk}`}>{call.risk}</span>
                  </div>

                  <div className="meta-row">
                    <span>{call.intent}</span>
                    <span className="action-pill">{actionLabels[call.action] ?? call.action}</span>
                    <span className="action-pill">
                      {callStatusLabels[call.call_status ?? (call.simulated ? 'simulated' : 'unknown')]}
                    </span>
                  </div>

                  <p className="call-summary">{call.summary}</p>

                  <div className="call-meta-row">
                    <small>{call.provider}</small>
                    <small>confidence {call.confidence}</small>
                    <small>{call.created_at ? new Date(call.created_at).toLocaleString() : 'just now'}</small>
                  </div>

                  {call.risk_reasons.length > 0 && (
                    <div className="call-reasons">
                      <strong>Signals</strong>
                      <ul>
                        {call.risk_reasons.map((reason) => (
                          <li key={reason}>{reason}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>

          {selectedCall && (
            <div className="call-detail-panel">
              <div className="detail-header">
                <span className={`risk-badge risk-${selectedCall.risk}`}>{selectedCall.risk}</span>
                <strong>{selectedCall.intent}</strong>
              </div>

              <p className="detail-summary">{selectedCall.summary}</p>

              <div className="detail-grid">
                <span>Urgency: {selectedCall.urgency}</span>
                <span>Confidence: {selectedCall.confidence}</span>
                <span>Action: {actionLabels[selectedCall.action] ?? selectedCall.action}</span>
                <span>Caller known: {selectedCall.caller_known ? 'Yes' : 'No'}</span>
                <span>Provider: {selectedCall.provider}</span>
                <span>
                  Call status:{' '}
                  {callStatusLabels[
                    selectedCall.call_status ?? (selectedCall.simulated ? 'simulated' : 'unknown')
                  ]}
                </span>
                <span>Source: {selectedCall.simulated ? 'Simulated' : 'Live'}</span>
              </div>

              <div className="detail-section">
                <strong>Transcript</strong>
                <p className="detail-transcript">{selectedCall.transcript || 'No transcript captured.'}</p>
              </div>

              {selectedCall.risk_reasons.length > 0 && (
                <div className="detail-section">
                  <strong>Decision rationale</strong>
                  <ul className="detail-reasons">
                    {selectedCall.risk_reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  );
}
