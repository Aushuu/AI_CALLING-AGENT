export type RiskLevel = 'low' | 'unknown' | 'spam' | 'suspicious' | 'possible_scam';
export type UrgencyLevel = 'low' | 'medium' | 'high';
export type CallAction = 'agent_off' | 'take_message' | 'transfer' | 'clarify';
export type CallStatus =
  | 'unknown'
  | 'simulated'
  | 'queued'
  | 'ringing'
  | 'in-progress'
  | 'completed'
  | 'busy'
  | 'failed'
  | 'no-answer'
  | 'canceled';

export type ContactRule =
  | 'always_screen'
  | 'always_message'
  | 'always_transfer'
  | 'delivery_agent'
  | 'block_reject';

export interface CallRecord {
  id?: number;
  call_sid?: string | null;
  caller_phone: string;
  caller_name: string;
  caller_known: boolean;
  transcript: string;
  intent: string;
  urgency: UrgencyLevel;
  risk: RiskLevel;
  risk_reasons: string[];
  confidence: number;
  action: CallAction;
  summary: string;
  provider: string;
  simulated: boolean;
  call_status?: CallStatus;
  created_at?: string;
  inferred_caller?: string | null;
  inferred_organization?: string | null;
  identity_note?: string;
}

export interface HealthStatus {
  status: string;
  auth_required: boolean;
  auth_configured: boolean;
  ai_enabled: boolean;
  push_notifications_enabled?: boolean;
  twilio_enabled: boolean;
  twilio_missing_config?: string[];
  twilio_webhook_url?: string | null;
  twilio_webhook_uses_public_https?: boolean;
  inbound_phone_configured?: boolean;
  agent_available: boolean;
  storage: string;
}

export interface SettingsState {
  manual_enabled: boolean;
  schedule_enabled: boolean;
  schedule_days: string[];
  schedule_start: string;
  schedule_end: string;
  timezone: string;
  owner_phone: string;
}

export interface ContactRecord {
  id: number;
  name: string;
  phone: string;
  rule: ContactRule;
  created_at: string;
}
