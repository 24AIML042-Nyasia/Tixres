/**
 * auth.js – Client-side auth helpers shared across all Tixres pages.
 *
 * Usage:
 *   import { requireAuth, getToken, getRole, renderUserPill, logout } from "./auth.js";
 *   requireAuth("current-page.html");  // redirects to login if no token
 */

/** Redirect to login if no token stored. currentPage is appended as ?next= */
export function requireAuth(currentPage = "") {
  const token = sessionStorage.getItem("sysmon_token");
  if (!token) {
    const next = currentPage ? `?next=${encodeURIComponent(currentPage)}` : "";
    location.href = `login.html${next}`;
  }
  return token;
}

export function getToken()    { return sessionStorage.getItem("sysmon_token")    || ""; }
export function getUsername() { return sessionStorage.getItem("sysmon_username") || "user"; }
export function getRole()     { return sessionStorage.getItem("sysmon_role")     || "user"; }

export function logout() {
  sessionStorage.clear();
  location.href = "login.html";
}

/**
 * Inject a user pill into the element identified by `containerId`.
 * If the container doesn't exist, does nothing.
 */
export function renderUserPill(containerId = "user-pill-container") {
  const el = document.getElementById(containerId);
  if (!el) return;
  const username = getUsername();
  const role     = getRole();
  const initial  = username[0].toUpperCase();

  el.innerHTML = `
    <div class="user-pill" title="Click to sign out" onclick="import('./js/auth.js').then(m=>m.logout())"
         style="display:flex;align-items:center;gap:7px;background:#21262d;border:1px solid #30363d;
                border-radius:20px;padding:4px 12px 4px 4px;font-size:12px;color:#8b949e;
                cursor:pointer;transition:border-color .15s;">
      <div style="width:22px;height:22px;border-radius:50%;background:linear-gradient(135deg,#1f6feb,#388bfd);
                  display:flex;align-items:center;justify-content:center;font-size:10px;color:#fff;font-weight:700;">
        ${initial}
      </div>
      <span>${escHtml(username)}</span>
      <span style="font-size:9px;font-weight:600;text-transform:uppercase;padding:1px 5px;border-radius:3px;
                   background:${role === 'admin' ? 'rgba(210,153,34,.2)' : 'rgba(31,111,235,.15)'};
                   color:${role === 'admin' ? '#d29922' : '#58a6ff'};">
        ${role}
      </span>
    </div>
  `;
}

function escHtml(str) {
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}
