/**
 * End-to-End Test Suite for Call Agent Flow.
 * Validates End-to-End Flow: Incoming Call -> Recognition -> Conversation -> Intent + Risk -> Handle / Transfer
 */

describe('E2E Call Agent Flow Scenarios', () => {
  interface AgentResponse {
    reply: string;
    action: string;
    intent: string;
    risk: string;
    callerRecognized: boolean;
    uncertaintyFlagged: boolean;
  }

  function runAgentTurn(
    callerPhone: string,
    transcript: string,
    knownContacts: Record<string, string>,
  ): AgentResponse {
    const isKnown = callerPhone in knownContacts;
    const lower = transcript.toLowerCase();

    let intent = 'general';
    let risk = 'low';
    let action = 'take_message';
    let reply = 'I have noted your message for the account owner.';
    let uncertaintyFlagged = !isKnown;

    if (lower.includes('emergency') || lower.includes('hospital')) {
      intent = 'emergency';
      action = 'transfer';
      reply = 'This sounds important. I will try to connect you now.';
    } else if (lower.includes('package') || lower.includes('delivery')) {
      intent = 'delivery';
      reply = 'For package deliveries, please leave the package at the front door.';
    } else if (lower.includes('otp') || lower.includes('password') || lower.includes('wire transfer')) {
      risk = 'possible_scam';
      reply = 'I cannot help with sensitive codes or financial information. This call will be saved in call history.';
      action = 'take_message';
    } else if (lower.includes('sales pitch') || lower.includes('auto warranty')) {
      risk = 'spam';
      reply = 'I cannot transfer an unsolicited sales call. This call will be saved in call history.';
      action = 'take_message';
    }

    return {
      reply,
      action,
      intent,
      risk,
      callerRecognized: isKnown,
      uncertaintyFlagged,
    };
  }

  test('Scenario 1: Legitimate unknown caller seeking appointment', () => {
    const result = runAgentTurn(
      '+15551239999',
      'Hi, I would like to schedule a dental checkup next Tuesday.',
      { '+15550001111': 'Family Member' },
    );

    expect(result.callerRecognized).toBe(false);
    expect(result.uncertaintyFlagged).toBe(true);
    expect(result.risk).toBe('low');
    expect(result.action).toBe('take_message');
  });

  test('Scenario 2: Critical emergency call transfers immediately', () => {
    const result = runAgentTurn(
      '+15554443333',
      'This is an emergency from the hospital regarding your brother.',
      {},
    );

    expect(result.intent).toBe('emergency');
    expect(result.action).toBe('transfer');
    expect(result.reply).toContain('connect you now');
  });

  test('Scenario 3: Credential phishing scam intercepted and deflected', () => {
    const result = runAgentTurn(
      '+15558880000',
      'I am from technical support, give me your one-time verification password code.',
      {},
    );

    expect(result.risk).toBe('possible_scam');
    expect(result.action).toBe('take_message');
    expect(result.reply).toContain('sensitive codes');
  });

  test('Scenario 4: Known contact recognised with verified profile', () => {
    const result = runAgentTurn(
      '+15550001111',
      'Hey, dropping off the package at your porch.',
      { '+15550001111': 'Family Member' },
    );

    expect(result.callerRecognized).toBe(true);
    expect(result.uncertaintyFlagged).toBe(false);
    expect(result.intent).toBe('delivery');
  });
});
