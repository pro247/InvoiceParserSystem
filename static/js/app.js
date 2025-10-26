// static/js/app.js
// NOTE: module type; runs in all pages. Detects location and attaches handlers.

const API_BASE = ""; // same origin

// helper: get/set token
export function getToken() {
    return localStorage.getItem("invoice_token");
}
export function setToken(t) {
    localStorage.setItem("invoice_token", t);
    updateNav();
}
export function clearToken() {
    localStorage.removeItem("invoice_token");
    updateNav();
}

// add Authorization header if token exists
export function authHeaders() {
    const token = getToken();
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

function updateNav() {
    const logout = document.getElementById("nav-logout");
    const dashboardLink = document.getElementById("nav-dashboard");
    const signupLink = document.getElementById("nav-signup");
    if (getToken()) {
        logout.style.display = "inline";
        dashboardLink.style.display = "inline";
        signupLink.style.display = "none";
    } else {
        logout.style.display = "none";
        dashboardLink.style.display = "none";
        signupLink.style.display = "inline";
    }
}

window.addEventListener("load", () => {
    updateNav();
    const path = location.pathname;
    if (path === "/" || path.startsWith("/index")) {
        initLogin();
    } else if (path.startsWith("/signup")) {
        initSignup();
    } else if (path.startsWith("/dashboard")) {
        initDashboard();
    }

    const logout = document.getElementById("nav-logout");
    if (logout) logout.onclick = (e) => { e.preventDefault(); clearToken(); location.href = "/"; };
});

// ----------------- Login -----------------
function initLogin() {
    const form = document.getElementById("loginForm");
    if (!form) return;
    form.onsubmit = async (e) => {
        e.preventDefault();
        const ident = document.getElementById("login-username").value.trim();
        const password = document.getElementById("login-password").value;
        const payload = { password };
        // decide if ident is email or username
        if (ident.includes("@")) payload.email = ident;
        else payload.username = ident;

        const res = await fetch("/auth/signin", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        const msg = document.getElementById("loginMessage");
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: "Login failed" }));
            msg.textContent = err.detail || "Login failed";
            msg.style.color = "red";
            return;
        }
        const data = await res.json();
        setToken(data.access_token);
        msg.textContent = "Signed in";
        msg.style.color = "green";
        setTimeout(() => location.href = "/dashboard", 600);
    };
}

// ----------------- Signup -----------------
function initSignup() {
    const form = document.getElementById("signupForm");
    if (!form) return;
    form.onsubmit = async (e) => {
        e.preventDefault();
        const username = document.getElementById("signup-username").value.trim();
        const email = document.getElementById("signup-email").value.trim();
        const password = document.getElementById("signup-password").value;

        const res = await fetch("/auth/signup", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, email, password })
        });

        const msg = document.getElementById("signupMessage");
        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: "Signup failed" }));
            msg.textContent = err.detail || "Signup failed";
            msg.style.color = "red";
            return;
        }
        const data = await res.json();
        // some backends return token in response
        if (data.access_token) setToken(data.access_token);
        msg.textContent = "Account created. Signing in...";
        msg.style.color = "green";
        setTimeout(() => location.href = "/dashboard", 700);
    };
}

// ----------------- Dashboard -----------------
async function initDashboard() {
    // redirect if no token
    if (!getToken()) { location.href = "/"; return; }

    // UI elements
    const fileInput = document.getElementById("invoiceFile");
    const uploadBox = document.getElementById("uploadBox");
    const filename = document.getElementById("filename");
    const uploadBtn = document.getElementById("uploadBtn");
    const exportSelect = document.getElementById("exportSelect");
    const uploadResult = document.getElementById("uploadResult");
    const historyBody = document.getElementById("historyBody");
    const historyEmpty = document.getElementById("historyEmpty");

    // drag/drop
    uploadBox.addEventListener("click", () => fileInput.click());
    uploadBox.addEventListener("dragover", e => { e.preventDefault(); uploadBox.classList.add("drag"); });
    uploadBox.addEventListener("dragleave", e => { e.preventDefault(); uploadBox.classList.remove("drag"); });
    uploadBox.addEventListener("drop", e => {
        e.preventDefault();
        uploadBox.classList.remove("drag");
        if (e.dataTransfer.files.length) {
            fileInput.files = e.dataTransfer.files;
            filename.textContent = fileInput.files[0].name;
        }
    });

    fileInput.addEventListener("change", () => {
        filename.textContent = fileInput.files[0]?.name || "";
    });

    uploadBtn.onclick = async () => {
        if (!fileInput.files.length) { uploadResult.textContent = "Please select a file."; uploadResult.style.color = "red"; return; }
        uploadResult.textContent = "Processing..."; uploadResult.style.color = "black";
        const fd = new FormData();
        fd.append("file", fileInput.files[0]);
        fd.append("export_format", exportSelect.value);

        const res = await fetch("/process_invoice", {
            method: "POST",
            headers: authHeaders(),
            body: fd
        });

        if (!res.ok) {
            const err = await res.json().catch(() => ({ detail: "Upload failed" }));
            uploadResult.textContent = err.detail || JSON.stringify(err);
            uploadResult.style.color = "red";
            await loadHistory();
            return;
        }
        const data = await res.json();
        uploadResult.textContent = "Done. " + (data.export?.file || data.export?.url || JSON.stringify(data));
        uploadResult.style.color = "green";
        await loadHistory();
    };

    // load history
    async function loadHistory() {
        historyBody.innerHTML = "";
        historyEmpty.style.display = "none";
        const res = await fetch("/invoices", { headers: authHeaders() });
        if (!res.ok) { historyEmpty.textContent = "Failed to load history."; historyEmpty.style.display = "block"; return; }
        const data = await res.json();
        const invoices = data.invoices || data;
        if (!invoices || invoices.length === 0) {
            historyEmpty.style.display = "block";
            return;
        }
        historyEmpty.style.display = "none";
        for (const inv of invoices) {
            const tr = document.createElement("tr");
            const exportInfo = inv.export || inv.exports?.slice(-1)?.[0] || {};
            const exportId = exportInfo.id || (exportInfo.path ? null : null);
            const exportPath = exportInfo.path || exportInfo.export_path || exportInfo.path || exportInfo.url || null;
            const exportFormat = exportInfo.format || exportInfo.export_format || "";

            const actionsTd = document.createElement("td");
            // download button (local)
            if (exportFormat && exportFormat !== "gsheets" && exportPath) {
                const a = document.createElement("a");
                a.href = `/download/${exportInfo.id}`;
                a.textContent = "Download";
                a.className = "btn";
                a.onclick = (e) => { /* default link will ask for token at server side */ };
                actionsTd.appendChild(a);
            }
            // google sheets open
            if (exportFormat === "gsheets" && exportPath) {
                const a2 = document.createElement("a");
                a2.href = exportPath;
                a2.target = "_blank";
                a2.textContent = "Open Sheet";
                a2.className = "btn";
                actionsTd.appendChild(a2);
            }

            tr.innerHTML = `
        <td>${inv.invoice_id ?? inv.id ?? ""}</td>
        <td>${inv.invoice_number ?? (inv.data && inv.data.invoice_number) || ""}</td>
        <td>${inv.vendor ?? (inv.data && inv.data.vendor) || ""}</td>
        <td>${inv.date ?? (inv.data && inv.data.date) || ""}</td>
        <td>${exportFormat || (exportInfo.format || "")}</td>
      `;
            tr.appendChild(actionsTd);
            historyBody.appendChild(tr);
        }
    }

    // initial load
    await loadHistory();
}
