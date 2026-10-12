/**
 * Central Application Configuration.
 * Defines configuration defaults, screening thresholds, telephony routes, and schedule profiles.
 */

export interface TelephonyConfig {
  defaultLanguage: string;
  speechTimeoutSeconds: number;
  maxSilenceReprompts: number;
  dtmfEnabled: boolean;
  cellularScheme: 'tel:';
  byocInterconnectSupported: boolean;
}

export interface ScreeningPolicy {
  minimumConfidenceThreshold: number;
  autoTransferEmergencies: boolean;
  prohibitSensitiveTransfers: boolean;
  allowedIntents: string[];
  riskLevels: ('low' | 'unknown' | 'spam' | 'suspicious' | 'possible_scam')[];
  personalizedRules: ('always_screen' | 'always_message' | 'always_transfer' | 'delivery_agent' | 'block_reject')[];
}

export interface AppConfig {
  appName: string;
  version: string;
  apiBaseUrl: string;
  defaultTimezone: string;
  telephony: TelephonyConfig;
  screening: ScreeningPolicy;
  schedulePresets: Array<{
    name: string;
    description: string;
    start: string;
    end: string;
    days: string[];
  }>;
}

export const applicationConfig: AppConfig = {
  appName: 'AI-Powered Personal Call Agent',
  version: '2.0.0',
  apiBaseUrl: typeof process !== 'undefined' && process.env?.VITE_API_BASE_URL ? process.env.VITE_API_BASE_URL : 'http://127.0.0.1:8000',
  defaultTimezone: 'UTC',

  telephony: {
    defaultLanguage: 'en-US',
    speechTimeoutSeconds: 5,
    maxSilenceReprompts: 2,
    dtmfEnabled: true,
    cellularScheme: 'tel:',
    byocInterconnectSupported: true,
  },

  screening: {
    minimumConfidenceThreshold: 0.4,
    autoTransferEmergencies: true,
    prohibitSensitiveTransfers: true,
    allowedIntents: [
      'emergency',
      'appointment',
      'delivery',
      'work',
      'sales',
      'general',
      'unclear',
    ],
    riskLevels: ['low', 'unknown', 'spam', 'suspicious', 'possible_scam'],
    personalizedRules: [
      'always_screen',
      'always_message',
      'always_transfer',
      'delivery_agent',
      'block_reject',
    ],
  },

  schedulePresets: [
    {
      name: 'Business Working Hours',
      description: 'Screen calls during Monday-Friday office hours',
      start: '09:00',
      end: '17:00',
      days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday'],
    },
    {
      name: 'Evening Quiet Hours',
      description: 'Screen evening calls so you can unwind',
      start: '18:00',
      end: '22:00',
      days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    },
    {
      name: 'Overnight Sleep Shield',
      description: 'Filter late-night calls and only permit emergencies',
      start: '22:00',
      end: '07:00',
      days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    },
    {
      name: 'All-Day Focus Mode',
      description: 'Screen all calls around the clock',
      start: '00:00',
      end: '23:59',
      days: ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'],
    },
  ],
};

export default applicationConfig;
