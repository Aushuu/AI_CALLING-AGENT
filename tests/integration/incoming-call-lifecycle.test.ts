/**
 * Integration tests for Incoming Call Lifecycle:
 * Incoming Call -> Caller Recognition -> Voice Conversation -> Judging Focus (Intent + Risk) -> Handle / Transfer
 */

describe('Incoming Call Lifecycle Integration Flow', () => {
  interface CallSession {
    callSid: string;
    from: string;
    contactName: string | null;
    isKnown: boolean;
    transcript: string[];
    intent: string;
    urgency: string;
    risk: string;
    action: 'take_message' | 'transfer' | 'clarify';
    status: 'in-progress' | 'transferred' | 'completed';
  }

  function simulateCallLifecycle(
    fromNumber: string,
    contacts: Map<string, { name: string; rule: string }>,
    speechTurns: string[],
    ownerPhone?: string,
  ): CallSession {
    const contact = contacts.get(fromNumber);
    const session: CallSession = {
      callSid: `CA-${Math.random().toString(36).substring(7)}`,
      from: fromNumber,
      contactName: contact ? contact.name : null,
      isKnown: Boolean(contact),
      transcript: [],
      intent: 'general',
      urgency: 'low',
      risk: 'low',
      action: 'take_message',
      status: 'in-progress',
    };

    // Process speech turns
    for (const turn of speechTurns) {
      session.transcript.push(`Caller: ${turn}`);

      if (/accident|emergency|hospital/i.test(turn)) {
        session.intent = 'emergency';
        session.urgency = 'high';
      } else if (/delivery|package/i.test(turn)) {
        session.intent = 'delivery';
      }

      if (/otp|verification code|password|anydesk/i.test(turn)) {
        session.risk = 'possible_scam';
      } else if (/warranty|unsolicited sales/i.test(turn)) {
        session.risk = 'spam';
      }

      // Decision logic
      if (session.risk === 'possible_scam' || session.risk === 'spam') {
        session.action = 'take_message';
      } else if (contact?.rule === 'always_transfer' && ownerPhone) {
        session.action = 'transfer';
        session.status = 'transferred';
      } else if (session.intent === 'emergency' && ownerPhone) {
        session.action = 'transfer';
        session.status = 'transferred';
      } else {
        session.action = 'take_message';
      }
    }

    if (session.status !== 'transferred') {
      session.status = 'completed';
    }

    return session;
  }

  const contactsBook = new Map<string, { name: string; rule: string }>([
    ['+15551112222', { name: 'Alice Manager', rule: 'always_transfer' }],
    ['+15553334444', { name: 'Bob Friend', rule: 'always_message' }],
  ]);

  test('known VIP caller triggers immediate intelligent transfer', () => {
    const session = simulateCallLifecycle(
      '+15551112222',
      contactsBook,
      ['Hi, this is Alice calling about the urgent board meeting.'],
      '+15559990000',
    );

    expect(session.isKnown).toBe(true);
    expect(session.contactName).toBe('Alice Manager');
    expect(session.action).toBe('transfer');
    expect(session.status).toBe('transferred');
  });

  test('scam attempt by known number overrides transfer rule to protect owner', () => {
    const session = simulateCallLifecycle(
      '+15551112222',
      contactsBook,
      ['Alice here, I urgently need your 6 digit OTP code to access the account.'],
      '+15559990000',
    );

    expect(session.risk).toBe('possible_scam');
    expect(session.action).toBe('take_message'); // Blocked transfer
    expect(session.status).toBe('completed');
  });

  test('unknown caller with emergency escalates to owner', () => {
    const session = simulateCallLifecycle(
      '+15557778888',
      contactsBook,
      ['Hello, there has been an accident involving your car, please connect me!'],
      '+15559990000',
    );

    expect(session.isKnown).toBe(false);
    expect(session.intent).toBe('emergency');
    expect(session.urgency).toBe('high');
    expect(session.action).toBe('transfer');
  });

  test('delivery package handled politely without interrupting owner', () => {
    const session = simulateCallLifecycle(
      '+15558889999',
      contactsBook,
      ['FedEx delivery driver here with your package.'],
      '+15559990000',
    );

    expect(session.intent).toBe('delivery');
    expect(session.action).toBe('take_message');
    expect(session.status).toBe('completed');
  });
});
