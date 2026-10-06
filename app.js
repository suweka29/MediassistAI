(() => {
  "use strict";

  const API = ""; // same-origin; set to e.g. "http://localhost:8000" if serving frontend separately

  // -------------------------------------------------------------- auth gate
  let authToken = localStorage.getItem("mediassist_token");
  if (!authToken) {
    window.location.href = "/login";
    return;
  }

  const els = {
    messages: document.getElementById("messages"),
    typing: document.getElementById("typing"),
    form: document.getElementById("chatForm"),
    input: document.getElementById("chatInput"),
    resetBtn: document.getElementById("resetBtn"),
    logoutBtn: document.getElementById("logoutBtn"),
    detailsBtn: document.getElementById("detailsBtn"),
    drawer: document.getElementById("detailsDrawer"),
    applyDetailsBtn: document.getElementById("applyDetailsBtn"),
    ageInput: document.getElementById("ageInput"),
    genderInput: document.getElementById("genderInput"),
    durationInput: document.getElementById("durationInput"),
    severityInput: document.getElementById("severityInput"),
    severityVal: document.getElementById("severityVal"),
    modelBadge: document.getElementById("modelBadge"),
    userBadge: document.getElementById("userBadge"),
  };

  let sessionId = localStorage.getItem("mediassist_session_id") || null;

  function goToLogin() {
    localStorage.removeItem("mediassist_token");
    localStorage.removeItem("mediassist_username");
    localStorage.removeItem("mediassist_display_name");
    localStorage.removeItem("mediassist_session_id");
    window.location.href = "/login";
  }

  // ------------------------------------------------------------- rendering
  function scrollToBottom() {
    els.messages.scrollTop = els.messages.scrollHeight;
  }

  function assistantAvatar() {
    const av = document.createElement("div");
    av.className = "msg-avatar";
    av.innerHTML = '<svg viewBox="0 0 24 24" width="16" height="16" fill="none" ' +
      'stroke="currentColor" stroke-width="2.2"><path d="M12 2v6M12 16v6M4.9 4.9l4.2 ' +
      '4.2M14.9 14.9l4.2 4.2M2 12h6M16 12h6M4.9 19.1l4.2-4.2M14.9 9.1l4.2-4.2"/></svg>';
    return av;
  }

  function addUserBubble(text) {
    const wrap = document.createElement("div");
    wrap.className = "msg msg-user";
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    els.messages.appendChild(wrap);
    scrollToBottom();
  }

  function addPlainAssistantBubble(text) {
    const wrap = document.createElement("div");
    wrap.className = "msg msg-assistant";
    wrap.appendChild(assistantAvatar());
    const bubble = document.createElement("div");
    bubble.className = "bubble";
    bubble.textContent = text;
    wrap.appendChild(bubble);
    els.messages.appendChild(wrap);
    scrollToBottom();
  }

  function confDotClass(level) {
    if (level === "high") return "conf-high";
    if (level === "medium") return "conf-medium";
    return "conf-low";
  }

  function addAssistantCard(data) {
    const wrap = document.createElement("div");
    wrap.className = "msg msg-assistant";
    wrap.appendChild(assistantAvatar());

    const card = document.createElement("div");
    card.className = "card";
    if (data.type === "emergency") {
      const level = data.safety && data.safety.level;
      card.classList.add(level === "emergency" ? "emergency" : "urgent");
    }

    const title = document.createElement("div");
    title.className = "card-title";
    title.textContent = data.type === "emergency"
      ? `⚠ ${data.safety ? data.safety.rule : "Urgent safety notice"}`
      : data.type === "clarify" ? "Need more information"
      : "Triage assessment";
    card.appendChild(title);

    // main message text (question / narrative), minus the condition list
    // which we render separately below for the "prediction" type.
    if (data.type === "prediction" && data.top_conditions && data.top_conditions.length) {
      const list = document.createElement("div");
      list.className = "condition-list";
      const maxP = Math.max(...data.top_conditions.map(c => c.probability));
      data.top_conditions.forEach(c => {
        const row = document.createElement("div");
        row.className = "condition-row";
        const name = document.createElement("div");
        name.className = "condition-name";
        name.textContent = c.condition;
        const track = document.createElement("div");
        track.className = "condition-bar-track";
        const fill = document.createElement("div");
        fill.className = "condition-bar-fill";
        const pct = Math.round(c.probability * 1000) / 10;
        fill.style.width = `${Math.max(3, (c.probability / (maxP || 1)) * 100)}%`;
        track.appendChild(fill);
        const pctLabel = document.createElement("div");
        pctLabel.className = "condition-pct";
        pctLabel.textContent = `${pct}%`;
        row.appendChild(name);
        row.appendChild(track);
        row.appendChild(pctLabel);
        list.appendChild(row);
      });
      card.appendChild(list);

      const confRow = document.createElement("div");
      confRow.className = "confidence-row";
      const dot = document.createElement("span");
      dot.className = `conf-dot ${confDotClass(data.confidence)}`;
      confRow.appendChild(dot);
      confRow.appendChild(document.createTextNode(
        `confidence: ${data.confidence} (${Math.round((data.confidence_score || 0) * 1000) / 10}%)`));
      card.appendChild(confRow);
    }

    if (data.symptoms && data.symptoms.length) {
      const chipRow = document.createElement("div");
      chipRow.className = "chip-row";
      data.symptoms.forEach(s => {
        const chip = document.createElement("span");
        chip.className = "chip";
        chip.textContent = s.replace(/_/g, " ");
        chipRow.appendChild(chip);
      });
      card.appendChild(chipRow);
    }

    if (data.type === "emergency") {
      const body = document.createElement("div");
      body.className = "card-body";
      body.textContent = data.safety ? data.safety.guidance : data.message;
      card.appendChild(body);
    } else if (data.followup_question) {
      const body = document.createElement("div");
      body.className = "card-body";
      body.textContent = data.followup_question.question;
      card.appendChild(body);

      const qr = document.createElement("div");
      qr.className = "quick-replies";
      ["Yes", "No"].forEach(label => {
        const btn = document.createElement("button");
        btn.type = "button";
        btn.textContent = label;
        btn.addEventListener("click", () => sendMessage(label));
        qr.appendChild(btn);
      });
      card.appendChild(qr);
    } else if (data.type === "clarify") {
      const body = document.createElement("div");
      body.className = "card-body";
      body.textContent = data.message;
      card.appendChild(body);
    }

    if (data.care_advice) {
      const advice = data.care_advice;
      const box = document.createElement("div");
      box.className = "care-advice";

      const heading = document.createElement("div");
      heading.className = "care-advice-title";
      heading.textContent = `Precautions & self-care — ${advice.condition}`;
      box.appendChild(heading);

      const sections = [
        ["Precautions", advice.precautions],
        ["What you can do now / first aid", advice.home_care],
        ["See a doctor promptly if", advice.seek_care_if],
      ];
      sections.forEach(([label, items]) => {
        if (!items || !items.length) return;
        const sec = document.createElement("div");
        sec.className = "care-advice-section";
        const secTitle = document.createElement("div");
        secTitle.className = "care-advice-section-title";
        secTitle.textContent = label;
        sec.appendChild(secTitle);
        const ul = document.createElement("ul");
        items.forEach(item => {
          const li = document.createElement("li");
          li.textContent = item;
          ul.appendChild(li);
        });
        sec.appendChild(ul);
        box.appendChild(sec);
      });

      card.appendChild(box);
    }

    if (data.disclaimer) {
      const disc = document.createElement("div");
      disc.className = "disclaimer-line";
      disc.textContent = data.disclaimer;
      card.appendChild(disc);
    }

    wrap.appendChild(card);
    els.messages.appendChild(wrap);
    scrollToBottom();
  }

  function setTyping(on) {
    els.typing.classList.toggle("hidden", !on);
    if (on) scrollToBottom();
  }

  // ------------------------------------------------------------------ API
  function authHeaders(extra) {
    return Object.assign({ "Authorization": `Bearer ${authToken}` }, extra || {});
  }

  async function apiPost(path, body) {
    const res = await fetch(API + path, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body || {}),
    });
    if (res.status === 401) { goToLogin(); throw new Error("401: not authenticated"); }
    if (!res.ok) {
      const detail = await res.text();
      throw new Error(`${res.status}: ${detail}`);
    }
    return res.json();
  }

  async function apiGet(path) {
    const res = await fetch(API + path, { headers: authHeaders() });
    if (res.status === 401) { goToLogin(); throw new Error("401: not authenticated"); }
    return res;
  }

  function currentDetails() {
    return {
      age: parseInt(els.ageInput.value, 10) || 35,
      gender: els.genderInput.value,
      duration_days: parseInt(els.durationInput.value, 10) || 3,
      severity: parseInt(els.severityInput.value, 10) || 5,
    };
  }

  async function ensureSession() {
    if (sessionId) {
      // stored id might belong to a previous server run whose DB was
      // reset - verify it still exists before trusting it.
      try {
        const res = await apiGet(`/api/session/${sessionId}/history`);
        if (res.ok) return;
      } catch (err) {
        // network/auth error - fall through and let the caller's own
        // error handling deal with it via the /api/session call below
      }
      localStorage.removeItem("mediassist_session_id");
      sessionId = null;
    }
    const data = await apiPost("/api/session", currentDetails());
    sessionId = data.session_id;
    localStorage.setItem("mediassist_session_id", sessionId);
    addPlainAssistantBubble(data.message);
  }

  async function sendMessage(text) {
    text = text.trim();
    if (!text) return;
    els.input.value = "";
    addUserBubble(text);
    setTyping(true);
    try {
      await ensureSession();
      let data;
      try {
        data = await apiPost("/api/chat", { session_id: sessionId, message: text });
      } catch (err) {
        // Stale session_id from a previous server run (DB was reset) -
        // transparently start a fresh session and retry once.
        if (err.message.startsWith("404")) {
          localStorage.removeItem("mediassist_session_id");
          sessionId = null;
          await ensureSession();
          data = await apiPost("/api/chat", { session_id: sessionId, message: text });
        } else {
          throw err;
        }
      }
      setTyping(false);
      addAssistantCard(data);
    } catch (err) {
      setTyping(false);
      addPlainAssistantBubble("Sorry, something went wrong reaching the server. " +
        "Please make sure the backend is running. (" + err.message + ")");
      console.error(err);
    }
  }

  async function newSession() {
    localStorage.removeItem("mediassist_session_id");
    sessionId = null;
    els.messages.innerHTML = "";
    try {
      await ensureSession();
    } catch (err) {
      addPlainAssistantBubble("Could not reach the server: " + err.message);
    }
  }

  async function loadModelBadge() {
    try {
      const res = await fetch(API + "/api/health");
      const data = await res.json();
      els.modelBadge.textContent =
        `model: ${data.model_classes} conditions · ${Math.round(data.test_accuracy * 1000) / 10}% test acc.`;
      els.modelBadge.classList.remove("badge-muted");
    } catch (err) {
      els.modelBadge.textContent = "model offline";
    }
  }

  function showUserBadge() {
    const name = localStorage.getItem("mediassist_display_name") ||
      localStorage.getItem("mediassist_username") || "you";
    els.userBadge.textContent = `👤 ${name}`;
    els.userBadge.classList.remove("hidden");
  }

  // ---------------------------------------------------------------- events
  els.form.addEventListener("submit", (e) => {
    e.preventDefault();
    sendMessage(els.input.value);
  });

  els.resetBtn.addEventListener("click", newSession);

  els.logoutBtn.addEventListener("click", async () => {
    try { await apiPost("/api/auth/logout", {}); } catch (err) { /* ignore */ }
    goToLogin();
  });

  els.detailsBtn.addEventListener("click", () => {
    els.drawer.classList.toggle("hidden");
  });

  els.severityInput.addEventListener("input", () => {
    els.severityVal.textContent = els.severityInput.value;
  });

  els.applyDetailsBtn.addEventListener("click", async () => {
    if (!sessionId) { await ensureSession(); return; }
    try {
      await apiPost(`/api/session/${sessionId}/reset`, currentDetails());
      els.messages.innerHTML = "";
      const res = await apiGet(`/api/session/${sessionId}/history`);
      const data = await res.json();
      addPlainAssistantBubble(data.messages[data.messages.length - 1].content);
    } catch (err) {
      addPlainAssistantBubble("Could not apply details: " + err.message);
    }
  });

  // ------------------------------------------------------------------ init
  showUserBadge();
  loadModelBadge();
  ensureSession().catch(err => {
    addPlainAssistantBubble("Could not reach the server: " + err.message +
      "\n\nStart the backend with: uvicorn backend.main:app --reload");
  });
})();
