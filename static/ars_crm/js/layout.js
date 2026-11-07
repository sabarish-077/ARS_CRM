(() => {
  const sidebar = document.getElementById("appSidebar");
  const openButton = document.querySelector("[data-sidebar-open]");
  const closeButton = document.querySelector("[data-sidebar-close]");
  if (!sidebar || !openButton || !closeButton) return;

  const setOpen = (open) => {
    sidebar.classList.toggle("is-open", open);
    closeButton.hidden = !open;
    openButton.setAttribute("aria-expanded", String(open));
    document.body.classList.toggle("navigation-open", open);
    if (open) sidebar.querySelector("a")?.focus();
    else openButton.focus();
  };

  openButton.addEventListener("click", () => setOpen(true));
  closeButton.addEventListener("click", () => setOpen(false));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && sidebar.classList.contains("is-open")) setOpen(false);
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 991 && sidebar.classList.contains("is-open")) setOpen(false);
  });
})();
