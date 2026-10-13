"""Local HTTP server for the standalone MTF signal panel."""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from gold_mtf_flow.signal_state import SignalStateStore

PANEL_HTML = """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1"/>
  <title>Main Force MTF — Painel de Sinais</title>
  <style>
    :root {
      --bg: #0d1117;
      --card: #161b22;
      --border: #30363d;
      --text: #e6edf3;
      --muted: #8b949e;
      --long: #3fb950;
      --short: #f85149;
      --neutral: #d29922;
      --mf: #58a6ff;
      --retail: #bc8cff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      min-height: 100vh;
    }
    header {
      padding: 1rem 1.5rem;
      border-bottom: 1px solid var(--border);
      display: flex;
      flex-wrap: wrap;
      align-items: center;
      gap: 1rem;
      justify-content: space-between;
    }
    h1 { font-size: 1.15rem; margin: 0; font-weight: 600; }
    .meta { font-size: 0.85rem; color: var(--muted); }
    .badge {
      display: inline-block;
      padding: 0.2rem 0.55rem;
      border-radius: 999px;
      font-size: 0.75rem;
      border: 1px solid var(--border);
    }
    .badge.ok { border-color: var(--long); color: var(--long); }
    .badge.off { border-color: var(--muted); color: var(--muted); }
    main { padding: 1.25rem 1.5rem 2rem; max-width: 1100px; margin: 0 auto; }
    .signal-hero {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 1.5rem;
      text-align: center;
      margin-bottom: 1.25rem;
    }
    .signal-label { font-size: 0.8rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
    .signal-value {
      font-size: 2.5rem;
      font-weight: 700;
      margin: 0.35rem 0;
    }
    .signal-value.long { color: var(--long); }
    .signal-value.short { color: var(--short); }
    .signal-value.neutral { color: var(--neutral); }
    .conf-bar {
      height: 8px;
      background: #21262d;
      border-radius: 4px;
      overflow: hidden;
      max-width: 320px;
      margin: 0.75rem auto 0;
    }
    .conf-fill { height: 100%; background: linear-gradient(90deg, var(--mf), var(--long)); transition: width 0.4s; }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
      gap: 1rem;
      margin-bottom: 1.25rem;
    }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 10px;
      padding: 1rem 1.1rem;
    }
    .card h2 { margin: 0 0 0.75rem; font-size: 0.95rem; color: var(--muted); }
    .metric { margin-bottom: 0.65rem; }
    .metric label { font-size: 0.72rem; color: var(--muted); display: block; margin-bottom: 0.2rem; }
    .bar-wrap {
      height: 22px;
      background: #21262d;
      border-radius: 4px;
      position: relative;
      overflow: hidden;
    }
    .bar-center {
      position: absolute;
      left: 50%;
      top: 0;
      bottom: 0;
      width: 1px;
      background: var(--border);
    }
    .bar-fill {
      position: absolute;
      top: 4px;
      bottom: 4px;
      border-radius: 2px;
      transition: left 0.35s, width 0.35s;
    }
    .bar-fill.mf { background: var(--mf); }
    .bar-fill.retail { background: var(--retail); opacity: 0.85; }
    .val { font-size: 0.85rem; font-variant-numeric: tabular-nums; }
    .alert {
      display: none;
      background: #3d2a00;
      border: 1px solid var(--neutral);
      color: #f0cc66;
      padding: 0.75rem 1rem;
      border-radius: 8px;
      margin-bottom: 1rem;
      font-size: 0.9rem;
    }
    .alert.show { display: block; }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.82rem;
    }
    th, td {
      text-align: left;
      padding: 0.45rem 0.5rem;
      border-bottom: 1px solid var(--border);
    }
    th { color: var(--muted); font-weight: 500; }
    .sig-pill {
      font-weight: 600;
      padding: 0.1rem 0.4rem;
      border-radius: 4px;
    }
    .sig-pill.l { background: rgba(63,185,80,0.2); color: var(--long); }
    .sig-pill.s { background: rgba(248,81,73,0.2); color: var(--short); }
    .sig-pill.n { background: rgba(210,153,34,0.2); color: var(--neutral); }
    .empty { color: var(--muted); text-align: center; padding: 2rem; }
  </style>
</head>
<body>
  <header>
    <div>
      <h1>Main Force Funds Flow — Ouro MTF</h1>
      <div class="meta">Painel independente · 10m / 30m / 1H · sem EA</div>
    </div>
    <div class="meta">
      <span id="symbol">—</span> ·
      Fonte: <span id="source">—</span> ·
      <span id="conn" class="badge off">aguardando</span>
    </div>
  </header>
  <main>
    <div id="divergence" class="alert"></div>
    <section class="signal-hero" id="hero">
      <div class="signal-label">Sinal composto (grid)</div>
      <div id="signalText" class="signal-value neutral">—</div>
      <div class="meta">Confiança: <span id="confPct">0</span>%</div>
      <div class="conf-bar"><div id="confFill" class="conf-fill" style="width:0%"></div></div>
      <div class="meta" style="margin-top:0.75rem">Última barra 10m: <span id="ts">—</span></div>
    </section>
    <div class="grid" id="tfGrid"></div>
    <section class="card">
      <h2>Histórico recente (fechamentos 10m)</h2>
      <div id="histWrap">
        <table>
          <thead>
            <tr>
              <th>Timestamp</th>
              <th>Sinal</th>
              <th>Conf.</th>
              <th>MF 10m</th>
              <th>MF 30m</th>
              <th>MF 1H</th>
            </tr>
          </thead>
          <tbody id="histBody"></tbody>
        </table>
      </div>
    </section>
  </main>
  <script>
    const TF_ORDER = ["10m", "30m", "1H"];
    const TF_LABEL = {"10m": "10 min (gatilho)", "30m": "30 min (confirmação)", "1H": "1 hora (viés)"};

    function barStyle(norm) {
      const v = Math.max(-1, Math.min(1, norm));
      const pct = Math.abs(v) * 50;
      if (v >= 0) return { left: "50%", width: pct + "%" };
      return { left: (50 - pct) + "%", width: pct + "%" };
    }

    function signalLabel(sig) {
      if (sig === 1) return { text: "LONG (+1)", cls: "long" };
      if (sig === -1) return { text: "SHORT (−1)", cls: "short" };
      return { text: "NEUTRO (0)", cls: "neutral" };
    }

    function renderTfCard(tf, data) {
      const mf = data.mf_delta_norm ?? 0;
      const rt = data.retail_delta_norm ?? 0;
      const mfs = barStyle(mf);
      const rts = barStyle(rt);
      return `
        <article class="card">
          <h2>${TF_LABEL[tf] || tf}</h2>
          <div class="metric">
            <label>Main Force Δ norm</label>
            <div class="bar-wrap"><div class="bar-center"></div>
              <div class="bar-fill mf" style="left:${mfs.left};width:${mfs.width}"></div>
            </div>
            <span class="val">${mf.toFixed(3)}</span>
          </div>
          <div class="metric">
            <label>Varejo Δ norm</label>
            <div class="bar-wrap"><div class="bar-center"></div>
              <div class="bar-fill retail" style="left:${rts.left};width:${rts.width}"></div>
            </div>
            <span class="val">${rt.toFixed(3)}</span>
          </div>
        </article>`;
    }

    function checkDivergence(tf, latest) {
      const tfs = latest.timeframes;
      if (!tfs) return null;
      for (const key of ["30m", "1H"]) {
        const x = tfs[key];
        if (!x) continue;
        const mf = x.mf_delta_norm, rt = x.retail_delta_norm;
        if (mf > 0.1 && rt < -0.15) return "Possível distribuição: MF comprador em " + key + ", varejo vendendo — cautela em LONG.";
        if (mf < -0.1 && rt > 0.15) return "Possível absorção: MF vendedor em " + key + ", varejo comprando — cautela em SHORT.";
      }
      return null;
    }

    function renderHistory(rows) {
      const body = document.getElementById("histBody");
      if (!rows || !rows.length) {
        body.innerHTML = '<tr><td colspan="6" class="empty">Sem histórico ainda</td></tr>';
        return;
      }
      body.innerHTML = rows.slice().reverse().map(r => {
        const s = r.composite_signal;
        const pill = s === 1 ? "l" : (s === -1 ? "s" : "n");
        const t = r.timeframes || {};
        return `<tr>
          <td>${r.timestamp || "—"}</td>
          <td><span class="sig-pill ${pill}">${s}</span></td>
          <td>${((r.confidence_score ?? 0) * 100).toFixed(0)}%</td>
          <td>${(t["10m"]?.mf_delta_norm ?? 0).toFixed(2)}</td>
          <td>${(t["30m"]?.mf_delta_norm ?? 0).toFixed(2)}</td>
          <td>${(t["1H"]?.mf_delta_norm ?? 0).toFixed(2)}</td>
        </tr>`;
      }).join("");
    }

    async function tick() {
      try {
        const res = await fetch("/api/state");
        const st = await res.json();
        document.getElementById("source").textContent = st.source || "—";
        const conn = document.getElementById("conn");
        if (st.latest) {
          conn.textContent = "ativo · " + (st.message_count || 0) + " msgs";
          conn.className = "badge ok";
        } else {
          conn.textContent = "aguardando dados";
          conn.className = "badge off";
        }
        const L = st.latest;
        if (!L) {
          document.getElementById("signalText").textContent = "Aguardando…";
          return;
        }
        document.getElementById("symbol").textContent = L.symbol || "—";
        const sl = signalLabel(L.composite_signal);
        const el = document.getElementById("signalText");
        el.textContent = sl.text;
        el.className = "signal-value " + sl.cls;
        const conf = L.confidence_score ?? 0;
        document.getElementById("confPct").textContent = (conf * 100).toFixed(0);
        document.getElementById("confFill").style.width = (conf * 100) + "%";
        document.getElementById("ts").textContent = L.timestamp || "—";
        const grid = document.getElementById("tfGrid");
        const tfs = L.timeframes || {};
        grid.innerHTML = TF_ORDER.filter(t => tfs[t]).map(t => renderTfCard(t, tfs[t])).join("");
        const div = checkDivergence(null, L);
        const da = document.getElementById("divergence");
        if (div) { da.textContent = "⚠ " + div; da.classList.add("show"); }
        else { da.classList.remove("show"); }
        renderHistory(st.history || []);
      } catch (e) {
        console.error(e);
      }
    }
    setInterval(tick, 1500);
    tick();
  </script>
</body>
</html>
"""


def create_panel_handler(store: SignalStateStore, cfg: dict) -> type[BaseHTTPRequestHandler]:
    """Build a request handler class bound to ``store`` and config snapshot."""

    class PanelHandler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            return

        def do_GET(self) -> None:
            path = self.path.split("?", 1)[0]
            if path == "/api/state":
                body = store.snapshot()
                body["config"] = {
                    "symbol": cfg.get("symbol"),
                    "threshold_1h": cfg.get("threshold_1h"),
                    "threshold_30m": cfg.get("threshold_30m"),
                    "threshold_10m": cfg.get("threshold_10m"),
                }
                data = json.dumps(body).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            if path in ("/", "/index.html"):
                data = PANEL_HTML.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                return
            self.send_response(404)
            self.end_headers()

    return PanelHandler


class PanelServer:
    """Threaded HTTP server for the signal dashboard."""

    def __init__(self, store: SignalStateStore, cfg: dict, host: str, port: int) -> None:
        handler = create_panel_handler(store, cfg)
        self._httpd = ThreadingHTTPServer((host, port), handler)
        self._thread: threading.Thread | None = None
        self.host = host
        self.port = port

    @property
    def url(self) -> str:
        return f"http://{self.host}:{self.port}/"

    def start(self) -> None:
        self._thread = threading.Thread(target=self._httpd.serve_forever, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._httpd.shutdown()
