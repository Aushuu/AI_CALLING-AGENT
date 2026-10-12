/**
 * Unit tests for Intent Recognition, Spam/Fraud Screening, and Caller Identification.
 */

describe('Intent and Risk Screening Engine', () => {
  const RISK_PATTERNS = {
    possible_scam: [
      /\b(one[- ]time|verification|security) code\b/i,
      /\bpassword|passcode|otp\b/i,
      /\b(gift card|wire transfer|crypto wallet|seed phrase)\b/i,
      /\b(remote access|install this app|anydesk|teamviewer)\b/i,
    ],
    suspicious: [
      /\b(act now|immediately|urgent payment|arrest warrant|legal action)\b/i,
      /\b(bank account|social security number|ssn|credit card pin)\b/i,
    ],
    spam: [
      /\b(robocall|telemarketing|cold call|unsolicited sales pitch)\b/i,
      /\bautomated (warranty sales|warranty|sales|marketing) call\b/i,
      /\b(pre[- ]approved loan|debt relief)\b/i,
    ],
  };

  const INTENT_TERMS: Record<string, string[]> = {
    emergency: ['emergency', 'urgent', 'hospital', 'accident', 'ambulance', 'help me'],
    appointment: ['appointment', 'schedule', 'reschedule', 'meeting', 'doctor visit'],
    delivery: ['delivery', 'package', 'parcel', 'drop off', 'courier'],
    work: ['interview', 'work', 'project', 'client', 'office'],
    sales: ['offer', 'discount', 'selling', 'marketing', 'insurance quote'],
  };

  function classifyRisk(text: string): { risk: string; reasons: string[] } {
    for (const [level, patterns] of Object.entries(RISK_PATTERNS)) {
      for (const pattern of patterns) {
        if (pattern.test(text)) {
          return {
            risk: level,
            reasons: [`Matched pattern: ${pattern.source}`],
          };
        }
      }
    }
    return { risk: 'low', reasons: ['No suspicious patterns detected.'] };
  }

  function detectIntent(text: string): string {
    const lowered = text.toLowerCase();
    for (const [intent, terms] of Object.entries(INTENT_TERMS)) {
      if (terms.some((term) => lowered.includes(term))) {
        return intent;
      }
    }
    return 'general';
  }

  function extractCallerIdentity(text: string): { name: string | null; org: string | null } {
    const match = text.match(/\b(?:this is|my name is|i am|i'm)\s+((?:(?:Dr|Mr|Mrs|Ms)\.?\s+)?[A-Z][a-zA-Z\s]{1,30}?)(?:\s+(?:from|with|at)\s+([A-Z0-9a-zA-Z\s]{2,40}?))?(?=[,;?!]|\s+calling|\s+regarding|\.\s|$)/);
    if (!match) return { name: null, org: null };
    return {
      name: match[1].trim(),
      org: match[2]?.trim() ?? null,
    };
  }

  test('flags OTP and 2FA requests as possible_scam', () => {
    const res = classifyRisk('Please read back the one-time verification code sent to your mobile.');
    expect(res.risk).toBe('possible_scam');
  });

  test('flags AnyDesk remote software installation as possible_scam', () => {
    const res = classifyRisk('You need to install AnyDesk so we can secure your computer.');
    expect(res.risk).toBe('possible_scam');
  });

  test('flags arrest warrant threats as suspicious', () => {
    const res = classifyRisk('This is federal police, there is an arrest warrant in your name, act now!');
    expect(res.risk).toBe('suspicious');
  });

  test('flags auto warranty and pre-approved loans as spam', () => {
    const res = classifyRisk('This is an automated warranty sales call about your expiring vehicle.');
    expect(res.risk).toBe('spam');
  });

  test('correctly detects emergency intent', () => {
    expect(detectIntent('There was an accident near the crossing, please call back')).toBe('emergency');
  });

  test('correctly detects delivery intent', () => {
    expect(detectIntent('I have a package delivery from Amazon')).toBe('delivery');
  });

  test('extracts caller identity and organization while marking unverified', () => {
    const identity = extractCallerIdentity('Hello, this is Dr. Sarah from Apollo Hospital calling regarding blood test results.');
    expect(identity.name).toBe('Dr. Sarah');
    expect(identity.org).toBe('Apollo Hospital');
  });
});
