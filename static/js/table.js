/* Play tab: drives /api/game/* through a server-side session, and /api/advise
   for the "what should I do" panel. The shoe/session are recreated whenever
   the shared ruleset/system selector changes (see App.onRulesChange below) --
   a session is tied to the RuleSet+system it was created with. */
App.Table = {
    sessionId: null,
    sessionRules: null,
    sessionSystem: null,
    currentAdviceEv: null,       // {action_word: ev} from the last /api/advise call
    currentLegal: new Set(),
    tally: { correct: 0, incorrect: 0, evLost: 0 },
};

App.Table.els = {};

document.addEventListener("DOMContentLoaded", () => {
    const T = App.Table;
    T.els.dealerCards = document.getElementById("dealer-cards");
    T.els.dealerTotal = document.getElementById("dealer-total");
    T.els.playerCards = document.getElementById("player-cards");
    T.els.playerTotal = document.getElementById("player-total");
    T.els.status = document.getElementById("play-status");
    T.els.actionRow = document.getElementById("action-row");
    T.els.adviceBadgeWrap = document.getElementById("advice-badge-wrap");
    T.els.adviceAction = document.getElementById("advice-action");
    T.els.adviceReason = document.getElementById("advice-reason");
    T.els.evChart = document.getElementById("ev-chart");

    document.getElementById("btn-deal").addEventListener("click", () => T.deal().catch(T.fail));
    T.els.actionRow.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.addEventListener("click", () => T.act(btn.dataset.action).catch(T.fail));
    });

    App.onRulesChange(() => {
        // A mid-round session can't switch rulesets underneath the player; just
        // mark the session stale so the next Deal recreates it from scratch.
        T.sessionId = null;
        T.setActionsEnabled(new Set());
        T.els.status.textContent = "Ruleset/system changed -- next deal starts a fresh shoe.";
    });
});

App.Table.fail = function (err) {
    App.toast(err.message, true);
    App.Table.els.status.textContent = err.message;
    App.Table.els.status.className = "status-line error";
};

App.Table.ensureSession = async function () {
    if (this.sessionId && this.sessionRules === App.state.ruleset && this.sessionSystem === App.state.system) return;
    const data = await App.post("/api/game/new", { rules: App.state.ruleset, system: App.state.system });
    this.sessionId = data.session_id;
    this.sessionRules = App.state.ruleset;
    this.sessionSystem = App.state.system;
};

App.Table.renderCard = function (container, rank, faceDown = false) {
    const card = document.createElement("div");
    card.className = "playing-card" + (faceDown ? " card-back" : "");
    if (!faceDown) {
        card.innerHTML = `<span class="pc-top">${rank}</span><span class="pc-bottom">${rank}</span>`;
    }
    container.appendChild(card);
};

App.Table.renderHands = function (state) {
    this.els.dealerCards.innerHTML = "";
    this.els.playerCards.innerHTML = "";
    if (state.dealer_up) {
        this.renderCard(this.els.dealerCards, state.dealer_up);
        this.renderCard(this.els.dealerCards, "", true);
        this.els.dealerTotal.textContent = "";
    }
    if (state.hand) {
        for (const rank of state.hand) this.renderCard(this.els.playerCards, rank);
        this.els.playerTotal.textContent = `(${state.total}${state.is_soft ? " soft" : ""})`;
    }
    document.getElementById("m-rc").textContent = App.fmtNum(state.running_count, 1);
    document.getElementById("m-tc").textContent = state.true_count !== undefined ? App.fmtNum(state.true_count, 1) : "—";
    document.getElementById("m-decks").textContent = App.fmtNum(state.decks_remaining, 2);
};

App.Table.renderRoundResult = function (result) {
    this.els.dealerCards.innerHTML = "";
    for (const rank of result.dealer_hand) this.renderCard(this.els.dealerCards, rank);
    this.els.dealerTotal.textContent = `(${result.dealer_total})`;

    this.els.playerCards.innerHTML = "";
    const lastHand = result.hands[result.hands.length - 1];
    if (lastHand) {
        for (const rank of lastHand.cards) this.renderCard(this.els.playerCards, rank);
        this.els.playerTotal.textContent = `(${lastHand.total})`;
    }

    const netStr = result.net >= 0 ? `+${App.fmtMoney(result.net)}` : `-${App.fmtMoney(Math.abs(result.net))}`;
    this.els.status.textContent = `Round settled: net ${netStr}` + (result.dealer_blackjack ? " (dealer blackjack)" : "");
    this.els.status.className = "status-line " + (result.net >= 0 ? "ok" : "error");
    this.setActionsEnabled(new Set());
    this.clearAdvice("Deal another hand to continue.");
};

App.Table.setActionsEnabled = function (legalSet) {
    this.currentLegal = legalSet;
    this.els.actionRow.querySelectorAll("button[data-action]").forEach((btn) => {
        btn.disabled = !legalSet.has(btn.dataset.action);
    });
};

App.Table.clearAdvice = function (msg) {
    this.currentAdviceEv = null;
    this.els.adviceBadgeWrap.innerHTML = "";
    this.els.adviceAction.textContent = "—";
    this.els.adviceReason.textContent = msg;
    this.els.evChart.innerHTML = "";
};

App.Table.argmaxLegal = function (evObj, legalSet) {
    let best = null, bestVal = -Infinity;
    for (const [k, v] of Object.entries(evObj)) {
        if (legalSet.has(k) && v > bestVal) { best = k; bestVal = v; }
    }
    return best;
};

App.Table.renderEvChart = function (evObj, legalSet, recommendedWord) {
    this.els.evChart.innerHTML = "";
    const entries = Object.entries(evObj).filter(([k]) => legalSet.size === 0 || legalSet.has(k));
    const scale = Math.max(0.25, ...entries.map(([, v]) => Math.abs(v)));
    for (const [word, val] of entries) {
        const row = document.createElement("div");
        row.className = "ev-row";
        const pct = Math.min(50, (Math.abs(val) / scale) * 50);
        row.innerHTML = `
            <span class="ev-label${word === recommendedWord ? " chosen" : ""}">${word}</span>
            <div class="ev-track">
                <div class="ev-zero-line"></div>
                <div class="ev-fill ${val >= 0 ? "pos" : "neg"}" style="width:${pct}%"></div>
            </div>
            <span class="ev-value${word === recommendedWord ? " best" : ""}">${App.fmtNum(val, 3)}</span>`;
        this.els.evChart.appendChild(row);
    }
};

App.Table.fetchAdvice = async function (state) {
    const data = await App.post("/api/advise", {
        player_cards: state.hand,
        dealer_up: state.dealer_up,
        running_count: state.running_count,
        decks_remaining: state.decks_remaining,
        rules: App.state.ruleset,
        system: App.state.system,
    });
    this.currentAdviceEv = data.ev;
    const legalSet = new Set(state.legal_actions);
    const recommended = (data.is_deviation && legalSet.has(data.deviation_action))
        ? data.deviation_action
        : this.argmaxLegal(data.ev, legalSet);
    this.recommendedWord = recommended;

    this.els.adviceBadgeWrap.innerHTML = data.is_deviation
        ? `<span class="advice-badge deviation">Deviation (${data.deviation_reason})</span>`
        : `<span class="advice-badge basic">Basic Strategy</span>`;
    this.els.adviceAction.textContent = recommended || "—";
    this.els.adviceReason.textContent = data.is_deviation
        ? `${data.reason} at a neutral shoe, but TC ${App.fmtNum(data.true_count, 1)} flips this (EV gain ${App.fmtNum(data.ev_gain, 4)}).`
        : data.reason;
    this.renderEvChart(data.ev, legalSet, recommended);
};

App.Table.applyState = async function (state) {
    this.renderHands(state);
    if (state.round_active && state.legal_actions) {
        this.setActionsEnabled(new Set(state.legal_actions));
        this.els.status.textContent = "";
        this.els.status.className = "status-line";
        try { await this.fetchAdvice(state); } catch (e) { this.fail(e); }
    } else {
        this.setActionsEnabled(new Set());
    }
};

App.Table.deal = async function () {
    await this.ensureSession();
    const bet = Number(document.getElementById("bet-amount").value) || 1;
    const data = await App.post("/api/game/deal", { session_id: this.sessionId, bet });
    if (data.round_result) {
        this.renderRoundResult(data.round_result);
        document.getElementById("m-rc").textContent = App.fmtNum(data.state.running_count, 1);
        document.getElementById("m-tc").textContent = data.state.true_count !== undefined ? App.fmtNum(data.state.true_count, 1) : "—";
        document.getElementById("m-decks").textContent = App.fmtNum(data.state.decks_remaining, 2);
        return;
    }
    await this.applyState(data.state);
};

App.Table.act = async function (actionName) {
    if (this.currentAdviceEv && this.recommendedWord) {
        const chosenEv = this.currentAdviceEv[actionName];
        const bestEv = this.currentAdviceEv[this.recommendedWord];
        if (chosenEv !== undefined && bestEv !== undefined) {
            if (actionName === this.recommendedWord) {
                this.tally.correct += 1;
            } else {
                this.tally.incorrect += 1;
                this.tally.evLost += Math.max(0, bestEv - chosenEv);
            }
            document.getElementById("tally-correct").textContent = this.tally.correct;
            document.getElementById("tally-incorrect").textContent = this.tally.incorrect;
            document.getElementById("tally-ev").textContent = this.tally.evLost.toFixed(3);
        }
    }

    const data = await App.post("/api/game/action", { session_id: this.sessionId, action: actionName });
    if (data.round_result) {
        this.renderRoundResult(data.round_result);
        return;
    }
    await this.applyState(data.state);
};
