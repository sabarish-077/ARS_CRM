(() => {
  const card = document.getElementById("authCard");
  const title = document.getElementById("welcomeTitle");
  const text = document.getElementById("welcomeText");
  const loginPanel = document.querySelector(".login-panel");
  const requestPanel = document.querySelector(".signup-panel");
  if (!card) return;
  const copy = {
    login: ["Welcome<br><em>back.</em>", "Good to see you again.<br>Let's get today's work in motion."],
    request: ["Join the<br><em>team.</em>", "Request access to the staff workspace.<br>The owner will review your details."]
  };
  document.querySelectorAll("[data-switch]").forEach((button) => button.addEventListener("click", () => {
    const requesting = button.dataset.switch === "signup";
    card.classList.toggle("signup", requesting);
    loginPanel.toggleAttribute("inert", requesting);
    requestPanel.toggleAttribute("inert", !requesting);
    title.innerHTML = requesting ? copy.request[0] : copy.login[0];
    text.innerHTML = requesting ? copy.request[1] : copy.login[1];
    (requesting ? requestPanel : loginPanel).querySelector("input,select")?.focus();
  }));
  const toggle = document.querySelector(".password-toggle");
  const password = document.getElementById("id_password");
  toggle?.addEventListener("click", () => {
    const visible = password.type === "password";
    password.type = visible ? "text" : "password";
    toggle.setAttribute("aria-pressed", String(visible));
    toggle.setAttribute("aria-label", visible ? "Hide password" : "Show password");
    toggle.innerHTML = `<i class="bi bi-eye${visible ? '-slash' : ''}"></i>`;
  });
  if (document.querySelector(".signup-panel .field-error")) {
    card.classList.add("signup");
    loginPanel.toggleAttribute("inert", true);
    requestPanel.toggleAttribute("inert", false);
    title.innerHTML = copy.request[0];
    text.innerHTML = copy.request[1];
  }
})();
