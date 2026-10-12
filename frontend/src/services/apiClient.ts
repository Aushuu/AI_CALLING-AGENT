import type { CallRecord, ContactRecord, HealthStatus, SettingsState } from '../types/call';

const API_BASE = import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8000';
const ACCESS_TOKEN_KEY = 'calling-agent-access-token';

export function getAccessToken(): string | null {
  return sessionStorage.getItem(ACCESS_TOKEN_KEY);
}

function setAccessToken(token: string): void {
  sessionStorage.setItem(ACCESS_TOKEN_KEY, token);
}

export function clearAccessToken(): void {
  sessionStorage.removeItem(ACCESS_TOKEN_KEY);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = new Headers(init?.headers);
  if (!headers.has('Content-Type')) headers.set('Content-Type', 'application/json');
  const accessToken = getAccessToken();
  if (accessToken && path !== '/api/auth/login') {
    headers.set('Authorization', `Bearer ${accessToken}`);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers,
  });

  if (!response.ok) {
    const errorText = await response.text();
    if (response.status === 401 && path !== '/api/auth/login') {
      clearAccessToken();
      window.dispatchEvent(new Event('owner-session-expired'));
    }
    let message = errorText || `Request failed with status ${response.status}`;
    try {
      const errorPayload = JSON.parse(errorText) as { detail?: string };
      message = errorPayload.detail ?? message;
    } catch {
      // Keep the raw response text for non-JSON errors.
    }
    throw new Error(message);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return (await response.json()) as T;
}

export function getHealth(): Promise<HealthStatus> {
  return request<HealthStatus>('/api/health');
}

export async function loginOwner(username: string, password: string): Promise<void> {
  const response = await request<{ access_token: string }>('/api/auth/login', {
    method: 'POST',
    body: JSON.stringify({ username, password }),
  });
  setAccessToken(response.access_token);
}

export function getSettings(): Promise<SettingsState> {
  return request<SettingsState>('/api/settings');
}

export function saveSettings(payload: SettingsState): Promise<SettingsState> {
  return request<SettingsState>('/api/settings', {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function getContacts(): Promise<ContactRecord[]> {
  return request<ContactRecord[]>('/api/contacts');
}

export function createContact(payload: { name: string; phone: string; rule: ContactRecord['rule'] }): Promise<ContactRecord> {
  return request<ContactRecord>('/api/contacts', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function deleteContact(contactId: number): Promise<void> {
  return request<void>(`/api/contacts/${contactId}`, {
    method: 'DELETE',
  });
}

export function getCalls(limit = 20): Promise<CallRecord[]> {
  return request<CallRecord[]>(`/api/calls?limit=${limit}`);
}

export function simulateCall(payload: { caller_phone: string; transcript: string }): Promise<CallRecord> {
  return request<CallRecord>('/api/calls/simulate', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export interface DemoCallResponse {
  session_id: string;
  transcript: string;
  agent_reply: string;
  demo_mode: true;
}

export function startDemoCall(payload: { caller_phone: string; caller_name: string }): Promise<DemoCallResponse> {
  return request<DemoCallResponse>('/api/demo/calls', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function sendDemoMessage(sessionId: string, message: string): Promise<DemoCallResponse> {
  return request<DemoCallResponse>(`/api/demo/calls/${encodeURIComponent(sessionId)}/message`, {
    method: 'POST',
    body: JSON.stringify({ message }),
  });
}

export interface PushSubscriptionPayload {
  endpoint: string;
  keys: { p256dh: string; auth: string };
}

export function getPushPublicKey(): Promise<{ enabled: boolean; public_key: string | null }> {
  return request<{ enabled: boolean; public_key: string | null }>('/api/notifications/public-key');
}

export function savePushSubscription(subscription: PushSubscriptionPayload): Promise<{ saved: boolean }> {
  return request<{ saved: boolean }>('/api/notifications/subscriptions', {
    method: 'POST',
    body: JSON.stringify(subscription),
  });
}

export function deletePushSubscription(endpoint: string): Promise<void> {
  return request('/api/notifications/subscriptions', {
    method: 'DELETE',
    body: JSON.stringify({ endpoint }),
  });
}

