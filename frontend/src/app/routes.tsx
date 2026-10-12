import React from 'react';

export type AppRoute = 'voice' | 'schedule' | 'contacts' | 'dialer' | 'history' | 'setup';

export interface RouteItem {
  id: AppRoute;
  label: string;
  icon: string;
  description: string;
}

export const APP_ROUTES: RouteItem[] = [
  {
    id: 'voice',
    label: 'Voice Call Center',
    icon: '🎙️',
    description: 'Multi-turn live voice screening with speech recognition & audio synthesis.',
  },
  {
    id: 'schedule',
    label: 'Agent Mode & Schedule',
    icon: '⚙️',
    description: 'Manual mode toggle and customizable automated schedule windows.',
  },
  {
    id: 'contacts',
    label: 'Known Contacts & Rules',
    icon: '👥',
    description: 'Personalized rules for VIPs, delivery agents, and blocklists.',
  },
  {
    id: 'dialer',
    label: 'Cellular Dialer',
    icon: '📶',
    description: 'Native cellular telephony dialer requiring zero internet connectivity.',
  },
  {
    id: 'history',
    label: 'Call History',
    icon: '📜',
    description: 'Detailed records with intent, risk signals, and decision rationale.',
  },
  {
    id: 'setup',
    label: 'Setup Guide',
    icon: '🔧',
    description: 'Carrier conditional call forwarding and Twilio BYOC interconnect instructions.',
  },
];

export default APP_ROUTES;
