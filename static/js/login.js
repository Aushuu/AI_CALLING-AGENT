(() => {
  "use strict";

  const form = document.getElementById("loginForm");
  const password = document.getElementById("loginPassword");
  const error = document.getElementById("loginError");
  const submit = form.querySelector('button[type="submit"]');

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    submit.disabled = true;
    try {
      const response = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ password: password.value }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.error || "Unable to sign in.");
      window.location.assign("/");
    } catch (exception) {
      error.textContent = exception.message || "Unable to sign in.";
      error.hidden = false;
      password.select();
    } finally {
      submit.disabled = false;
    }
  });
})();