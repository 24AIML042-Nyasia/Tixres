/**
 * config.js – Central URL configuration for all Tixres frontend pages.
 *
 * This is the ONLY place you need to change host/port settings for the UI.
 * All other JS files import from here.
 */

const _CFG = {
  server: {
    host:    "127.0.0.1",
    wsPort:  8765,
    uiPort:  8000,
  },
  chatbot: {
    host: "127.0.0.1",
    port: 8001,
  },
};

/** WebSocket URL for the main metric server */
export const WS_URL      = `ws://${_CFG.server.host}:${_CFG.server.wsPort}`;

/** Base HTTP URL for the main server (static assets are served here) */
export const SERVER_URL  = `http://${_CFG.server.host}:${_CFG.server.uiPort}`;

/** Base HTTP URL for the chatbot microservice */
export const CHATBOT_URL = `http://${_CFG.chatbot.host}:${_CFG.chatbot.port}`;

/** Chat endpoint */
export const CHAT_ENDPOINT = `${CHATBOT_URL}/chat`;

/** Ingest endpoints */
export const INGEST_ENDPOINT      = `${CHATBOT_URL}/ingest`;
export const INGEST_BULK_ENDPOINT = `${CHATBOT_URL}/ingest/bulk`;

/** Chatbot health endpoint */
export const CHATBOT_HEALTH = `${CHATBOT_URL}/health`;
