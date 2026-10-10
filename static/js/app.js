(() => {
  "use strict";

  const elements = {
    agentStatus: document.getElementById("agentStatus"),
    agentStatusText: document.getElementById("agentStatusText"),
    agentToggle: document.getElementById("agentToggle"),
    callDuration: document.getElementById("callDuration"),
    callForm: document.getElementById("callForm"),
    callerId: document.getElementById("callerId"),
    callerMatch: document.getElementById("callerMatch"),
    connectionBadge: document.getElementById("connectionBadge"),
    connectionText: document.getElementById("connectionText"),
    conversationEmpty: document.getElementById("conversationEmpty"),
    contactForm: document.getElementById("contactForm"),
    contactList: document.getElementById("contactList"),
    contactsEmpty: document.getElementById("contactsEmpty"),
    contactName: document.getElementById("contactName"),
    contactPhone: document.getElementById("contactPhone"),
    contactRule: document.getElementById("contactRule"),
    contactNotes: document.getElementById("contactNotes"),
    decisionPanel: document.getElementById("decisionPanel"),
    decisionTitle: document.getElementById("decisionTitle"),
    decisionSummary: document.getElementById("decisionSummary"),
    decisionReason: document.getElementById("decisionReason"),
    riskChip: document.getElementById("riskChip"),
    transferCall: document.getElementById("transferCall"),
    transferHint: document.getElementById("transferHint"),
    endCall: document.getElementById("endCall"),
    messageFeed: document.getElementById("messageFeed"),
    recordCount: document.getElementById("recordCount"),
    refreshLogs: document.getElementById("refreshLogs"),
    registryEmpty: document.getElementById("registryEmpty"),
    registryList: document.getElementById("registryList"),
    registrySubtitle: document.getElementById("registrySubtitle"),
    settingsForm: document.getElementById("settingsForm"),
    scheduleEnabled: document.getElementById("scheduleEnabled"),
    scheduleStart: document.getElementById("scheduleStart"),
    scheduleEnd: document.getElementById("scheduleEnd"),
    timeZone: document.getElementById("timeZone"),
    transferNumber: document.getElementById("transferNumber"),
    userPreferences: document.getElementById("userPreferences"),
    preferencesSaveState: document.getElementById("preferencesSaveState"),
    importDeviceContacts: document.getElementById("importDeviceContacts"),
    logoutButton: document.getElementById("logoutButton"),
    startCall: document.getElementById("startCall"),
    toast: document.getElementById("toast"),
    transcriptStatus: document.getElementById("transcriptStatus"),
    transcriptStatusText: document.getElementById("transcriptStatusText"),
  };

  const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
  const state = {
    active: true,
    manualActive: true,
    agentSource: "manual",
    callActive: false,
    ending: false,
    socket: null,
    recognition: null,
    callId: null,
    startedAt: null,
    durationTimer: null,
    latestClassification: "General Inquiry",
    latestSummary: "The call ended without a message.",
    messages: [],
    contacts: [],
    transferNumber: "",
    toastTimer: null,
  };

  function showToast(message, kind = "info") {
    elements.toast.textContent = message;
    elements.toast.dataset.kind = kind;
    elements.toast.classList.add("is-visible");
    window.clearTimeout(state.toastTimer);
    state.toastTimer = window.setTimeout(() => elements.toast.classList.remove("is-visible"), 3800);
  }

  function setConnection(label, connectionState = "ready") {
    elements.connectionText.textContent = label;
    elements.connectionBadge.dataset.state = connectionState;
  }

  function setListening(listening, message) {
    elements.transcriptStatus.dataset.listening = String(listening);
    elements.transcriptStatusText.textContent = message;
  }

  function setAgentState(agent) {
    state.active = Boolean(agent.active);
    state.manualActive = Boolean(agent.manual_active ?? agent.active);
    state.agentSource = agent.source || (state.active ? "manual" : "offline");
    elements.agentStatus.dataset.active = String(state.active);
    elements.agentStatusText.textContent = state.active
      ? `Agent active · ${state.agentSource}`
      : "Agent offline";
    elements.agentToggle.setAttribute("aria-pressed", String(state.manualActive));
    elements.agentToggle.setAttribute(
      "aria-label",
      state.manualActive ? "Disable manual agent mode" : "Enable manual agent mode",
    );
  }

  async function requestJson(url, options = {}) {
    const response = await fetch(url, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    let payload;
    try {
      payload = await response.json();
    } catch {
      payload = {};
    }
    if (!response.ok) throw new Error(payload.error || `Request failed (${response.status})`);
    return payload;
  }

  function appendMessage(speaker, text, classification = null) {
    const content = String(text || "").trim();
    if (!content) return;
    elements.conversationEmpty.hidden = true;
    const wrapper = document.createElement("article");
    wrapper.className = `message ${speaker === "agent" ? "message-agent" : "message-caller"}`;
    const meta = document.createElement("div");
    meta.className = "message-meta";
    const name = document.createElement("span");
    name.textContent = speaker === "agent" ? "CALL AGENT" : "CALLER";
    meta.append(name);
    if (classification) {
      const badge = document.createElement("span");
      badge.className = "classification-tag";
      badge.dataset.classification = classification;
      badge.textContent = classification.toUpperCase();
      meta.append(badge);
    }
    const bubble = document.createElement("div");
    bubble.className = "message-bubble";
    bubble.textContent = content;
    wrapper.append(meta, bubble);
    elements.messageFeed.append(wrapper);
    elements.messageFeed.scrollTop = elements.messageFeed.scrollHeight;
    state.messages.push({ speaker, text: content });
  }

  function speak(text) {
    if (!("speechSynthesis" in window) || !text) return;
    window.speechSynthesis.cancel();
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 1;
    window.speechSynthesis.speak(utterance);
  }

  function formatDuration(seconds) {
    const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
    const remainder = (seconds % 60).toString().padStart(2, "0");
    return `${minutes}:${remainder}`;
  }

  function updateDuration() {
    if (!state.startedAt) return;
    elements.callDuration.textContent = formatDuration(Math.floor((Date.now() - state.startedAt) / 1000));
  }

  function addCallRecord(record) {
    elements.registryEmpty.hidden = true;
    const article = document.createElement("article");
    article.className = "call-record";
    const top = document.createElement("div");
    top.className = "record-top";
    const caller = document.createElement("strong");
    caller.className = "record-caller";
    caller.textContent = record.caller_id || "Unknown caller";
    const date = document.createElement("time");
    date.className = "record-time";
    date.dateTime = record.timestamp || "";
    date.textContent = formatTimestamp(record.timestamp);
    top.append(caller, date);

    const meta = document.createElement("div");
    meta.className = "record-meta";
    const badge = document.createElement("span");
    badge.className = "classification-tag";
    badge.dataset.classification = record.classification || "General Inquiry";
    badge.textContent = String(record.classification || "General Inquiry").toUpperCase();
    const duration = document.createElement("span");
    duration.className = "record-duration";
    duration.textContent = `${Math.max(0, Number(record.duration_seconds) || 0)} SEC`;
    meta.append(badge, duration);
    const decisionMeta = document.createElement("div");
    decisionMeta.className = "registry-decision";
    const decision = document.createElement("span");
    decision.className = "decision-chip";
    decision.dataset.decision = record.decision || "Handle";
    decision.textContent = String(record.decision || "Handle").toUpperCase();
    const risk = document.createElement("span");
    risk.className = "risk-chip";
    risk.dataset.risk = record.risk_level || "Medium";
    risk.textContent = `${String(record.risk_level || "Medium").toUpperCase()} RISK`;
    decisionMeta.append(decision, risk);

    const summary = document.createElement("p");
    summary.className = "record-summary";
    summary.textContent = record.decision_reason || record.summary || "No call summary available.";
    article.append(top, meta, decisionMeta, summary);
    elements.registryList.append(article);
  }

  function formatTimestamp(timestamp) {
    if (!timestamp) return "JUST NOW";
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return "RECENT";
    return new Intl.DateTimeFormat(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" }).format(date);
  }

  async function loadLogs() {
    elements.refreshLogs.classList.add("is-loading");
    try {
      const payload = await requestJson("/api/logs", { method: "GET", headers: {} });
      const logs = Array.isArray(payload.logs) ? payload.logs : [];
      elements.registryList.replaceChildren();
      elements.registryEmpty.hidden = logs.length > 0;
      logs.forEach(addCallRecord);
      elements.recordCount.textContent = `${logs.length} ${logs.length === 1 ? "RECORD" : "RECORDS"}`;
      elements.registrySubtitle.textContent = logs.length ? `Latest of ${logs.length} screened calls` : "Waiting for your first call";
    } catch (error) {
      showToast(error.message || "Unable to load call history.", "error");
    } finally {
      elements.refreshLogs.classList.remove("is-loading");
    }
  }

  async function loadAgentStatus() {
    try {
      const payload = await requestJson("/api/agent", { method: "GET", headers: {} });
      setAgentState(payload);
    } catch (error) {
      showToast(error.message || "Unable to load agent status.", "error");
    }
  }

  async function toggleAgent() {
    const nextActive = !state.manualActive;
    elements.agentToggle.disabled = true;
    try {
      const payload = await requestJson("/api/agent", {
        method: "POST",
        body: JSON.stringify({ active: nextActive }),
      });
      setAgentState(payload);
      showToast(payload.manual_active ? "Manual agent mode is on." : "Manual agent mode is off.");
    } catch (error) {
      showToast(error.message || "Unable to update agent status.", "error");
    } finally {
      elements.agentToggle.disabled = false;
    }
  }

  function setSettingsSaveState(text, kind = "") {
    elements.preferencesSaveState.textContent = text;
    elements.preferencesSaveState.dataset.state = kind;
  }

  function selectedScheduleDays() {
    return Array.from(document.querySelectorAll('input[name="scheduleDay"]:checked'))
      .map((input) => Number(input.value));
  }

  function fillSettings(settings) {
    elements.scheduleEnabled.checked = Boolean(settings.schedule_enabled);
    elements.scheduleStart.value = settings.schedule_start || "09:00";
    elements.scheduleEnd.value = settings.schedule_end || "17:00";
    const browserZone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    elements.timeZone.value = settings.timezone === "UTC" && browserZone ? browserZone : (settings.timezone || browserZone || "UTC");
    elements.transferNumber.value = settings.transfer_number || "";
    elements.userPreferences.value = settings.preferences || "";
    elements.transferNumber.dataset.initial = elements.transferNumber.value;
    const selected = new Set(settings.schedule_days || [0, 1, 2, 3, 4]);
    document.querySelectorAll('input[name="scheduleDay"]').forEach((input) => {
      input.checked = selected.has(Number(input.value));
    });
    state.transferNumber = elements.transferNumber.value;
  }

  async function loadSettings() {
    try {
      const payload = await requestJson("/api/settings", { method: "GET", headers: {} });
      fillSettings(payload.settings || {});
      setAgentState(payload.agent || {});
      setSettingsSaveState("Settings loaded from this device");
    } catch (error) {
      setSettingsSaveState("Unable to load settings", "error");
      showToast(error.message || "Unable to load agent preferences.", "error");
    }
  }

  async function saveSettings(event) {
    event.preventDefault();
    const days = selectedScheduleDays();
    if (!days.length) {
      setSettingsSaveState("Select at least one schedule day", "error");
      return;
    }
    const submit = elements.settingsForm.querySelector('button[type="submit"]');
    submit.disabled = true;
    setSettingsSaveState("Saving settings…");
    try {
      const payload = await requestJson("/api/settings", {
        method: "PUT",
        body: JSON.stringify({
          manual_active: state.manualActive,
          schedule_enabled: elements.scheduleEnabled.checked,
          timezone: elements.timeZone.value.trim(),
          schedule_days: days,
          schedule_start: elements.scheduleStart.value,
          schedule_end: elements.scheduleEnd.value,
          transfer_number: elements.transferNumber.value.trim(),
          preferences: elements.userPreferences.value.trim(),
        }),
      });
      fillSettings(payload.settings);
      setAgentState(payload.agent);
      setSettingsSaveState("Settings saved", "saved");
      showToast("Schedule and personal preferences saved.");
    } catch (error) {
      setSettingsSaveState(error.message || "Could not save settings", "error");
      showToast(error.message || "Unable to save settings.", "error");
    } finally {
      submit.disabled = false;
    }
  }

  function renderContacts() {
    elements.contactList.replaceChildren();
    elements.contactsEmpty.hidden = state.contacts.length > 0;
    for (const contact of state.contacts) {
      const item = document.createElement("article");
      item.className = "contact-item";
      const main = document.createElement("div");
      main.className = "contact-item-main";
      const name = document.createElement("strong");
      name.className = "contact-item-name";
      name.textContent = contact.name;
      const phone = document.createElement("span");
      phone.className = "contact-item-number";
      phone.textContent = contact.phone_number;
      main.append(name, phone);
      const remove = document.createElement("button");
      remove.className = "contact-remove";
      remove.type = "button";
      remove.dataset.phone = contact.phone_number;
      remove.setAttribute("aria-label", `Remove ${contact.name}`);
      remove.title = "Remove caller";
      remove.textContent = "×";
      const rule = document.createElement("span");
      rule.className = "contact-item-rule";
      rule.textContent = {
        screen: "Screen every call",
        always_transfer: "Always transfer to me",
        always_handle: "Let agent handle it",
      }[contact.rule] || "Screen every call";
      item.append(main, remove, rule);
      elements.contactList.append(item);
    }
    updateCallerMatch();
  }

  async function loadContacts() {
    try {
      const payload = await requestJson("/api/contacts", { method: "GET", headers: {} });
      state.contacts = Array.isArray(payload.contacts) ? payload.contacts : [];
      renderContacts();
    } catch (error) {
      showToast(error.message || "Unable to load saved callers.", "error");
    }
  }

  function phoneKey(value) {
    const digits = String(value || "").replace(/\D/g, "");
    return digits.length > 10 ? digits.slice(-10) : digits;
  }

  function updateCallerMatch() {
    const key = phoneKey(elements.callerId.value);
    const match = key ? state.contacts.find((contact) => phoneKey(contact.phone_number) === key) : null;
    elements.callerMatch.textContent = match ? `Recognized: ${match.name}` : "Caller not recognized";
    elements.callerMatch.dataset.known = String(Boolean(match));
  }

  async function addContact(event, contactInput = null) {
    event?.preventDefault();
    const source = contactInput || {
      name: elements.contactName.value.trim(),
      tel: [elements.contactPhone.value.trim()],
    };
    const phone = Array.isArray(source.tel) ? source.tel[0] : source.tel;
    if (!source.name || !phone) {
      showToast("A contact needs a name and phone number.", "error");
      return;
    }
    try {
      await requestJson("/api/contacts", {
        method: "POST",
        body: JSON.stringify({
          name: source.name,
          phone_number: phone,
          rule: contactInput ? "screen" : elements.contactRule.value,
          notes: contactInput ? "Imported from device contacts." : elements.contactNotes.value,
        }),
      });
      if (!contactInput) elements.contactForm.reset();
      elements.callerId.value = phone;
      await loadContacts();
      showToast(`${source.name} saved as a known caller.`);
    } catch (error) {
      showToast(error.message || "Unable to save caller.", "error");
    }
  }

  async function removeContact(phoneNumber) {
    try {
      await requestJson("/api/contacts", {
        method: "DELETE",
        body: JSON.stringify({ phone_number: phoneNumber }),
      });
      await loadContacts();
    } catch (error) {
      showToast(error.message || "Unable to remove caller.", "error");
    }
  }

  async function importDeviceContacts() {
    if (!navigator.contacts || typeof navigator.contacts.select !== "function") {
      showToast("This browser does not support the device contact picker. Add the caller manually.", "error");
      return;
    }
    try {
      const contacts = await navigator.contacts.select(["name", "tel"], { multiple: true });
      for (const contact of contacts) {
        const phone = Array.isArray(contact.tel) ? contact.tel.find(Boolean) : "";
        if (contact.name?.[0] && phone) {
          await addContact(null, { name: contact.name[0], tel: [phone] });
        }
      }
    } catch (error) {
      if (error.name !== "AbortError") showToast(error.message || "Unable to import device contacts.", "error");
    }
  }

  function showDecision(message) {
    const decision = message.decision || "Review";
    const identity = message.caller_identity || "Unknown caller; identity not verified";
    elements.decisionPanel.hidden = false;
    elements.decisionTitle.textContent = `${decision} · ${identity}`;
    elements.decisionSummary.textContent = message.summary || "The call is being screened.";
    elements.decisionReason.textContent = message.decision_reason || "The agent is not certain yet.";
    elements.riskChip.dataset.risk = message.risk_level || "Medium";
    elements.riskChip.textContent = `${String(message.risk_level || "Medium").toUpperCase()} RISK`;
    const number = String(message.transfer_number || state.transferNumber || "").replace(/[^\d+]/g, "");
    const hasValidNumber = /^\+?\d{7,20}$/.test(number);
    elements.transferCall.hidden = decision !== "Transfer" || !hasValidNumber;
    elements.transferHint.hidden = decision !== "Transfer" || hasValidNumber;
    if (hasValidNumber) elements.transferCall.href = `tel:${number}`;
  }

  function createRecognition() {
    if (!SpeechRecognition) return null;
    const recognition = new SpeechRecognition();
    recognition.lang = navigator.language || "en-US";
    recognition.continuous = true;
    recognition.interimResults = true;
    recognition.maxAlternatives = 1;

    recognition.onstart = () => setListening(true, "Listening for caller speech");
    recognition.onresult = (event) => {
      let interimText = "";
      for (let index = event.resultIndex; index < event.results.length; index += 1) {
        const result = event.results[index];
        const phrase = result[0].transcript.trim();
        if (!phrase) continue;
        if (result.isFinal) {
          appendMessage("caller", phrase);
          sendSocketMessage({ type: "transcript", text: phrase });
        } else {
          interimText = phrase;
        }
      }
      if (interimText) setListening(true, `Hearing: “${interimText.slice(0, 72)}”`);
    };
    recognition.onerror = (event) => {
      if (event.error === "no-speech") return;
      const messages = {
        "not-allowed": "Microphone permission was denied. Allow microphone access and try again.",
        "service-not-allowed": "Speech recognition is unavailable in this browser.",
        network: "Speech recognition needs an internet connection.",
      };
      const message = messages[event.error] || `Speech recognition error: ${event.error}`;
      setListening(false, message);
      showToast(message, "error");
    };
    recognition.onend = () => {
      if (state.callActive && !state.ending) {
        window.setTimeout(() => {
          if (state.callActive && !state.ending) {
            try { recognition.start(); } catch { /* A restart can race the browser's stop event. */ }
          }
        }, 250);
      } else {
        setListening(false, state.ending ? "Call ended" : "Microphone is idle");
      }
    };
    return recognition;
  }

  function socketUrl() {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}/ws/call`;
  }

  function sendSocketMessage(message) {
    if (!state.socket || state.socket.readyState !== WebSocket.OPEN) return false;
    state.socket.send(JSON.stringify(message));
    return true;
  }

  function handleSocketMessage(event) {
    let message;
    try {
      message = JSON.parse(event.data);
    } catch {
      showToast("The server sent an unreadable message.", "error");
      return;
    }
    if (message.type === "ready") {
      state.callId = message.call_id;
      sendSocketMessage({ type: "start", caller_id: elements.callerId.value.trim() });
      return;
    }
    if (message.type === "started") {
      state.startedAt = Date.now();
      state.callActive = true;
      state.ending = false;
      elements.startCall.disabled = true;
      elements.endCall.disabled = false;
      elements.callerId.disabled = true;
      setConnection("ON CALL", "connected");
      state.durationTimer = window.setInterval(updateDuration, 1000);
      if (state.recognition) {
        try { state.recognition.start(); } catch (error) { showToast(error.message, "error"); }
      }
      return;
    }
    if (message.type === "response") {
      state.latestClassification = message.classification || "General Inquiry";
      state.latestSummary = message.summary || "The caller shared a message.";
      showDecision(message);
      appendMessage("agent", message.response, state.latestClassification);
      speak(message.response);
      return;
    }
    if (message.type === "call_saved") {
      finishCallUi();
      showToast("Call saved to the registry.");
      loadLogs();
      return;
    }
    if (message.type === "error") showToast(message.message || "The call could not be processed.", "error");
  }

  function finishCallUi() {
    state.callActive = false;
    state.ending = false;
    if (state.durationTimer) window.clearInterval(state.durationTimer);
    state.durationTimer = null;
    if (state.recognition) {
      state.recognition.onend = null;
      try { state.recognition.stop(); } catch { /* Recognition may already have ended. */ }
      state.recognition = null;
    }
    if ("speechSynthesis" in window) window.speechSynthesis.cancel();
    elements.startCall.disabled = false;
    elements.endCall.disabled = true;
    elements.callerId.disabled = false;
    elements.callDuration.textContent = "00:00";
    elements.decisionPanel.hidden = true;
    setConnection("READY");
    setListening(false, "Microphone is idle");
    if (state.socket && state.socket.readyState < WebSocket.CLOSING) state.socket.close();
    state.socket = null;
  }

  function handleSocketClose() {
    if (state.callActive && !state.ending) {
      finishCallUi();
      showToast("The call connection closed.", "error");
      loadLogs();
    } else if (!state.ending) {
      setConnection("READY");
    }
  }

  function startCall() {
    const caller = elements.callerId.value.trim();
    if (!caller || caller.length > 80) {
      showToast("Enter a caller ID between 1 and 80 characters.", "error");
      elements.callerId.focus();
      return;
    }
    if (!window.WebSocket) {
      showToast("WebSockets are unavailable in this browser.", "error");
      return;
    }
    state.messages = [];
    state.callId = null;
    state.latestClassification = "General Inquiry";
    state.latestSummary = "The call ended without a message.";
    elements.messageFeed.replaceChildren(elements.conversationEmpty);
    elements.conversationEmpty.hidden = false;
    elements.callDuration.textContent = "00:00";
    if (!SpeechRecognition) {
      showToast("Use Chrome or another browser with Web Speech recognition support.", "error");
      setListening(false, "Speech recognition is not supported");
    }
    setConnection("CONNECTING", "busy");
    elements.startCall.disabled = true;
    try {
      state.socket = new WebSocket(socketUrl());
    } catch (error) {
      elements.startCall.disabled = false;
      setConnection("READY");
      showToast(error.message || "Unable to open the call connection.", "error");
      return;
    }
    state.socket.addEventListener("message", handleSocketMessage);
    state.socket.addEventListener("close", handleSocketClose);
    state.socket.addEventListener("error", () => showToast("Call connection failed. Check the server and try again.", "error"));
    state.socket.addEventListener("open", () => {
      state.recognition = createRecognition();
      if (!state.recognition) setListening(false, "Type-to-speech is unavailable in this browser");
    }, { once: true });
    state.socket.addEventListener("close", () => {
      if (!state.callActive) elements.startCall.disabled = false;
    }, { once: true });
  }

  function endCall() {
    if (!state.callActive || state.ending) return;
    state.ending = true;
    if (state.recognition) {
      try { state.recognition.stop(); } catch { /* Recognition may already have ended. */ }
    }
    setListening(false, "Saving call summary…");
    setConnection("SAVING", "busy");
    sendSocketMessage({ type: "end" });
    window.setTimeout(() => {
      if (state.ending) {
        finishCallUi();
        showToast("Call connection ended before confirmation; refreshing history.", "error");
        loadLogs();
      }
    }, 5000);
  }

  async function initialize() {
    if (!SpeechRecognition) {
      document.getElementById("browserNote").textContent = "This browser does not support Web Speech recognition. Try current Chrome over HTTPS.";
    }
    elements.callForm.addEventListener("submit", (event) => event.preventDefault());
    elements.agentToggle.addEventListener("click", toggleAgent);
    elements.startCall.addEventListener("click", startCall);
    elements.endCall.addEventListener("click", endCall);
    elements.refreshLogs.addEventListener("click", loadLogs);
    elements.settingsForm.addEventListener("submit", saveSettings);
    elements.contactForm.addEventListener("submit", addContact);
    elements.contactList.addEventListener("click", (event) => {
      const button = event.target.closest("button[data-phone]");
      if (button) removeContact(button.dataset.phone);
    });
    elements.importDeviceContacts.addEventListener("click", importDeviceContacts);
    elements.logoutButton.addEventListener("click", async () => {
      try {
        await requestJson("/api/logout", { method: "POST", body: "{}" });
        window.location.reload();
      } catch (error) {
        showToast(error.message || "Unable to sign out.", "error");
      }
    });
    elements.callerId.addEventListener("input", updateCallerMatch);
    elements.callerId.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        startCall();
      }
    });
    await Promise.all([loadLogs(), loadSettings(), loadAgentStatus(), loadContacts()]);
  }

  document.addEventListener("DOMContentLoaded", initialize, { once: true });
})();