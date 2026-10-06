(() => {
  "use strict";

  // already logged in -> skip straight to the app
  if (localStorage.getItem("mediassist_token")) {
    window.location.href = "/";
    return;
  }

  const tabs = document.querySelectorAll(".auth-tab");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  const loginError = document.getElementById("loginError");
  const registerError = document.getElementById("registerError");

  function showTab(name) {
    tabs.forEach(t => t.classList.toggle("active", t.dataset.tab === name));
    loginForm.classList.toggle("hidden", name !== "login");
    registerForm.classList.toggle("hidden", name !== "register");
    loginError.classList.add("hidden");
    registerError.classList.add("hidden");
  }

  tabs.forEach(t => t.addEventListener("click", () => showTab(t.dataset.tab)));

  function setError(el, msg) {
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  async function postJSON(path, body) {
    const res = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      throw new Error(data.detail || `Request failed (${res.status})`);
    }
    return data;
  }

  function onLoggedIn(data) {
    localStorage.setItem("mediassist_token", data.token);
    localStorage.setItem("mediassist_username", data.username);
    localStorage.setItem("mediassist_display_name", data.display_name || data.username);
    // a token belongs to a fresh login - any previously stored chat
    // session id belonged to a possibly different user/server state.
    localStorage.removeItem("mediassist_session_id");
    window.location.href = "/";
  }

  loginForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    loginError.classList.add("hidden");
    const username = document.getElementById("loginUsername").value.trim();
    const password = document.getElementById("loginPassword").value;
    const btn = loginForm.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const data = await postJSON("/api/auth/login", { username, password });
      onLoggedIn(data);
    } catch (err) {
      setError(loginError, err.message);
      btn.disabled = false;
    }
  });

  registerForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    registerError.classList.add("hidden");
    const username = document.getElementById("regUsername").value.trim();
    const password = document.getElementById("regPassword").value;
    const display_name = document.getElementById("regDisplayName").value.trim();
    const btn = registerForm.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const data = await postJSON("/api/auth/register", { username, password, display_name });
      onLoggedIn(data);
    } catch (err) {
      setError(registerError, err.message);
      btn.disabled = false;
    }
  });
})();
