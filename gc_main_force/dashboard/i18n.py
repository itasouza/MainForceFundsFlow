"""Screen copy for the Streamlit dashboard (Portuguese and English)."""

from __future__ import annotations

import re

import streamlit as st

LANGS = ("pt", "en")

_DIV_RE = re.compile(
    r"DIVERGENCE \((10m|30m|1H)\): Retail (selling|buying), Main Force (accumulating|distributing)"
)

STRINGS: dict[str, dict[str, str]] = {
    "pt": {
        "language": "Idioma",
        "lang.pt": "Português",
        "lang.en": "English",
        "sidebar.title": "Controles",
        "view_mode": "Modo de visualização",
        "mode.live": "Ao vivo (NinjaTrader / engine)",
        "mode.backtest": "Backtest (CSV)",
        "pause_live": "Pausar atualizações ao vivo",
        "exp.thresholds": "Limiares",
        "mf_min": "Main Force mín. contratos (GC)",
        "thr_1h": "Limiar 1H",
        "thr_30": "Limiar 30m",
        "thr_10": "Limiar 10m",
        "roll_h": "Janela do percentil (horas)",
        "exp.footprint": "Footprint",
        "show_fp": "Mostrar Rastro Institucional (LHB)",
        "show_fp_help": "Mapa por preço: onde o fluxo agride (Lee-Ready). O sinal MF continua com o limiar fixo.",
        "exp.ai": "IA — Regime / kill switch",
        "ai_on": "IA de regime ativa",
        "force_regime": "Forçar regime manual",
        "regime_opt.auto": "automático",
        "regime_opt.0": "0 — Chop / baixa volatilidade",
        "regime_opt.1": "1 — Tendência / padrão",
        "regime_opt.2": "2 — Alta volatilidade / notícia",
        "pause_signal": "Pausar sinal (override)",
        "pause_signal_help": "Kill switch humano: força a pausa do sinal e de novas entradas, independente da IA.",
        "apply_ai": "Aplicar controles da IA",
        "ai_saved": "Controles salvos — aplicados no próximo fechamento de 1H.",
        "session_filter": "Filtro de sessão",
        "session.all": "Todas",
        "session.asian": "Ásia (18:00–01:00 ET)",
        "session.london": "Londres (01:00–08:00 ET)",
        "session.new_york": "Nova York (08:00–17:00 ET)",
        "session.off_hours": "Fora do horário",
        "csv_upload": "CSV de ticks",
        "process_csv": "Processar CSV",
        "theme": "Tema",
        "theme.default": "Padrão",
        "theme.navy": "Azul-marinho",
        "theme.black": "Preto",
        "theme.graphite": "Grafite",
        "theme.emerald": "Esmeralda",
        "status.live": "🟢 AO VIVO",
        "status.live_stale": "🟡 AO VIVO (sem ticks)",
        "status.backtest": "🔴 BACKTEST",
        "status.idle": "⚪ OCIOSO",
        "status.live_line": "🟢 **AO VIVO** — recebendo ticks do NinjaTrader",
        "status.live_stale_line": "🟡 **AO VIVO (sem ticks)** — aguardando NinjaTrader / TCP",
        "status.backtest_line": "🔴 **BACKTEST** — modo CSV",
        "status.idle_line": "⚪ **OCIOSO** — engine não conectado",
        "signal.1": "VIÉS DE COMPRA",
        "signal.-1": "VIÉS DE VENDA",
        "signal.0": "NEUTRO — PAUSAR SINAL",
        "awaiting_signal": "AGUARDANDO SINAL",
        "tile.price": "Preço GC",
        "tile.session": "Sessão (ET)",
        "tile.regime": "Regime IA",
        "tile.paused": "Sinal pausado",
        "tile.thresholds": "Limiares",
        "yes": "SIM",
        "no": "NÃO",
        "yes_short": "S",
        "no_short": "N",
        "ticks_n": "{n} ticks",
        "source_line": "fonte: {source}",
        "source.default": "padrão",
        "source.manual": "manual",
        "source.ai": "IA",
        "source.lee_ready_flow": "fluxo Lee-Ready",
        "source.main_force": "Main Force",
        "mf_floor": "piso MF {n} cts",
        "brasilia": "Brasília",
        "regime.0": "Chop / baixa volatilidade",
        "regime.1": "Tendência forte / padrão",
        "regime.2": "Alta volatilidade / notícia",
        "info.waiting_close": "Recebendo ticks do NinjaTrader. O sinal composto aparece após o fechamento da primeira barra de 10m (e o alinhamento de 30m/1H).",
        "warn.no_ticks": "Sem ticks no estado. Confirme no Ninja: indicador GC Tick Publisher (TCP) com LISTENING e tps>0, e o engine Python em modo ao vivo.",
        "tab.op": "Operação",
        "tab.chart": "Gráficos",
        "tab.log": "Log de sinais",
        "mtf.title": "Análise Multi-Timeframe",
        "fp.timeframe": "Timeframe do footprint",
        "chart.title": "Preço GC (10m) + marcadores de sinal",
        "log.empty": "Sem sinais ainda.",
        "log.export": "Exportar log CSV",
        "footer": "Arquitetura: NinjaTrader (TCP :5556) → engine Python incremental → sinais ZMQ :5555 + painel. Estado: `{state}` · engine={engine}",
        "mtf.empty": "Sem dados MTF.",
        "side.buy": "COMPRA",
        "side.sell": "VENDA",
        "side.flat": "NEUTRO",
        "retail": "Varejo",
        "mf_delta": "MF Δ: {n} cts",
        "div.fallback": "Divergência MF vs varejo",
        "div.selling_accumulating": "DIVERGÊNCIA ({tf}): varejo vendendo, Main Force acumulando",
        "div.buying_distributing": "DIVERGÊNCIA ({tf}): varejo comprando, Main Force distribuindo",
        "div.suggestion": "Sugestão: considere pausar o sinal na direção da tendência.",
        "chart.no_bars": "Sem barras de 10m ainda",
        "chart.gc": "GC 10m",
        "chart.volume": "Volume",
        "chart.long": "COMPRA",
        "chart.short": "VENDA",
        "chart.neutral": "NEUTRO",
        "fp.chart_empty": "Sem footprint na última barra {tf}",
        "fp.hover": "${price}<br>Líquido: {net}<br>Compra: {buy} · Venda: {sell}",
        "fp.net": "Líquido {tf}",
        "fp.net_30": "Líquido 30m (contexto)",
        "fp.absorption": "Absorção ${price}{extra}",
        "fp.axis": "Main Force líquido (contratos)",
        "fp.heading": "🐉 Rastro Institucional — Footprint {tf}",
        "fp.bar_badge": "⏱ Barra de {tf}",
        "fp.manual": "leitura manual · baseada no footprint da barra de {tf} · não é ordem automática",
        "fp.title.wait_price": "Aguardando preço do Ninja",
        "fp.title.no_node": "⏸ SEM SINAL — AGUARDAR",
        "fp.title.buy_floor": "🟢 VIÉS DE COMPRA",
        "fp.title.sell_ceiling": "🔴 VIÉS DE VENDA",
        "fp.title.caution_buy": "⚠️ CAUTELA — não forçar compra",
        "fp.title.caution_sell": "⚠️ CAUTELA — não forçar venda",
        "fp.short.wait_price": "Sem último preço no estado — confira se o engine está recebendo ticks.",
        "fp.short.no_node": "Preço Ninja ${price}, mas ainda não há nó de absorção claro no footprint. Não force entrada manual.",
        "fp.short.buy_floor": "Chão institucional abaixo do mercado. Priorize compras nessa região.",
        "fp.short.sell_ceiling": "Teto institucional acima do mercado. Priorize vendas nessa região.",
        "fp.short.caution_buy": "O chão ficou acima do preço — risco de range. Não force compra.",
        "fp.short.caution_sell": "O teto ficou abaixo do preço. Evite vender agressivo.",
        "fp.tile.price": "Preço Ninja",
        "fp.tile.abs": "Absorção",
        "fp.tile.dist": "Distância",
        "fp.tile.dist_sub": "preço − absorção",
        "fp.tile.zone": "Zona sugerida",
        "fp.tile.zone_sub": "~3 ticks da absorção",
        "fp.tile.bar": "Barra",
        "fp.live": "AO VIVO",
        "fp.closed": "fechada",
        "fp.levels": "{n} níveis · lote máx {lot}",
        "fp.empty": "Footprint sem nós ainda. Aguarde ticks ou rode o backtest com o CSV de amostra.",
        "fp.rules_title": "Regras e filtros desta leitura",
        "fp.filter": "Filtro do footprint: {filt} · origem `{source}` · sinal MF com piso fixo ≥ {mf_fixed}",
        "fp.filt_mf": "MF ≥ {n}",
        "fp.filt_min": "≥ {n} cts",
        "fp.rules": (
            "| Comparação automática | Leitura para operação **manual** |\n"
            "|---|---|\n"
            "| Absorção **compra** (líquido +) **≤** preço Ninja | Viés de compra (chão abaixo) |\n"
            "| Absorção **venda** (líquido −) **≥** preço Ninja | Viés de venda (teto acima) |\n"
            "| Nó do lado errado em relação ao preço | Cautela — não forçar |\n"
            "| Sem nó / sem preço | Aguardar |\n\n"
            "Isso **não** dispara ordem. Cruze com o **sinal composto** (3 tempos) no topo do painel.\n"
            "Zona de entrada: **2–4 ticks** longe do nível de absorção."
        ),
        "metric.price": "Preço GC",
        "panel.composite": "SINAL COMPOSTO",
        "panel.conf": "Confiança: {conf}% · {ts}",
        "panel.wait": "Aguardando o primeiro sinal composto (fechamento de 10m).",
        "log.time": "Data/hora (BRT)",
        "log.signal": "Sinal",
        "log.conf": "Conf %",
        "log.div": "Divergência",
        "log.session": "Sessão",
    },
    "en": {
        "language": "Language",
        "lang.pt": "Português",
        "lang.en": "English",
        "sidebar.title": "Controls",
        "view_mode": "View mode",
        "mode.live": "Live (NinjaTrader / engine)",
        "mode.backtest": "Backtest (CSV)",
        "pause_live": "Pause live updates",
        "exp.thresholds": "Thresholds",
        "mf_min": "Main Force min contracts (GC)",
        "thr_1h": "1H threshold",
        "thr_30": "30m threshold",
        "thr_10": "10m threshold",
        "roll_h": "Percentile window (hours)",
        "exp.footprint": "Footprint",
        "show_fp": "Show Institutional Footprint (LHB)",
        "show_fp_help": "Price map of aggressive flow (Lee-Ready). The MF signal still uses the fixed threshold.",
        "exp.ai": "AI — Regime / kill switch",
        "ai_on": "Regime AI enabled",
        "force_regime": "Force regime manually",
        "regime_opt.auto": "auto",
        "regime_opt.0": "0 — Chop / low volatility",
        "regime_opt.1": "1 — Trend / standard",
        "regime_opt.2": "2 — High volatility / news",
        "pause_signal": "Pause signal (override)",
        "pause_signal_help": "Human kill switch: pauses the signal and new entries regardless of the AI.",
        "apply_ai": "Apply AI controls",
        "ai_saved": "Controls saved — applied on the next 1H close.",
        "session_filter": "Session filter",
        "session.all": "All",
        "session.asian": "Asia (18:00–01:00 ET)",
        "session.london": "London (01:00–08:00 ET)",
        "session.new_york": "New York (08:00–17:00 ET)",
        "session.off_hours": "Off hours",
        "csv_upload": "Tick CSV",
        "process_csv": "Process CSV",
        "theme": "Theme",
        "theme.default": "Default",
        "theme.navy": "Navy",
        "theme.black": "Black",
        "theme.graphite": "Graphite",
        "theme.emerald": "Emerald",
        "status.live": "🟢 LIVE",
        "status.live_stale": "🟡 LIVE (no ticks)",
        "status.backtest": "🔴 BACKTEST",
        "status.idle": "⚪ IDLE",
        "status.live_line": "🟢 **LIVE** — receiving NinjaTrader ticks",
        "status.live_stale_line": "🟡 **LIVE (no ticks)** — waiting for NinjaTrader / TCP",
        "status.backtest_line": "🔴 **BACKTEST** — CSV mode",
        "status.idle_line": "⚪ **IDLE** — engine not connected",
        "signal.1": "LONG BIAS",
        "signal.-1": "SHORT BIAS",
        "signal.0": "NEUTRAL — PAUSE SIGNAL",
        "awaiting_signal": "WAITING FOR SIGNAL",
        "tile.price": "GC price",
        "tile.session": "Session (ET)",
        "tile.regime": "AI regime",
        "tile.paused": "Signal paused",
        "tile.thresholds": "Thresholds",
        "yes": "YES",
        "no": "NO",
        "yes_short": "Y",
        "no_short": "N",
        "ticks_n": "{n} ticks",
        "source_line": "source: {source}",
        "source.default": "default",
        "source.manual": "manual",
        "source.ai": "AI",
        "source.lee_ready_flow": "Lee-Ready flow",
        "source.main_force": "Main Force",
        "mf_floor": "MF floor {n} cts",
        "brasilia": "Brasília",
        "regime.0": "Chop / low volatility",
        "regime.1": "Strong trend / standard",
        "regime.2": "High volatility / news",
        "info.waiting_close": "Receiving NinjaTrader ticks. The composite signal appears after the first 10m bar closes (and 30m/1H align).",
        "warn.no_ticks": "No ticks in state. In Ninja, confirm the GC Tick Publisher (TCP) indicator shows LISTENING and tps>0, and that the Python engine is in live mode.",
        "tab.op": "Trading",
        "tab.chart": "Charts",
        "tab.log": "Signal log",
        "mtf.title": "Multi-Timeframe Analysis",
        "fp.timeframe": "Footprint timeframe",
        "chart.title": "GC price (10m) + signal markers",
        "log.empty": "No signals yet.",
        "log.export": "Export log CSV",
        "footer": "Architecture: NinjaTrader (TCP :5556) → incremental Python engine → ZMQ signals :5555 + dashboard. State: `{state}` · engine={engine}",
        "mtf.empty": "No MTF data.",
        "side.buy": "BUY",
        "side.sell": "SELL",
        "side.flat": "FLAT",
        "retail": "Retail",
        "mf_delta": "MF Δ: {n} cts",
        "div.fallback": "MF vs retail divergence",
        "div.selling_accumulating": "DIVERGENCE ({tf}): Retail selling, Main Force accumulating",
        "div.buying_distributing": "DIVERGENCE ({tf}): Retail buying, Main Force distributing",
        "div.suggestion": "Suggestion: consider pausing the signal in the direction of the trend.",
        "chart.no_bars": "No 10m bars yet",
        "chart.gc": "GC 10m",
        "chart.volume": "Volume",
        "chart.long": "LONG",
        "chart.short": "SHORT",
        "chart.neutral": "FLAT",
        "fp.chart_empty": "No footprint on the latest {tf} bar",
        "fp.hover": "${price}<br>Net: {net}<br>Buy: {buy} · Sell: {sell}",
        "fp.net": "Net {tf}",
        "fp.net_30": "Net 30m (context)",
        "fp.absorption": "Absorption ${price}{extra}",
        "fp.axis": "Net Main Force (contracts)",
        "fp.heading": "🐉 Institutional Footprint — {tf}",
        "fp.bar_badge": "⏱ {tf} bar",
        "fp.manual": "manual read · based on the {tf} bar footprint · not an automatic order",
        "fp.title.wait_price": "Waiting for Ninja price",
        "fp.title.no_node": "⏸ NO SIGNAL — WAIT",
        "fp.title.buy_floor": "🟢 BUY BIAS",
        "fp.title.sell_ceiling": "🔴 SELL BIAS",
        "fp.title.caution_buy": "⚠️ CAUTION — do not force a buy",
        "fp.title.caution_sell": "⚠️ CAUTION — do not force a sell",
        "fp.short.wait_price": "No last price in state — check that the engine is receiving ticks.",
        "fp.short.no_node": "Ninja price ${price}, but there is no clear absorption node on the footprint yet. Do not force a manual entry.",
        "fp.short.buy_floor": "Institutional floor below the market. Favor buys in this area.",
        "fp.short.sell_ceiling": "Institutional ceiling above the market. Favor sells in this area.",
        "fp.short.caution_buy": "The floor is above price — range risk. Do not force a buy.",
        "fp.short.caution_sell": "The ceiling is below price. Avoid an aggressive sell.",
        "fp.tile.price": "Ninja price",
        "fp.tile.abs": "Absorption",
        "fp.tile.dist": "Distance",
        "fp.tile.dist_sub": "price − absorption",
        "fp.tile.zone": "Suggested zone",
        "fp.tile.zone_sub": "~3 ticks from absorption",
        "fp.tile.bar": "Bar",
        "fp.live": "LIVE",
        "fp.closed": "closed",
        "fp.levels": "{n} levels · max lot {lot}",
        "fp.empty": "Footprint has no nodes yet. Wait for ticks or run a backtest with the sample CSV.",
        "fp.rules_title": "Rules and filters for this read",
        "fp.filter": "Footprint filter: {filt} · source `{source}` · MF signal fixed floor ≥ {mf_fixed}",
        "fp.filt_mf": "MF ≥ {n}",
        "fp.filt_min": "≥ {n} cts",
        "fp.rules": (
            "| Automatic comparison | Read for **manual** trading |\n"
            "|---|---|\n"
            "| **Buy** absorption (net +) **≤** Ninja price | Buy bias (floor below) |\n"
            "| **Sell** absorption (net −) **≥** Ninja price | Sell bias (ceiling above) |\n"
            "| Node on the wrong side of price | Caution — do not force it |\n"
            "| No node / no price | Wait |\n\n"
            "This does **not** send an order. Cross it with the **composite signal** (3 timeframes) at the top of the panel.\n"
            "Entry zone: **2–4 ticks** away from the absorption level."
        ),
        "metric.price": "GC price",
        "panel.composite": "COMPOSITE SIGNAL",
        "panel.conf": "Confidence: {conf}% · {ts}",
        "panel.wait": "Waiting for the first composite signal (10m close).",
        "log.time": "Time (BRT)",
        "log.signal": "Signal",
        "log.conf": "Conf %",
        "log.div": "Divergence",
        "log.session": "Session",
    },
}

_REGIME_BY_EN = {
    "Chop / Low Volatility": "regime.0",
    "Strong Trend / Standard": "regime.1",
    "High Volatility / News": "regime.2",
}


def get_lang() -> str:
    lang = st.session_state.get("lang") or "pt"
    return lang if lang in STRINGS else "pt"


def t(key: str, **kwargs: object) -> str:
    lang = get_lang()
    text = STRINGS[lang].get(key) or STRINGS["pt"].get(key) or key
    if kwargs:
        return text.format(**kwargs)
    return text


def translate_divergence(message: str | None) -> str:
    raw = (message or "").strip()
    match = _DIV_RE.search(raw)
    if not match:
        return raw or t("div.fallback")
    tf, retail, mf = match.group(1), match.group(2), match.group(3)
    if retail == "selling" and mf == "accumulating":
        return t("div.selling_accumulating", tf=tf)
    if retail == "buying" and mf == "distributing":
        return t("div.buying_distributing", tf=tf)
    return raw or t("div.fallback")


def regime_label(label: object, regime_id: object = None) -> str:
    if regime_id is not None:
        key = f"regime.{regime_id}"
        if key in STRINGS["pt"]:
            return t(key)
    mapped = _REGIME_BY_EN.get(str(label or ""))
    if mapped:
        return t(mapped)
    text = str(label or "").strip()
    return text or "—"


def source_label(source: object) -> str:
    key = f"source.{source}"
    if key in STRINGS["pt"]:
        return t(key)
    text = str(source or "").strip()
    return text or "—"


def session_label(name: object) -> str:
    key = f"session.{name}"
    if key in STRINGS["pt"]:
        return t(key)
    text = str(name or "").strip()
    return text or "—"
