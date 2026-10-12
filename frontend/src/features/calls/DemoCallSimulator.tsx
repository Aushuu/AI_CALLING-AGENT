import { type FormEvent, useEffect, useRef, useState } from 'react';
import { sendDemoMessage, startDemoCall } from '../../services/apiClient';
import CallDecisionPanel from '../../components/CallDecisionPanel';
import { soundEffects } from '../../services/soundEffects';
import type { CallRecord } from '../../types/call';

interface ConversationMessage {
  speaker: string;
  text: string;
}

interface CallerPersona {
  id: string;
  label: string;
  name: string;
  phone: string;
  initialMessage: string;
  expectedIntent: string;
  expectedRisk: string;
}

const callerPersonas: CallerPersona[] = [
  {
    id: 'doctor',
    label: '🩺 Dr. Sarah (Hospital)',
    name: 'Dr. Sarah',
    phone: '+15554321000',
    initialMessage: 'Hello, this is Dr. Sarah from Apollo Hospital calling regarding blood test results.',
    expectedIntent: 'Appointment / Medical',
    expectedRisk: 'Low (Benign)',
  },
  {
    id: 'delivery',
    label: '📦 FedEx Courier',
    name: 'FedEx Driver',
    phone: '+15557890123',
    initialMessage: 'Hi, this is FedEx package delivery. I am outside your gate and need drop-off instructions.',
    expectedIntent: 'Package Delivery',
    expectedRisk: 'Low (Delivery)',
  },
  {
    id: 'emergency',
    label: '🚨 Emergency Escalation',
    name: 'Neighbor Mark',
    phone: '+15559998888',
    initialMessage: 'Urgent emergency! There is water flooding out of your main pipeline, please contact me immediately!',
    expectedIntent: 'Emergency',
    expectedRisk: 'Low (High Urgency)',
  },
  {
    id: 'scam_otp',
    label: '🛡️ Bank OTP Phishing Scam',
    name: 'Fraud Security Team',
    phone: '+15556667777',
    initialMessage: 'This is security verification from your bank. We detected suspicious access; read me your one-time verification password OTP right now.',
    expectedIntent: 'Security Inquiry',
    expectedRisk: 'Possible Scam (Phishing)',
  },
  {
    id: 'spam_warranty',
    label: '📢 Auto Warranty Robocall',
    name: 'National Auto Warranty',
    phone: '+15551113333',
    initialMessage: 'This is an automated warranty sales call. Your vehicle warranty has expired; press 1 for our exclusive discount.',
    expectedIntent: 'Sales Pitch',
    expectedRisk: 'Spam (Telemarketing)',
  },
  {
    id: 'unknown_clarify',
    label: '❓ Ambiguous Unknown Caller',
    name: 'Unknown Caller',
    phone: '+15550009999',
    initialMessage: 'Hey are you there? I really need to talk to you about something important.',
    expectedIntent: 'Unclear / General',
    expectedRisk: 'Unknown (Needs Clarification)',
  },
];

function parseTranscript(transcript: string): ConversationMessage[] {
  return transcript.split('\n').flatMap((line) => {
    const separator = line.indexOf(':');
    if (separator < 1) return [];
    const speaker = line.slice(0, separator).trim();
    const text = line.slice(separator + 1).trim();
    return speaker && text ? [{ speaker, text }] : [];
  });
}

// Browser SpeechRecognition interface
interface IWindowSpeechRecognition extends EventTarget {
  continuous: boolean;
  interimResults: boolean;
  lang: string;
  start: () => void;
  stop: () => void;
  onresult: ((event: { results: Array<Array<{ transcript: string }>> }) => void) | null;
  onerror: (() => void) | null;
  onend: (() => void) | null;
}

export default function DemoCallSimulator({ onSaved }: { onSaved?: () => void }) {
  const [callerName, setCallerName] = useState('Demo caller');
  const [callerPhone, setCallerPhone] = useState('+15550000000');
  const [message, setMessage] = useState('');
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [messages, setMessages] = useState<ConversationMessage[]>([]);
  const [currentCall, setCurrentCall] = useState<Partial<CallRecord> | null>(null);
  const [callState, setCallState] = useState<'idle' | 'ringing' | 'connected' | 'ended'>('idle');
  const [callDuration, setCallDuration] = useState(0);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [isListening, setIsListening] = useState(false);
  const [isSpeaking, setIsSpeaking] = useState(false);

  const recognitionRef = useRef<IWindowSpeechRecognition | null>(null);
  const timerRef = useRef<number | null>(null);

  // Active call duration timer
  useEffect(() => {
    if (callState === 'connected') {
      timerRef.current = window.setInterval(() => {
        setCallDuration((prev) => prev + 1);
      }, 1000);
    } else {
      if (timerRef.current !== null) {
        clearInterval(timerRef.current);
        timerRef.current = null;
      }
      if (callState === 'idle') setCallDuration(0);
    }
    return () => {
      if (timerRef.current !== null) clearInterval(timerRef.current);
    };
  }, [callState]);

  // Clean up sounds on unmount
  useEffect(() => {
    return () => {
      soundEffects.stopTelephoneRing();
      soundEffects.stopSpeaking();
    };
  }, []);

  const formatTimer = (seconds: number): string => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins.toString().padStart(2, '0')}:${secs.toString().padStart(2, '0')}`;
  };

  const handleSelectPersona = (persona: CallerPersona) => {
    setCallerName(persona.name);
    setCallerPhone(persona.phone);
    setMessage(persona.initialMessage);
  };

  const speakAgentReply = (text: string) => {
    if (!ttsEnabled) return;
    soundEffects.speakText(
      text,
      () => setIsSpeaking(true),
      () => setIsSpeaking(false)
    );
  };

  const handleStart = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError('');
    setCallState('ringing');
    soundEffects.startTelephoneRing();

    try {
      // Simulate 1.5s telephone ringing before AI answers
      await new Promise((resolve) => setTimeout(resolve, 1500));
      soundEffects.stopTelephoneRing();
      soundEffects.playCallConnected();

      const result = await startDemoCall({ caller_name: callerName, caller_phone: callerPhone });
      setSessionId(result.session_id);
      setCallState('connected');
      setCurrentCall(result as unknown as CallRecord);

      const parsed = parseTranscript(result.transcript);
      setMessages([...parsed, { speaker: 'Agent', text: result.agent_reply }]);
      speakAgentReply(result.agent_reply);
      onSaved?.();
    } catch (startError) {
      soundEffects.stopTelephoneRing();
      setCallState('idle');
      setError(startError instanceof Error ? startError.message : 'Unable to start the call session.');
    } finally {
      setBusy(false);
    }
  };

  const handleSend = async (event?: FormEvent<HTMLFormElement>, textToSend?: string) => {
    event?.preventDefault();
    const cleanedMessage = (textToSend ?? message).trim();
    if (!sessionId || !cleanedMessage) return;

    setBusy(true);
    setError('');
    try {
      const result = await sendDemoMessage(sessionId, cleanedMessage);
      setMessages(parseTranscript(result.transcript));
      setCurrentCall(result as unknown as CallRecord);
      setMessage('');
      speakAgentReply(result.agent_reply);
      onSaved?.();
    } catch (sendError) {
      setError(sendError instanceof Error ? sendError.message : 'Unable to send the caller message.');
    } finally {
      setBusy(false);
    }
  };

  const handleEndCall = () => {
    soundEffects.stopTelephoneRing();
    soundEffects.stopSpeaking();
    soundEffects.playCallEnded();
    setCallState('ended');
  };

  const handleNewSession = () => {
    soundEffects.stopTelephoneRing();
    soundEffects.stopSpeaking();
    setSessionId(null);
    setMessages([]);
    setCurrentCall(null);
    setMessage('');
    setError('');
    setCallState('idle');
    setCallDuration(0);
  };

  // Web Speech Recognition (Microphone Speech-to-Text)
  const toggleSpeechRecognition = () => {
    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const SpeechRecClass =
      (window as unknown as { SpeechRecognition?: new () => IWindowSpeechRecognition }).SpeechRecognition ||
      (window as unknown as { webkitSpeechRecognition?: new () => IWindowSpeechRecognition }).webkitSpeechRecognition;

    if (!SpeechRecClass) {
      setError('Web Speech Recognition is not supported by your browser. Please type your message.');
      return;
    }

    try {
      const recognition = new SpeechRecClass();
      recognition.lang = 'en-US';
      recognition.continuous = false;
      recognition.interimResults = false;

      recognition.onresult = (e) => {
        const spoken = e.results[0]?.[0]?.transcript || '';
        if (spoken) {
          setMessage(spoken);
          void handleSend(undefined, spoken);
        }
      };

      recognition.onerror = () => {
        setIsListening(false);
      };

      recognition.onend = () => {
        setIsListening(false);
      };

      recognition.start();
      recognitionRef.current = recognition;
      setIsListening(true);
    } catch {
      setIsListening(false);
    }
  };

  return (
    <section className="panel demo-call-panel" aria-labelledby="demo-call-title">
      <div className="demo-call-heading">
        <div>
          <h2 id="demo-call-title">Live Voice & Audio Call Simulator</h2>
          <p className="muted">
            Hold a multi-turn voice interaction with the AI assistant. Speak into your microphone or type to test caller recognition, intent extraction, fraud screening, and intelligent transfer decisions.
          </p>
        </div>
        <div className="call-header-controls">
          <button
            type="button"
            className={`secondary tts-toggle-btn ${ttsEnabled ? 'active' : ''}`}
            onClick={() => {
              if (ttsEnabled) soundEffects.stopSpeaking();
              setTtsEnabled(!ttsEnabled);
            }}
            title={ttsEnabled ? 'Mute AI voice output' : 'Enable AI voice output'}
          >
            {ttsEnabled ? '🔊 Voice On' : '🔇 Muted'}
          </button>
          {sessionId && (
            <button type="button" className="secondary" onClick={handleNewSession} disabled={busy}>
              New Call
            </button>
          )}
        </div>
      </div>

      {!sessionId ? (
        <div className="pre-call-container">
          <div className="persona-presets-box">
            <span className="preset-label">Quick Test Personas (Click to Load):</span>
            <div className="persona-grid">
              {callerPersonas.map((p) => (
                <button
                  key={p.id}
                  type="button"
                  className="secondary persona-card-btn"
                  onClick={() => handleSelectPersona(p)}
                >
                  <strong>{p.label}</strong>
                  <small className="subtle">{p.expectedIntent} · {p.expectedRisk}</small>
                </button>
              ))}
            </div>
          </div>

          <form className="demo-start-form" onSubmit={handleStart}>
            <div className="form-fields-grid">
              <label>
                Caller Name / Identity
                <input
                  value={callerName}
                  onChange={(event) => setCallerName(event.target.value)}
                  maxLength={80}
                  placeholder="e.g. Dr. Sarah or Unknown Caller"
                />
              </label>
              <label>
                Caller Phone Number
                <input
                  type="tel"
                  value={callerPhone}
                  onChange={(event) => setCallerPhone(event.target.value)}
                  placeholder="+15551234567"
                  required
                />
              </label>
            </div>
            <button type="submit" className="start-call-btn" disabled={busy}>
              {busy ? 'Initiating Call...' : '📞 Place Call to Agent'}
            </button>
          </form>
        </div>
      ) : (
        <div className="active-call-layout">
          <div className="call-interface-col">
            <div className="active-call-banner">
              <div className="caller-info">
                <span className="call-status-badge">
                  {callState === 'ringing'
                    ? '🔔 Ringing...'
                    : callState === 'connected'
                    ? `🟢 Connected · ${formatTimer(callDuration)}`
                    : '🔴 Call Ended'}
                </span>
                <strong>{callerName || 'Unknown Caller'}</strong>
                <span className="subtle">{callerPhone}</span>
              </div>
              <div className="call-actions-top">
                {callState === 'connected' && (
                  <button type="button" className="danger hangup-btn" onClick={handleEndCall}>
                    Hang Up
                  </button>
                )}
              </div>
            </div>

            {/* Voice Wave Animation */}
            {callState === 'connected' && (
              <div className={`audio-waveform ${isSpeaking ? 'speaking' : isListening ? 'listening' : ''}`} aria-hidden="true">
                <div className="wave-bar bar-1" />
                <div className="wave-bar bar-2" />
                <div className="wave-bar bar-3" />
                <div className="wave-bar bar-4" />
                <div className="wave-bar bar-5" />
                <span className="waveform-label">
                  {isSpeaking ? 'AI Agent Speaking...' : isListening ? 'Listening to Caller Microphone...' : 'In Call · Waiting for Speech'}
                </span>
              </div>
            )}

            <ol className="demo-transcript" aria-label="Call transcript" aria-live="polite">
              {messages.map((turn, index) => (
                <li
                  key={`${index}-${turn.speaker}`}
                  className={`demo-turn ${turn.speaker.toLowerCase() === 'agent' ? 'demo-agent-turn' : 'demo-caller-turn'}`}
                >
                  <span className="turn-speaker-badge">{turn.speaker}</span>
                  <p>{turn.text}</p>
                </li>
              ))}
            </ol>

            {callState === 'connected' ? (
              <form className="demo-message-form" onSubmit={(e) => handleSend(e)}>
                <label htmlFor="demo-caller-message">Caller Speech Turn</label>
                <div className="demo-message-controls">
                  <input
                    id="demo-caller-message"
                    value={message}
                    onChange={(event) => setMessage(event.target.value)}
                    maxLength={1500}
                    placeholder="Speak into mic or type what caller says..."
                    required
                  />
                  <button
                    type="button"
                    className={`mic-btn ${isListening ? 'listening' : ''}`}
                    onClick={toggleSpeechRecognition}
                    title={isListening ? 'Stop listening' : 'Speak into microphone'}
                  >
                    {isListening ? '🛑 Stop' : '🎤 Speak'}
                  </button>
                  <button type="submit" disabled={busy || !message.trim()}>
                    {busy ? 'Replying…' : 'Send Turn'}
                  </button>
                </div>
              </form>
            ) : (
              <div className="call-ended-summary">
                <p>Call concluded. You can review the judging focus, transcript, and risk rationale on the right.</p>
                <button type="button" className="secondary" onClick={handleNewSession}>
                  Start Another Call
                </button>
              </div>
            )}
          </div>

          <div className="judging-focus-col">
            <CallDecisionPanel call={currentCall} />
          </div>
        </div>
      )}

      {error && <p className="status-warn" role="alert">{error}</p>}
    </section>
  );
}
