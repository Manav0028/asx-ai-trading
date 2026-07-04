(function () {
  const params = new URLSearchParams(window.location.search);
  let ticker = params.get("ticker");

  const statusEl = document.getElementById("conn-status");
  const sourceEl = document.getElementById("source-badge");
  const titleEl = document.getElementById("ticker-title");
  const commentaryFeed = document.getElementById("commentary-feed");
  const commentaryEmpty = document.getElementById("commentary-empty");
  const journalBody = document.querySelector("#journal-table tbody");
  const journalEmpty = document.getElementById("journal-empty");

  let chart, candleSeries, markers = [];
  let commentaryCount = 0;

  function initChart() {
    const container = document.getElementById("chart-container");
    chart = LightweightCharts.createChart(container, {
      layout: { background: { color: "#12151c" }, textColor: "#9198ab", fontFamily: "Inter, sans-serif" },
      grid: { vertLines: { color: "#1a1e28" }, horzLines: { color: "#1a1e28" } },
      timeScale: { timeVisible: true, secondsVisible: false, borderColor: "#232838" },
      rightPriceScale: { borderColor: "#232838" },
      autoSize: true,
    });
    candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
      upColor: "#26c281", downColor: "#f0554c",
      borderVisible: false, wickUpColor: "#26c281", wickDownColor: "#f0554c",
    });
  }

  function toUnixSeconds(iso) {
    return Math.floor(new Date(iso).getTime() / 1000);
  }

  function handleCandleUpdate(msg) {
    if (msg.timeframe && msg.timeframe !== "1m") return; // chart shows the execution timeframe only
    candleSeries.update({
      time: toUnixSeconds(msg.ts), open: msg.open, high: msg.high, low: msg.low, close: msg.close,
    });
  }

  function handlePatternSignal(msg) {
    const marker = {
      time: toUnixSeconds(msg.bar_ts || new Date().toISOString()),
      position: msg.direction === "long" ? "belowBar" : "aboveBar",
      color: msg.direction === "long" ? "#26c281" : "#f0554c",
      shape: msg.direction === "long" ? "arrowUp" : "arrowDown",
      text: `${msg.pattern_name} (${msg.composite_score.toFixed(0)})`,
    };
    markers.push(marker);
    candleSeries.setMarkers(markers);
    prependCommentary(msg);
  }

  function prependCommentary(msg) {
    commentaryCount += 1;
    commentaryEmpty.classList.remove("visible");

    const dirIcon = msg.direction === "long" ? "ti-caret-up" : "ti-caret-down";
    const div = document.createElement("div");
    div.className = "commentary-item";
    div.innerHTML = `
      <div class="cm-header">
        <span>${new Date().toLocaleTimeString()}</span>
        <span class="cm-zone-chip">${msg.smc_zone || "n/a"}</span>
      </div>
      <div class="cm-pattern ${msg.direction}"><i class="ti ${dirIcon}" aria-hidden="true"></i> ${msg.pattern_name} — ${msg.direction.toUpperCase()}</div>
      <div class="cm-text">${msg.claude_rationale || msg.rule_reason || ""}</div>
      <div class="cm-score"><span>composite ${msg.composite_score.toFixed(1)}/100</span><span>confidence ${(msg.confidence * 100).toFixed(0)}%</span></div>
    `;
    commentaryFeed.prepend(div);
  }

  function setStatus(state) {
    statusEl.classList.remove("connected", "disconnected");
    if (state === "live") {
      statusEl.classList.add("connected");
      statusEl.innerHTML = '<i class="ti ti-plug-connected" aria-hidden="true"></i> live';
    } else {
      statusEl.classList.add("disconnected");
      statusEl.innerHTML = '<i class="ti ti-loader-2" aria-hidden="true"></i> reconnecting';
    }
  }

  function connect() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/candles/${ticker}`);

    ws.onopen = () => setStatus("live");
    ws.onclose = () => {
      setStatus("reconnecting");
      setTimeout(connect, 2000);
    };
    ws.onerror = () => ws.close();
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.type === "candle_update") handleCandleUpdate(msg);
      else if (msg.type === "pattern_signal") handlePatternSignal(msg);
    };
  }

  function loadJournal() {
    fetch(`/api/journal?ticker=${encodeURIComponent(ticker)}&limit=50`)
      .then((r) => r.json())
      .then((rows) => {
        journalBody.innerHTML = "";
        journalEmpty.classList.toggle("visible", rows.length === 0);
        rows.forEach((row) => {
          const tr = document.createElement("tr");
          const dirClass = row.direction === "long" ? "dir-long" : "dir-short";
          const actionChip = row.action
            ? `<span class="action-chip acted" title="${row.action.mode}">${row.action.action_type}</span>`
            : '<span class="action-chip">watch</span>';
          tr.innerHTML = `
            <td>${new Date(row.bar_ts).toLocaleTimeString()}</td>
            <td>${row.pattern_name}</td>
            <td class="${dirClass}">${row.direction}</td>
            <td class="score-cell">${row.composite_score ? row.composite_score.toFixed(0) : "—"}</td>
            <td>${row.smc_zone || "—"}</td>
            <td>${actionChip}</td>
          `;
          journalBody.appendChild(tr);
        });
      });
  }

  function initTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => {
          b.classList.remove("active");
          b.setAttribute("aria-selected", "false");
        });
        document.querySelectorAll(".tab-view").forEach((v) => v.classList.remove("active"));
        btn.classList.add("active");
        btn.setAttribute("aria-selected", "true");
        document.getElementById(`${btn.dataset.tab}-view`).classList.add("active");
        if (btn.dataset.tab === "journal") loadJournal();
      });
    });
    document.getElementById("refresh-journal").addEventListener("click", loadJournal);
  }

  function init() {
    commentaryEmpty.classList.add("visible");
    journalEmpty.classList.add("visible");

    // initTabs()/initChart() must run regardless of whether /api/tickers
    // succeeds — otherwise a slow-starting backend or a transient network
    // error leaves the whole page dead (no chart, no working tabs) with no
    // indication why.
    initChart();
    initTabs();

    fetch("/api/tickers")
      .then((r) => {
        if (!r.ok) throw new Error(`/api/tickers returned ${r.status}`);
        return r.json();
      })
      .then((data) => {
        if (!ticker) ticker = data.tickers[0];
        titleEl.textContent = ticker;
        sourceEl.textContent = data.active_source;
        connect();
      })
      .catch((err) => {
        console.error("Failed to load ticker list:", err);
        titleEl.textContent = ticker || "no ticker";
        statusEl.classList.add("disconnected");
        statusEl.innerHTML = '<i class="ti ti-alert-triangle" aria-hidden="true"></i> backend unavailable';
        sourceEl.textContent = "—";
        if (ticker) connect(); // still try the WS if a ticker was given via ?ticker=
      });
  }

  init();
})();
