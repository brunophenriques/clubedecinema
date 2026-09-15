/* Shared interface behavior. Page scripts retain their API and auth logic. */
document.addEventListener("DOMContentLoaded", () => {
  const chat = document.getElementById("chatPanel");
  if (chat) {
    const syncChatVisibility = () => {
      const open = chat.classList.contains("chat-panel--open");
      chat.inert = !open;
      chat.setAttribute("aria-hidden", String(!open));
    };
    syncChatVisibility();
    new MutationObserver(syncChatVisibility).observe(chat, { attributes: true, attributeFilter: ["class"] });
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && chat.classList.contains("chat-panel--open")) {
        document.getElementById("chatClose")?.click();
        document.getElementById("btnChat")?.focus();
      }
    });
  }
  const dialog = document.getElementById("submissionDialog");
  document.getElementById("openSubmission")?.addEventListener("click", () => {
    dialog?.showModal();
    document.getElementById("subTitle")?.focus();
  });
  document.getElementById("closeSubmission")?.addEventListener("click", () => dialog?.close());
  dialog?.addEventListener("click", event => {
    if (event.target !== dialog) return;
    const box = dialog.getBoundingClientRect();
    if (event.clientX < box.left || event.clientX > box.right || event.clientY < box.top || event.clientY > box.bottom) dialog.close();
  });
});
