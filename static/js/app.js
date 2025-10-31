// static/js/app.js
const TOKEN_KEY = "invoice_token";

// ---------------- Token Utilities ----------------
function getToken() {
    return localStorage.getItem(TOKEN_KEY);
}
function setToken(t) {
    localStorage.setItem(TOKEN_KEY, t);
    updateNav();
}
function clearToken() {
    localStorage.removeItem(TOKEN_KEY);
    updateNav();
}
function authHeaders() {
    const token = getToken();
    return token ? { "Authorization": `Bearer ${token}` } : {};
}

// ---------------- Navigation ----------------
function updateNav() {
    const logout = document.getElementById("nav-logout");
    const dashboardLink = document.getElementById("nav-dashboard");
    const signupLink = document.getElementById("nav-signup");
    if (!logout || !dashboardLink || !signupLink) return;

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

// ---------------- Initialization ----------------
window.addEventListener("load", () => {
    updateNav();

    // Logout button
    const logout = document.getElementById("nav-logout");
    if (logout) {
        logout.onclick = (e) => {
            e.preventDefault();
            clearToken();
            location.href = "/";
        };
    }

    // Initialize pages based on presence of forms
    if (document.getElementById("loginForm")) initLogin();
    if (document.getElementById("signupForm")) initSignup();
    if (document.getElementById("dashboardPage")) initDashboard(); // add id="dashboardPage" in dashboard HTML
});

// ---------------- Login ----------------
function initLogin() {
    const form = document.getElementById("loginForm");
    if (!form) return;

    const loginBtn = document.getElementById("loginBtn");
    const msg = document.getElementById("loginMessage");
    const usernameInput = document.getElementById("login-username");
    const passwordInput = document.getElementById("login-password");
    if (!loginBtn || !msg || !usernameInput || !passwordInput) return;

    loginBtn.onclick = async (e) => {
        e.preventDefault();
        msg.textContent = "";

        const identifier = usernameInput.value.trim();
        const password = passwordInput.value;

        if (!identifier || !password) {
            msg.textContent = "Enter credentials";
            msg.style.color = "red";
            return;
        }

        // Always send JSON that matches FastAPI's model
        const payload = {
            password: password,
            ...(identifier.includes("@") ? { email: identifier } : { username: identifier })
        };

        try {
            const res = await fetch("/auth/signin", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });

            const body = await res.json().catch(() => ({ detail: "Invalid response" }));

            if (!res.ok) {
                msg.textContent = body.detail || JSON.stringify(body);
                msg.style.color = "red";
                return;
            }

            setToken(body.access_token);
            msg.textContent = "Signed in — redirecting...";
            msg.style.color = "green";
            setTimeout(() => location.href = "/dashboard", 600);
        } catch (err) {
            msg.textContent = "Server error";
            msg.style.color = "red";
            console.error(err);
        }
    };
}


// ---------------- Signup ----------------
function initSignup() {
    const form = document.getElementById("signupForm");
    if (!form) return;

    const btn = document.getElementById("signupBtn");
    const msg = document.getElementById("signupMessage");
    const usernameInput = document.getElementById("signup-username");
    const emailInput = document.getElementById("signup-email");
    const passwordInput = document.getElementById("signup-password");
    if (!btn || !msg || !usernameInput || !emailInput || !passwordInput) return;

    btn.onclick = async (e) => {
        e.preventDefault();
        msg.textContent = "";

        const username = usernameInput.value.trim();
        const email = emailInput.value.trim();
        const password = passwordInput.value;

        if (!username || !email || !password) {
            msg.textContent = "Fill all fields";
            msg.style.color = "red";
            return;
        }

        try {
            const res = await fetch("/auth/signup", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, email, password })
            });

            const body = await res.json().catch(() => ({ detail: "Invalid response" }));

            if (!res.ok) {
                msg.textContent = body.detail || JSON.stringify(body);
                msg.style.color = "red";
                return;
            }

            if (body.access_token) setToken(body.access_token);
            msg.textContent = "Account created — redirecting...";
            msg.style.color = "green";
            setTimeout(() => location.href = "/dashboard", 700);
        } catch (err) {
            msg.textContent = "Signup failed";
            msg.style.color = "red";
            console.error(err);
        }
    };
}

// ---------------- Dashboard ----------------
async function initDashboard() {
    if (!getToken()) { location.href = "/"; return; }

    const fileInput = document.getElementById("invoiceFile");
    const uploadBox = document.getElementById("uploadBox");
    const filename = document.getElementById("filename");
    const uploadBtn = document.getElementById("uploadBtn");
    const exportSelect = document.getElementById("exportSelect");
    const uploadResult = document.getElementById("uploadResult");
    const historyBody = document.getElementById("historyBody");
    const historyEmpty = document.getElementById("historyEmpty");

    if (!fileInput || !uploadBox || !filename || !uploadBtn || !exportSelect || !uploadResult || !historyBody || !historyEmpty) return;

    // ---------- File Upload UI ----------
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
    fileInput.addEventListener("change", () => { filename.textContent = fileInput.files[0]?.name || ""; });

    uploadBtn.onclick = async () => {
        if (!fileInput.files.length) { uploadResult.textContent = "Please select file"; uploadResult.style.color = "red"; return; }
        uploadResult.textContent = "Processing..."; uploadResult.style.color = "black";

        const fd = new FormData();
        fd.append("file", fileInput.files[0]);
        fd.append("export_format", exportSelect.value);

        try {
            const res = await fetch("/process_invoice", {
                method: "POST",
                headers: authHeaders(),
                body: fd
            });
            const body = await res.json().catch(() => ({ detail: "Invalid response" }));

            if (!res.ok) {
                uploadResult.textContent = body.detail || JSON.stringify(body);
                uploadResult.style.color = "red";
                await loadHistory();
                return;
            }

            uploadResult.textContent = "Done: " + (body.export?.file || body.export?.url || JSON.stringify(body));
            uploadResult.style.color = "green";
            await loadHistory();
        } catch (err) {
            uploadResult.textContent = "Upload error";
            uploadResult.style.color = "red";
            console.error(err);
        }
    };

    // ---------- Load History ----------
    async function loadHistory() {
        historyBody.innerHTML = "";
        historyEmpty.style.display = "none";
        try {
            const res = await fetch("/invoices", { headers: { ...authHeaders(), "Accept": "application/json" } });
            if (!res.ok) {
                historyEmpty.textContent = "Failed to load history.";
                historyEmpty.style.display = "block";
                return;
            }

            const data = await res.json();
            const invoices = data.invoices || data;

            if (!invoices || invoices.length === 0) {
                historyEmpty.style.display = "block";
                return;
            }

            for (const inv of invoices) {
                const tr = document.createElement("tr");
                const exportInfo = inv.export || inv.exports?.slice(-1)?.[0] || {};
                const exportPath = exportInfo.path || exportInfo.export_path || exportInfo.url || null;
                const exportFormat = exportInfo.format || exportInfo.export_format || "";

                const actionsTd = document.createElement("td");

                if (exportFormat && exportFormat !== "gsheets" && exportPath) {
                    const a = document.createElement("a");
                    a.href = exportPath.startsWith("http") ? exportPath : `/download/${exportInfo.id}`;
                    a.textContent = "Download";
                    a.className = "btn";
                    a.style.marginRight = "6px";
                    actionsTd.appendChild(a);
                }

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
                    <td>${(inv.normalized && JSON.parse(inv.normalized).invoice_number) || inv.invoice_number || ""}</td>
                    <td>${(inv.normalized && JSON.parse(inv.normalized).vendor) || inv.vendor || ""}</td>
                    <td>${(inv.normalized && JSON.parse(inv.normalized).date) || inv.date || ""}</td>
                    <td>${exportFormat || ""}</td>
                `;
                tr.appendChild(actionsTd);
                historyBody.appendChild(tr);
            }
        } catch (err) {
            historyEmpty.textContent = "Error loading history";
            historyEmpty.style.display = "block";
            console.error(err);
        }
    }

    await loadHistory();
}
