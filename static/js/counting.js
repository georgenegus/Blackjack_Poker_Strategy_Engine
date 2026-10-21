/* Counting tab: a manually-clocked shoe (click a rank as it's dealt, or run
   the drill) fed through /api/count in dual-system mode -- betting system
   (its own selector here) vs playing system (the shared selector in the
   rules bar). Both counters always see the same card sequence. */
App.Counting = {
    dealt: [],       // ranks seen so far this "shoe"
    drillTimer: null,
    drillActualTC: null,
};

const COUNT_RANKS = ["2", "3", "4", "5", "6", "7", "8", "9", "T", "A"];
// Roughly matches a real 13-rank deck: T/J/Q/K collapse to one 4x-weighted bucket.
const COUNT_WEIGHTS = [1, 1, 1, 1, 1, 1, 1, 1, 4, 1];

App.Counting.numDecks = () => Number(document.getElementById("num-decks-count").value) || 6;

App.Counting.buildDealGrid = function () {
    const grid = document.getElementById("rank-deal-grid");
    grid.innerHTML = "";
    for (const rank of COUNT_RANKS) {
        const btn = document.createElement("button");
        btn.textContent = rank;
        btn.addEventListener("click", () => this.deal(rank));
        grid.appendChild(btn);
    }
};

App.Counting.buildTallyGrid = function () {
    const grid = document.getElementById("tally-grid");
    grid.innerHTML = COUNT_RANKS.map((r) => `
        <div class="tally-cell" data-rank="${r}"><div class="rk">${r}</div><div class="ct">0</div></div>`
    ).join("");
};

App.Counting.updateTally = function () {
    const counts = {};
    for (const r of COUNT_RANKS) counts[r] = 0;
    for (const r of this.dealt) counts[r] = (counts[r] || 0) + 1;
    document.querySelectorAll("#tally-grid .tally-cell").forEach((cell) => {
        cell.querySelector(".ct").textContent = counts[cell.dataset.rank];
    });
};

App.Counting.refresh = async function () {
    const bettingSlug = document.getElementById("sel-betting-system").value;
    try {
        const data = await App.post("/api/count", {
            cards: this.dealt,
            num_decks: this.numDecks(),
            betting_system: bettingSlug,
            playing_system: App.state.system,
        });
        document.getElementById("c-bet-rc").textContent = App.fmtNum(data.betting.running_count, 1);
        document.getElementById("c-bet-tc").textContent = data.betting.true_count_betting !== undefined
            ? App.fmtNum(data.betting.true_count_betting, 1) : "—";
        document.getElementById("c-play-rc").textContent = App.fmtNum(data.playing.running_count, 1);
        document.getElementById("c-play-tc").textContent = data.playing.true_count_playing !== undefined
            ? App.fmtNum(data.playing.true_count_playing, 1) : "—";
        this.drillActualTC = data.playing.true_count_playing;
    } catch (e) {
        App.toast(e.message, true);
    }
};

App.Counting.deal = function (rank) {
    this.dealt.push(rank);
    this.updateTally();
    this.refresh();
};

App.Counting.reset = function () {
    this.dealt = [];
    this.updateTally();
    this.refresh();
};

App.Counting.weightedRandomRank = function () {
    const total = COUNT_WEIGHTS.reduce((a, b) => a + b, 0);
    let r = Math.random() * total;
    for (let i = 0; i < COUNT_RANKS.length; i++) {
        r -= COUNT_WEIGHTS[i];
        if (r <= 0) return COUNT_RANKS[i];
    }
    return COUNT_RANKS[COUNT_RANKS.length - 1];
};

App.Counting.startDrill = function () {
    if (this.drillTimer) clearInterval(this.drillTimer);
    this.reset();
    const flash = document.getElementById("drill-flash");
    const status = document.getElementById("drill-status");
    document.getElementById("btn-drill-check").disabled = true;
    status.textContent = "";
    status.className = "status-line";

    const n = 15 + Math.floor(Math.random() * 16); // 15-30 cards
    let i = 0;
    this.drillTimer = setInterval(() => {
        if (i >= n) {
            clearInterval(this.drillTimer);
            this.drillTimer = null;
            flash.textContent = "?";
            document.getElementById("btn-drill-check").disabled = false;
            status.textContent = `${n} cards dealt -- enter your true count guess (playing system).`;
            return;
        }
        const rank = this.weightedRandomRank();
        flash.textContent = rank;
        this.dealt.push(rank);
        this.updateTally();
        this.refresh();
        i += 1;
    }, 700);
};

App.Counting.checkGuess = function () {
    const guess = Number(document.getElementById("drill-guess").value);
    const status = document.getElementById("drill-status");
    if (this.drillActualTC === null || this.drillActualTC === undefined) {
        status.textContent = "No true count available -- pick a balanced playing system.";
        status.className = "status-line error";
        return;
    }
    const diff = Math.abs(guess - this.drillActualTC);
    if (diff <= 0.5) {
        status.textContent = `Close enough! Actual true count: ${App.fmtNum(this.drillActualTC, 1)} (you guessed ${guess}).`;
        status.className = "status-line ok";
    } else {
        status.textContent = `Off by ${diff.toFixed(1)}. Actual true count: ${App.fmtNum(this.drillActualTC, 1)} (you guessed ${guess}).`;
        status.className = "status-line error";
    }
};

document.addEventListener("DOMContentLoaded", () => {
    App.Counting.buildDealGrid();
    App.Counting.buildTallyGrid();
    document.getElementById("btn-count-reset").addEventListener("click", () => App.Counting.reset());
    document.getElementById("num-decks-count").addEventListener("change", () => App.Counting.reset());
    document.getElementById("btn-drill-start").addEventListener("click", () => App.Counting.startDrill());
    document.getElementById("btn-drill-check").addEventListener("click", () => App.Counting.checkGuess());

    // The shared system selector doubles as the playing system here; the
    // betting-system selector is independently populated in rules.js.
    App.onRulesChange(() => App.Counting.refresh());
});
