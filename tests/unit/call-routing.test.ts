/**
 * Unit tests for Call Routing and Schedule Logic.
 */

describe('Call Routing Engine', () => {
  const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

  function normalizePhone(raw: string): string {
    const trimmed = raw.trim();
    const hasPlus = trimmed.startsWith('+');
    const digits = trimmed.replace(/\D/g, '');
    if (digits.length < 7 || digits.length > 15) {
      throw new Error('Invalid phone number length.');
    }
    return hasPlus ? `+${digits}` : digits;
  }

  function isWithinSchedule(start: string, end: string, current: string): boolean {
    const toMinutes = (time: string): number => {
      const [h, m] = time.split(':').map(Number);
      return h * 60 + m;
    };
    const curM = toMinutes(current);
    const startM = toMinutes(start);
    const endM = toMinutes(end);

    if (startM < endM) {
      return curM >= startM && curM < endM;
    }
    // Overnight window (e.g. 22:00 to 06:00)
    return curM >= startM || curM < endM;
  }

  test('normalizes varied international phone numbers', () => {
    expect(normalizePhone('+1 (555) 123-4567')).toBe('+15551234567');
    expect(normalizePhone('+91 98765-43210')).toBe('+919876543210');
    expect(normalizePhone('  5550001234  ')).toBe('5550001234');
  });

  test('rejects phone numbers with invalid digit counts', () => {
    expect(() => normalizePhone('123')).toThrow('Invalid phone number length.');
    expect(() => normalizePhone('12345678901234567')).toThrow('Invalid phone number length.');
  });

  test('evaluates daytime working schedule correctly', () => {
    const start = '09:00';
    const end = '17:00';
    expect(isWithinSchedule(start, end, '09:00')).toBe(true);
    expect(isWithinSchedule(start, end, '12:30')).toBe(true);
    expect(isWithinSchedule(start, end, '16:59')).toBe(true);
    expect(isWithinSchedule(start, end, '17:00')).toBe(false);
    expect(isWithinSchedule(start, end, '08:59')).toBe(false);
  });

  test('evaluates overnight schedule crossing midnight', () => {
    const start = '22:00';
    const end = '06:00';
    expect(isWithinSchedule(start, end, '23:30')).toBe(true);
    expect(isWithinSchedule(start, end, '02:15')).toBe(true);
    expect(isWithinSchedule(start, end, '05:59')).toBe(true);
    expect(isWithinSchedule(start, end, '06:00')).toBe(false);
    expect(isWithinSchedule(start, end, '15:00')).toBe(false);
  });

  test('routes contacts according to personalized rules', () => {
    type Rule = 'always_screen' | 'always_message' | 'always_transfer' | 'delivery_agent' | 'block_reject';
    function determineAction(rule: Rule, risk: string, hasOwnerPhone: boolean): string {
      if (rule === 'block_reject') return 'take_message';
      if (risk === 'possible_scam' || risk === 'spam') return 'take_message';
      if (rule === 'always_transfer' && hasOwnerPhone && (risk === 'low' || risk === 'unknown')) return 'transfer';
      return 'take_message';
    }

    expect(determineAction('always_transfer', 'low', true)).toBe('transfer');
    expect(determineAction('always_transfer', 'possible_scam', true)).toBe('take_message'); // Risk override
    expect(determineAction('always_message', 'low', true)).toBe('take_message');
    expect(determineAction('block_reject', 'low', true)).toBe('take_message');
  });
});
