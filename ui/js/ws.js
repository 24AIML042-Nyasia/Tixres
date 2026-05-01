export function createWsClient(url, { onMessage, onOpen, onClose, onError } = {}) {
  let ws = null;
  let closedByUser = false;
  let reconnectMs = 1500;

  function connect() {
    closedByUser = false;
    ws = new WebSocket(url);

    ws.addEventListener("open", () => {
      reconnectMs = 1500;
      onOpen?.();
    });

    ws.addEventListener("message", (ev) => {
      if (typeof ev.data !== "string") return;
      let obj = null;
      try {
        obj = JSON.parse(ev.data);
      } catch {
        return;
      }
      if (!obj || typeof obj !== "object") return;
      onMessage?.(obj);
    });

    ws.addEventListener("close", () => {
      onClose?.();
      if (closedByUser) return;
      const wait = reconnectMs;
      reconnectMs = Math.min(10_000, reconnectMs * 1.5);
      window.setTimeout(connect, wait);
    });

    ws.addEventListener("error", () => {
      onError?.();
      // Browser will emit close afterward.
    });
  }

  function send(obj) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    ws.send(JSON.stringify(obj));
    return true;
  }

  function close() {
    closedByUser = true;
    try {
      ws?.close();
    } catch {
      // ignore
    }
  }

  // Alias used in login page
  const disconnect = close;

  return { connect, send, close, disconnect };
}
