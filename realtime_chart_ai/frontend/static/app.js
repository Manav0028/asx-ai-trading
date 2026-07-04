(function () {
  const params = new URLSearchParams(window.location.search);
  let ticker = params.get("ticker");

  const statusEl = document.getElementById("conn-status");
  const sourceEl = document.getElementById("source-badge");
  const titleEl = document.getElementById("ticker-title");
  const commentaryFeed = document.getElementById("commentary-feed");
  const journalBody = document.querySelector("#journal-table tbody");

  let chart, candleSeries, markers = [];

  function initChart() {
    const container = document.getElementById("chart-container");
    chart = LightweightCharts.createChart(container, {
      layout: { background: { color: "#0e1117" }, textColor: "#d7dae0" },
      grid: { vertLines: { color: "#1c2028" }, horzLines: { color: "#1c2028" } },
      timeScale: { timeVisible: true, secondsVisible: false },
      autoSize: true,
    });
    candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
      upColor: "#00c48c", downColor: "#ff5a5a",
      borderVisible: false, wickUpColor: "#00c48c", wickDownColor: "#ff5a5a",
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
      color: msg.direction === "long" ? "#00c48c" : "#ff5a5a",
      shape: msg.direction === "long" ? "arrowUp" : "arrowDown",
      text: `${msg.pattern_name} (${msg.composite_score.toFixed(0)})`,
    };
    markers.push(marker);
    candleSeries.setMarkers(markers);
    prependCommentary(msg);
  }

  function prependCommentary(msg) {
    const div = document.createElement("div");
    div.className = "commentary-item";
    div.innerHTML = `
      <div class="cm-header"><span>${new Date().toLocaleTimeString()}</span><span>${msg.smc_zone || ""}</span></div>
      <div class="cm-pattern ${msg.direction}">${msg.pattern_name} — ${msg.direction.toUpperCase()}</div>
      <div class="cm-text">${msg.claude_rationale || msg.rule_reason || ""}</div>
      <div class="cm-score">composite ${msg.composite_score.toFixed(1)}/100 · confidence ${(msg.confidence * 100).toFixed(0)}%</div>
    `;
    commentaryFeed.prepend(div);
  }

  function connect() {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${window.location.host}/ws/candles/${ticker}`);

    ws.onopen = () => {
      statusEl.textContent = "live";
      statusEl.className = "badge connected";
    };
    ws.onclose = () => {
      statusEl.textContent = "reconnecting…";
      statusEl.className = "badge disconnected";
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
        rows.forEach((row) => {
          const tr = document.createElement("tr");
          const actionText = row.action ? `${row.action.action_type} (${row.action.mode})` : "observed only";
          tr.innerHTML = `
            <td>${new Date(row.bar_ts).toLocaleTimeString()}</td>
            <td>${row.pattern_name}</td>
            <td>${row.direction}</td>
            <td>${row.composite_score ? row.composite_score.toFixed(0) : ""}</td>
            <td>${row.smc_zone || ""}</td>
            <td>${actionText}</td>
          `;
          journalBody.appendChild(tr);
        });
      });
  }

  function initTabs() {
    document.querySelectorAll(".tab-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
        document.querySelectorAll(".tab-view").forEach((v) => v.classList.remove("active"));
        btn.classList.add("active");
        document.getElementById(`${btn.dataset.tab}-view`).classList.add("active");
        if (btn.dataset.tab === "journal") loadJournal();
      });
    });
    document.getElementById("refresh-journal").addEventListener("click", loadJournal);
  }

  function init() {
    fetch("/api/tickers")
      .then((r) => r.json())
      .then((data) => {
        if (!ticker) ticker = data.tickers[0];
        titleEl.textContent = ticker;
        sourceEl.textContent = data.active_source;
        initChart();
        initTabs();
        connect();
      });
  }

  init();
})();
