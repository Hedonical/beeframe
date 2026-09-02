(() => {
  const CHANNEL = "shinylive_google";
  const parentOrigin = window.location.origin;
  Shiny.addCustomMessageHandler("google_request", (message) => {
    if (!message || typeof message.requestId !== "string" || !message.request) return;
    window.parent.postMessage({ channel: CHANNEL, type: "request", ...message }, parentOrigin);
  });
  window.addEventListener("message", (event) => {
    if (event.origin !== parentOrigin || event.source !== window.parent) return;
    const message = event.data;
    if (!message || message.channel !== CHANNEL || message.type !== "result" || typeof message.requestId !== "string") return;
    Shiny.setInputValue("google_result", JSON.stringify(message), { priority: "event" });
  });
})();
