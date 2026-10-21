/* App shell: tab navigation, fetch helper, toasts. Every other js/*.js file
   attaches to the shared `App` namespace rather than declaring its own globals. */
const App = {
    state: {
        rulesets: [],      // [{key, num_decks, dealer_hits_soft_17, double_after_split, surrender, penetration}, ...]
        systems: [],       // [{slug, name, level, balanced, ...}, ...]
        ruleset: null,     // currently selected ruleset key
        system: null,      // currently selected system slug (doubles as the Play tab's playing system)
    },
    listeners: [],         // callbacks(rulesetKey, systemSlug) run whenever the shared selector changes
    onRulesChange(fn) { this.listeners.push(fn); },
    notifyRulesChange() {
        for (const fn of this.listeners) fn(this.state.ruleset, this.state.system);
    },
};

App.api = async function (path, options = {}) {
    const opts = { headers: { "Content-Type": "application/json" }, ...options };
    const res = await fetch(path, opts);
    let body = null;
    try { body = await res.json(); } catch (e) { /* no JSON body */ }
    if (!res.ok) {
        const msg = (body && body.error) ? body.error : `${res.status} ${res.statusText}`;
        throw new Error(msg);
    }
    return body;
};

App.get = (path) => App.api(path, { method: "GET" });
App.post = (path, data) => App.api(path, { method: "POST", body: JSON.stringify(data) });

App.toast = function (message, isError = false) {
    const container = document.getElementById("toast-container");
    const el = document.createElement("div");
    el.className = "toast" + (isError ? " error" : "");
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 5000);
};

App.fmtPct = (x) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : (x * 100).toFixed(2) + "%";
App.fmtNum = (x, d = 2) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : Number(x).toFixed(d);
App.fmtMoney = (x) => (x === null || x === undefined || Number.isNaN(x)) ? "—" : "$" + Number(x).toFixed(0);

document.addEventListener("DOMContentLoaded", () => {
    const tabButtons = document.querySelectorAll(".tab-btn");
    tabButtons.forEach((btn) => {
        btn.addEventListener("click", () => {
            tabButtons.forEach((b) => { b.classList.remove("active"); b.setAttribute("aria-selected", "false"); });
            document.querySelectorAll(".tab-content").forEach((c) => c.classList.remove("active"));
            btn.classList.add("active");
            btn.setAttribute("aria-selected", "true");
            document.getElementById("tab-" + btn.dataset.tab).classList.add("active");
        });
    });

    App.init().catch((e) => App.toast("Failed to load /api/rules: " + e.message, true));
});

App.init = async function () {
    const data = await App.get("/api/rules");
    App.state.rulesets = data.rulesets;
    App.state.systems = data.systems;
    App.state.ruleset = data.defaults.ruleset;
    App.state.system = data.defaults.system;

    App.Rules.populateSelectors(data);
    App.notifyRulesChange();
};
