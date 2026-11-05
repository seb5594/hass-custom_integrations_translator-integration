/* A service call has a user context but no browser address. Only the visible admin tab opens. */
async function listen() {
  await customElements.whenDefined("home-assistant");
  const root = document.querySelector("home-assistant");
  if (!root) return;
  while ((!root.hass?.connection || !root.hass?.user) && root.isConnected) {
    await new Promise(resolve => setTimeout(resolve, 500));
  }
  if (!root.hass?.user?.is_admin) return;
  await root.hass.connection.subscribeEvents(async event => {
    if (document.visibilityState !== "visible" || event.data.user_id !== root.hass.user.id ||
        document.querySelector("dialog[data-cit]")) return;
    await import("./workspace.js?v=2026.11.05.8");
    const dialog = document.createElement("dialog");
    dialog.dataset.cit = "";
    dialog.ariaLabel = "Custom Integration Translator";
    dialog.style.cssText = "width:min(56rem,94vw);max-height:88dvh;padding:0;border:0;border-radius:var(--ha-card-border-radius,16px);background:var(--primary-background-color);color:var(--primary-text-color)";
    const panel = document.createElement("cit-workspace");
    panel.popup = true;
    panel.hass = root.hass;
    dialog.append(panel);
    dialog.addEventListener("close", () => dialog.remove(), {once:true});
    dialog.addEventListener("cit-close", () => dialog.close());
    document.body.append(dialog);
    dialog.showModal();
  }, "custom_integration_translator_open");
}
listen();
