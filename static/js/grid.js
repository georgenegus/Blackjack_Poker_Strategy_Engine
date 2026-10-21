/* Strategy Grid tab: renders the solved grid (hard / soft / pairs) for the
   selected ruleset. Cell keys from /api/grid are "{total}v{upcard_value}"
   (upcard_value 11 == Ace) for hard/soft, "{rank}{rank}v{upcard_value}" for
   pairs -- see src/strategy/grid_builder.py. */
App.Grid = {};

const GRID_CODE_LABEL = {
    H: "Hit", S: "Stand", D: "Double/Hit", Ds: "Double/Stand",
    P: "Split", Ph: "Split/Hit", Rh: "Surrender/Hit", Rs: "Surrender/Stand", Rp: "Surrender/Split",
};
const UPCARD_ORDER = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11];
const PAIR_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"];

App.Grid.upcardLabel = (v) => (v === 11 ? "A" : String(v));

App.Grid.buildTable = function (caption, rowLabels, rowKeyFn, cells) {
    const table = document.createElement("table");
    table.className = "strategy-table";
    const cap = document.createElement("caption");
    cap.textContent = caption;
    table.appendChild(cap);

    const thead = document.createElement("thead");
    const headRow = document.createElement("tr");
    headRow.innerHTML = `<th class="rowhead"></th>` + UPCARD_ORDER.map((u) => `<th>${App.Grid.upcardLabel(u)}</th>`).join("");
    thead.appendChild(headRow);
    table.appendChild(thead);

    const tbody = document.createElement("tbody");
    rowLabels.forEach((label, i) => {
        const tr = document.createElement("tr");
        let rowHtml = `<th class="rowhead">${label}</th>`;
        for (const u of UPCARD_ORDER) {
            const key = rowKeyFn(i, u);
            const cell = cells[key];
            if (!cell) { rowHtml += `<td>?</td>`; continue; }
            const close = cell.margin < 0.001 ? " close" : "";
            const title = Object.entries(cell.ev_by_action).map(([k, v]) => `${k}=${v.toFixed(4)}`).join("  ") +
                `  (margin ${cell.margin.toFixed(4)})`;
            rowHtml += `<td class="cell-${cell.action}${close}" title="${title}">${cell.action}</td>`;
        }
        tr.innerHTML = rowHtml;
        tbody.appendChild(tr);
    });
    table.appendChild(tbody);

    const wrap = document.createElement("div");
    wrap.className = "strategy-table-wrap";
    wrap.appendChild(table);
    return wrap;
};

App.Grid.renderLegend = function () {
    const legend = document.getElementById("grid-legend");
    legend.innerHTML = Object.entries(GRID_CODE_LABEL).map(([code, label]) => `
        <span class="legend-chip"><span class="legend-swatch cell-${code}"></span>${code} &mdash; ${label}</span>`
    ).join("") + `<span class="legend-chip">&bull; near-indifferent (EV gap &lt; 0.001)</span>`;
};

App.Grid.load = async function () {
    const status = document.getElementById("grid-status");
    const container = document.getElementById("grid-tables");
    status.textContent = "Loading...";
    status.className = "status-line";
    try {
        const data = await App.get(`/api/grid?ruleset=${encodeURIComponent(App.state.ruleset)}`);
        container.innerHTML = "";
        this.renderLegend();

        const hardLabels = [];
        for (let t = 5; t <= 20; t++) hardLabels.push(String(t));
        container.appendChild(this.buildTable("Hard Totals", hardLabels, (i, u) => `${i + 5}v${u}`, data.hard));

        const softLabels = [];
        for (let t = 13; t <= 20; t++) softLabels.push(`A,${t - 11}`);
        container.appendChild(this.buildTable("Soft Totals", softLabels, (i, u) => `${i + 13}v${u}`, data.soft));

        const pairLabels = PAIR_RANKS.map((r) => `${r},${r}`);
        container.appendChild(this.buildTable("Pairs", pairLabels, (i, u) => `${PAIR_RANKS[i]}${PAIR_RANKS[i]}v${u}`, data.pairs));

        status.textContent = "";
    } catch (e) {
        status.textContent = e.message;
        status.className = "status-line error";
    }
};

document.addEventListener("DOMContentLoaded", () => {
    App.onRulesChange(() => App.Grid.load().catch(() => {}));
});
