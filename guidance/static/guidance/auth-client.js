const state = {
  base: "",
  token: localStorage.getItem("authToken") || "",
  user: JSON.parse(localStorage.getItem("authUser") || "null"),
};

function normalizeBase(raw) {
  if (!raw || !raw.trim()) return null;
  let url = raw.trim();
  if (!/^https?:\/\//i.test(url)) url = "http://" + url;
  if (url.endsWith("/")) url = url.slice(0, -1);
  try { return new URL(url).origin; } catch { return null; }
}

function saveAuth(token, user) {
  state.token = token;
  state.user = user;
  localStorage.setItem("authToken", token || "");
  localStorage.setItem("authUser", user ? JSON.stringify(user) : "");
  renderUserChip();
}

function renderUserChip() {
  const chip = document.getElementById("userChip");
  if (state.user && state.token) {
    chip.textContent = `${state.user.name || state.user.email} (${state.user.role})`;
  } else {
    chip.textContent = "Not signed in";
  }
}

function switchTab(tab) {
  document.querySelectorAll(".nav-tab").forEach(t => t.classList.remove("active"));
  document.querySelector(`.nav-tab[data-tab='${tab}']`).classList.add("active");
  document.querySelectorAll(".card").forEach(c => c.classList.add("hidden"));
  document.getElementById(tab + "Card").classList.remove("hidden");
  if (tab === "admin") {
    if (!state.user || state.user.role !== "admin") {
      document.getElementById("adminStatus").textContent = "Admin only. Login as admin first.";
      return;
    }
    refreshUsers();
  }
}

async function login() {
  const base = normalizeBase(document.getElementById("baseUrl")?.value || window.location.origin);
  const email = document.getElementById("loginEmail").value.trim();
  const password = document.getElementById("loginPassword").value;
  const status = document.getElementById("loginStatus");
  if (!base || !email || !password) { status.textContent = "Base URL, email, password required."; status.style.color="#e8445a"; return; }
  status.textContent = "Signing in…"; status.style.color = "#6b7280";
  try {
    const res = await fetch(`${base}/api/dev-auth/login/`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({email, password})
    });
    const data = await res.json();
    if (!res.ok) { status.textContent = data.error || `Error ${res.status}`; status.style.color="#e8445a"; return; }
    saveAuth(data.token, data.user);
    status.textContent = "Signed in.";
    status.style.color = "#2a8a7e";
  } catch (e) {
    status.textContent = `Error: ${e}`;
    status.style.color = "#e8445a";
  }
}

async function register() {
  const base = normalizeBase(document.getElementById("baseUrl")?.value || window.location.origin);
  const email = document.getElementById("regEmail").value.trim();
  const name = document.getElementById("regName").value.trim();
  const password = document.getElementById("regPassword").value;
  const status = document.getElementById("regStatus");
  if (!base || !email || !password) { status.textContent = "Base URL, email, password required."; status.style.color="#e8445a"; return; }
  status.textContent = "Registering…"; status.style.color = "#6b7280";
  try {
    const res = await fetch(`${base}/api/dev-auth/register/`, {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({email, password, name, role:"end_user"})
    });
    const data = await res.json();
    if (!res.ok) { status.textContent = data.error || `Error ${res.status}`; status.style.color="#e8445a"; return; }
    saveAuth(data.token, data.user);
    status.textContent = "Account created and signed in.";
    status.style.color = "#2a8a7e";
  } catch (e) {
    status.textContent = `Error: ${e}`;
    status.style.color = "#e8445a";
  }
}

function logout() {
  saveAuth("", null);
  document.getElementById("loginStatus").textContent = "";
  document.getElementById("regStatus").textContent = "";
  document.getElementById("adminStatus").textContent = "";
}

function copyToken() {
  if (!state.token) return;
  navigator.clipboard?.writeText(state.token);
}

function authHeaders() {
  return state.token ? { Authorization: `Bearer ${state.token}` } : {};
}

async function refreshUsers() {
  if (!state.user || state.user.role !== "admin") {
    document.getElementById("adminStatus").textContent = "Admin only.";
    document.getElementById("adminStatus").style.color = "#e8445a";
    return;
  }
  const base = normalizeBase(document.getElementById("baseUrl")?.value || window.location.origin);
  if (!base) return;
  const status = document.getElementById("adminStatus");
  status.textContent = "Loading users…"; status.style.color = "#6b7280";
  try {
    const res = await fetch(`${base}/api/auth/users/?limit=200`, { headers: { ...authHeaders() }});
    const data = await res.json();
    if (!res.ok) { status.textContent = data.error || `Error ${res.status}`; status.style.color="#e8445a"; return; }
    renderUserTable(data.items || []);
    status.textContent = `Loaded ${data.items?.length || 0} users.`;
    status.style.color = "#2a8a7e";
  } catch (e) {
    status.textContent = `Error: ${e}`;
    status.style.color = "#e8445a";
  }
}

function renderUserTable(items) {
  const wrap = document.getElementById("userTable");
  if (!items.length) { wrap.innerHTML = '<div class="hint">No users yet.</div>'; return; }
  const header = `<div class="row header"><div>User ID</div><div>Email</div><div>Role</div><div>Skills</div><div>Status</div></div>`;
  const rows = items.map(u => `
    <div class="row">
      <div>${u.user_id}</div>
      <div>${u.email}</div>
      <div>${u.role}</div>
      <div>${(u.skill_set || []).join(", ")}</div>
      <div>${u.is_active ? "active" : "inactive"}</div>
    </div>`).join("");
  wrap.innerHTML = header + rows;
}

async function promoteResolver() {
  const base = normalizeBase(document.getElementById("baseUrl")?.value || window.location.origin);
  const target = document.getElementById("promoteUserId").value.trim();
  const status = document.getElementById("adminStatus");
  if (!base || !target) { status.textContent = "User ID/email required."; status.style.color="#e8445a"; return; }
  status.textContent = "Promoting…"; status.style.color="#6b7280";
  try {
    const res = await fetch(`${base}/api/auth/users/${encodeURIComponent(target)}/`, {
      method: "PATCH",
      headers: {"Content-Type":"application/json", ...authHeaders()},
      body: JSON.stringify({role:"resolver"})
    });
    const data = await res.json();
    if (!res.ok) { status.textContent = data.error || `Error ${res.status}`; status.style.color="#e8445a"; return; }
    status.textContent = `Updated role for ${data.user_id || target}`;
    status.style.color = "#2a8a7e";
    refreshUsers();
  } catch (e) {
    status.textContent = `Error: ${e}`;
    status.style.color = "#e8445a";
  }
}

async function addSkill(remove=false) {
  const base = normalizeBase(document.getElementById("baseUrl")?.value || window.location.origin);
  const target = document.getElementById("promoteUserId").value.trim();
  const skill = document.getElementById("skillName").value.trim();
  const status = document.getElementById("adminStatus");
  if (!base || !target || !skill) { status.textContent = "User ID and skill required."; status.style.color="#e8445a"; return; }
  const path = remove ? "remove" : "add";
  status.textContent = `${remove ? "Removing" : "Adding"} skill…`; status.style.color="#6b7280";
  try {
    const res = await fetch(`${base}/api/auth/users/${encodeURIComponent(target)}/skills/${path}/`, {
      method: "POST",
      headers: {"Content-Type":"application/json", ...authHeaders()},
      body: JSON.stringify({skill})
    });
    const data = await res.json();
    if (!res.ok) { status.textContent = data.error || `Error ${res.status}`; status.style.color="#e8445a"; return; }
    status.textContent = `Skill set: ${(data.skill_set || []).join(", ")}`;
    status.style.color = "#2a8a7e";
    refreshUsers();
  } catch (e) {
    status.textContent = `Error: ${e}`;
    status.style.color = "#e8445a";
  }
}

function removeSkill() { addSkill(true); }

// init
(function init() {
  const baseInput = document.getElementById("baseUrl");
  if (baseInput) baseInput.value = state.base || baseInput.placeholder;
  renderUserChip();
})();
