"""
Bookmap Python API add-on — publica trades em TCP JSON (mesmo contrato do NinjaTrader)
e desenha, no painel de preço, a abertura, máxima, mínima e fechamento dos dois
pregões já encerrados (ontem e o linhão).

Uso no Bookmap:
  1. Abra o instrumento (ex.: WDO com pelo menos dois pregões no gráfico).
  2. Python API → abra este script → Run.
  3. Ative o add-on no gráfico do instrumento.
  4. Engine: python -m python_engine.main --mode live --source bookmap --profile live_wdo

Formato (uma linha por tick):
  {"timestamp":"...Z","symbol":"...","price":...,"volume":...,"bid":...,"ask":...}
"""

from __future__ import annotations

import json
import re
import socket
import threading
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional

try:
    import bookmap as bm
except ImportError:  # fora do Bookmap dá para testar só o cálculo das velas
    bm = None  # type: ignore[assignment]

# Porta dedicada ao Bookmap (NT usa 5556).
TCP_HOST = "0.0.0.0"
TCP_PORT = 5558

# Fotos do book (para estudar faixas de liquidez); não passam pela porta do engine.
DEPTH_DIR = Path(r"C:\MainForceFundsFlow\gc_main_force\data_depth")
DEPTH_SNAPSHOT_SECONDS = 5.0
DEPTH_SNAPSHOT_LEVELS = 40  # níveis de preço para cada lado do meio

# Velas diárias do linhão. O trade do Bookmap não traz horário; o add-on recebe
# um on_interval a cada 100 ms de tempo do gráfico (INTERVAL_100_MILLISECONDS).
CHART_INTERVAL_MS = 100
REALTIME_GAP_MIN_S = 0.06
REALTIME_GAP_MAX_S = 0.30
REALTIME_STREAK = 50
MIN_CLOSED_SPAN = timedelta(minutes=60)
UNTIMED_BURST_TRADES = 2000
LINHAO_PATH = DEPTH_DIR / "linhao_sessions.json"
MAX_BOOK_SPREAD = 1.0  # foto do book com spread maior que isso nao entra na vela
_QUOTE_RE = re.compile(
    r'"timestamp":"([^"]+)","symbol":"[^"]*","bid":(-?\d+(?:\.\d+)?),"ask":(-?\d+(?:\.\d+)?)'
)

# Nome, campo OHLC, grupo, cor inicial, estilo. A cor o Bookmap pode trocar.
_LEVEL_SPECS: tuple[tuple[str, str, str, tuple[int, int, int], str], ...] = (
    ("Ontem fechamento", "close", "ontem", (255, 105, 180), "SOLID"),
    ("Ontem abertura", "open", "ontem", (148, 0, 211), "SOLID"),
    ("Ontem maxima", "high", "ontem", (220, 40, 40), "SOLID"),
    ("Ontem minima", "low", "ontem", (30, 120, 255), "SOLID"),
    ("Linhao fechamento", "close", "linhao", (255, 210, 0), "LONG_DASH"),
    ("Linhao abertura", "open", "linhao", (255, 210, 0), "LONG_DASH"),
    ("Linhao maxima", "high", "linhao", (255, 210, 0), "LONG_DASH"),
    ("Linhao minima", "low", "linhao", (255, 210, 0), "LONG_DASH"),
)

# Estado por instrumento (alias Bookmap)
_instruments: dict[str, dict[str, Any]] = {}
_level_requests: dict[int, tuple[str, str]] = {}  # req_id -> (alias, nome da linha)
_sessions_lock = threading.Lock()
_clients: list[socket.socket] = []
_clients_lock = threading.Lock()
_server_sock: Optional[socket.socket] = None
_req_id = 1
_ticks_sent = 0


def _next_req() -> int:
    global _req_id
    rid = _req_id
    _req_id += 1
    return rid


def _iso_utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def _broadcast(line: str) -> None:
    global _ticks_sent
    payload = line.encode("utf-8")
    dead: list[socket.socket] = []
    with _clients_lock:
        for client in _clients:
            try:
                client.sendall(payload)
            except OSError:
                dead.append(client)
        for client in dead:
            try:
                client.close()
            except OSError:
                pass
            if client in _clients:
                _clients.remove(client)
    if not dead or _clients:
        _ticks_sent += 1


def _accept_loop(stop: threading.Event) -> None:
    global _server_sock
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind((TCP_HOST, TCP_PORT))
    sock.listen(8)
    sock.settimeout(1.0)
    _server_sock = sock
    print(f"[bm_tick_publisher] LISTENING TCP {TCP_HOST}:{TCP_PORT}")
    while not stop.is_set():
        try:
            client, addr = sock.accept()
            client.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            with _clients_lock:
                _clients.append(client)
            print(f"[bm_tick_publisher] client connected {addr}")
        except socket.timeout:
            continue
        except OSError:
            break
    try:
        sock.close()
    except OSError:
        pass


def _derive_symbol(alias: str, full_name: str) -> str:
    """Nome do contrato para o engine, ex.: ESZ6.CME, GCZ6.COMEX, WDOX26.

    Alias típicos: "ESZ6.CME@RITHMIC", "WDOX26＠CC" (＠ fullwidth) ou "CC@WDOX26".
    Pega a primeira parte com dígito (contrato); sem isso, usa full_name.
    """
    parts = [
        p.strip()
        for p in (alias or "").replace("＠", "@").split("@")
        if p.strip()
    ]
    parts = [p.split(":")[0] for p in parts]
    symbol = next((p for p in parts if any(ch.isdigit() for ch in p)), "")
    if not symbol and full_name:
        symbol = full_name.replace("＠", "@").split("@")[0].split(":")[0].strip()
    if not symbol:
        symbol = parts[0] if parts else "BTC-USDT"
    return symbol.replace("/", "-")


def _session_tz() -> timezone:
    """Pregão pela data civil de São Paulo. O Brasil não usa horário de verão."""
    try:
        from zoneinfo import ZoneInfo

        return ZoneInfo("America/Sao_Paulo")  # type: ignore[return-value]
    except Exception:
        return timezone(timedelta(hours=-3))


def _empty_candle() -> dict[str, Any]:
    return {
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "n": 0,
        "first": None,
        "last": None,
        "source": None,
    }


def _apply_trade(candle: dict[str, Any], price: float, ts: datetime | None) -> None:
    px = round(float(price), 2)
    if candle["open"] is None:
        candle["open"] = px
        candle["high"] = px
        candle["low"] = px
        if ts is not None:
            candle["first"] = ts.isoformat()
    else:
        candle["high"] = max(float(candle["high"]), px)
        candle["low"] = min(float(candle["low"]), px)
    candle["close"] = px
    candle["n"] = int(candle.get("n") or 0) + 1
    if ts is not None:
        candle["last"] = ts.isoformat()


def _merge_bucket(dst: dict[str, Any], src: dict[str, Any], ts: datetime) -> None:
    """Junta um bloco de 100 ms numa vela diária, na ordem do tempo."""
    if src.get("open") is None:
        return
    if dst["open"] is None:
        dst["open"] = src["open"]
        dst["high"] = src["high"]
        dst["low"] = src["low"]
        dst["first"] = ts.isoformat()
    else:
        dst["high"] = max(float(dst["high"]), float(src["high"]))
        dst["low"] = min(float(dst["low"]), float(src["low"]))
    dst["close"] = src["close"]
    dst["n"] = int(dst.get("n") or 0) + int(src.get("n") or 0)
    dst["last"] = ts.isoformat()


def _span_ok(candle: dict[str, Any], minimum: timedelta = MIN_CLOSED_SPAN) -> bool:
    first = candle.get("first")
    last = candle.get("last")
    if not first or not last or candle.get("open") is None:
        return False
    try:
        start = datetime.fromisoformat(str(first))
        end = datetime.fromisoformat(str(last))
    except ValueError:
        return False
    return (end - start) >= minimum


def _combine_candles(old: dict[str, Any] | None, new: dict[str, Any]) -> dict[str, Any]:
    """Une duas leituras do mesmo dia. A abertura fica com o primeiro trade."""
    if not old or old.get("open") is None:
        return new
    if new.get("open") is None:
        return old
    first_old = str(old.get("first") or "")
    first_new = str(new.get("first") or "")
    last_old = str(old.get("last") or "")
    last_new = str(new.get("last") or "")
    out = _empty_candle()
    if first_new and (not first_old or first_new < first_old):
        out["open"] = new["open"]
        out["first"] = new["first"]
    else:
        out["open"] = old["open"]
        out["first"] = old["first"]
    out["high"] = max(float(old["high"]), float(new["high"]))
    out["low"] = min(float(old["low"]), float(new["low"]))
    if last_new >= last_old:
        out["close"] = new["close"]
        out["last"] = new["last"]
    else:
        out["close"] = old["close"]
        out["last"] = old["last"]
    out["n"] = int(old.get("n") or 0) + int(new.get("n") or 0)
    out["source"] = "live" if "live" in (old.get("source"), new.get("source")) else new.get("source")
    return out


def _rebuild_days_from_buckets(
    buckets: dict[int, dict[str, Any]],
    anchor: datetime,
    anchor_index: int,
) -> dict[str, dict[str, Any]]:
    """Converte o índice do intervalo de 100 ms em data civil de São Paulo."""
    tz = _session_tz()
    if anchor.tzinfo is None:
        anchor = anchor.replace(tzinfo=tz)
    days: dict[str, dict[str, Any]] = {}
    for index in sorted(buckets):
        ts = anchor - timedelta(milliseconds=CHART_INTERVAL_MS * (anchor_index - index))
        ts = ts.astimezone(tz)
        key = ts.date().isoformat()
        candle = days.setdefault(key, _empty_candle())
        _merge_bucket(candle, buckets[index], ts)
        candle["source"] = "replay"
    return days


def _closed_days(days: dict[str, dict[str, Any]], today: date) -> list[str]:
    keys: list[str] = []
    for key, candle in days.items():
        try:
            day = date.fromisoformat(key)
        except ValueError:
            continue
        if day < today and _span_ok(candle):
            keys.append(key)
    keys.sort()
    return keys


def _level_prices(
    days: dict[str, dict[str, Any]], today: date
) -> tuple[dict[str, float], str, str] | None:
    closed = _closed_days(days, today)
    if len(closed) < 2:
        return None
    yesterday_key = closed[-1]
    linhao_key = closed[-2]
    yesterday = days[yesterday_key]
    linhao = days[linhao_key]
    prices: dict[str, float] = {}
    for name, field, group, _color, _style in _LEVEL_SPECS:
        source = yesterday if group == "ontem" else linhao
        value = source.get(field)
        if value is None:
            return None
        prices[name] = round(float(value), 2)
    return prices, yesterday_key, linhao_key


def _empty_level_state() -> dict[str, Any]:
    return {
        "interval_index": 0,
        "last_interval_mono": None,
        "realtime_streak": 0,
        "saw_fast_interval": False,
        "clock_started": False,
        "trades_before_clock": 0,
        "history_done": False,
        "buckets": {},
        "days": {},
        "registered": False,
        "level_ids": {},
        "last_log_key": None,
        "missing_logged": False,
        "point_tick": 0,
        "dirty": False,
        "last_save_mono": 0.0,
    }


def _letter_prefix(symbol: str) -> str:
    chars: list[str] = []
    for ch in symbol:
        if ch.isalpha():
            chars.append(ch.upper())
        else:
            break
    return "".join(chars)


def _same_family(left: str, right: str) -> bool:
    """WDO-TM e WDOX26 sao o mesmo mini dolar. ESZ6 nao se mistura com WDO."""
    if left == right:
        return True
    a, b = _letter_prefix(left), _letter_prefix(right)
    if not a or not b:
        return False
    short, long = (a, b) if len(a) <= len(b) else (b, a)
    return len(short) >= 3 and long.startswith(short)


def _merge_arquivo(older: dict[str, Any], newer: dict[str, Any]) -> dict[str, Any]:
    first_old = str(older.get("first") or "")
    first_new = str(newer.get("first") or "")
    last_old = str(older.get("last") or "")
    last_new = str(newer.get("last") or "")
    out = _empty_candle()
    if first_new and (not first_old or first_new < first_old):
        out["open"] = newer["open"]
        out["first"] = newer["first"]
    else:
        out["open"] = older["open"]
        out["first"] = older["first"]
    out["high"] = max(float(older["high"]), float(newer["high"]))
    out["low"] = min(float(older["low"]), float(newer["low"]))
    if last_new >= last_old:
        out["close"] = newer["close"]
        out["last"] = newer["last"]
    else:
        out["close"] = older["close"]
        out["last"] = older["last"]
    out["n"] = int(older.get("n") or 0) + int(newer.get("n") or 0)
    out["source"] = "arquivo"
    return out


def _candles_from_depth(symbol: str) -> dict[str, dict[str, Any]]:
    """Velas diarias a partir das fotos do book ja gravadas, pela data de Sao Paulo.

    Cada arquivo e uma foto a cada 5 s (bid/ask), nao o negocio em si. Abertura e
    fechamento usam o bid; maxima o maior ask; minima o menor bid. Um book cruzado
    ou com spread largo fica de fora.
    """
    if not DEPTH_DIR.exists():
        return {}
    days: dict[str, dict[str, Any]] = {}
    tz = _session_tz()
    for path in sorted(DEPTH_DIR.glob("*_depth.jsonl")):
        match = re.match(r"(.+)_(\d{8})_depth\.jsonl$", path.name)
        if not match or not _same_family(match.group(1), symbol):
            continue
        file_days: dict[str, dict[str, Any]] = {}
        try:
            with path.open(encoding="utf-8") as handle:
                for line in handle:
                    found = _QUOTE_RE.search(line)
                    if not found:
                        continue
                    bid = float(found.group(2))
                    ask = float(found.group(3))
                    if bid <= 0 or ask < bid or (ask - bid) > MAX_BOOK_SPREAD:
                        continue
                    ts = datetime.fromisoformat(found.group(1).replace("Z", "+00:00")).astimezone(tz)
                    key = ts.date().isoformat()
                    candle = file_days.get(key)
                    if candle is None:
                        candle = _empty_candle()
                        candle["open"] = round(bid, 2)
                        candle["high"] = round(ask, 2)
                        candle["low"] = round(bid, 2)
                        candle["close"] = round(bid, 2)
                        candle["first"] = ts.isoformat()
                        candle["last"] = ts.isoformat()
                        candle["n"] = 1
                        candle["source"] = "arquivo"
                        file_days[key] = candle
                    else:
                        candle["high"] = max(float(candle["high"]), round(ask, 2))
                        candle["low"] = min(float(candle["low"]), round(bid, 2))
                        candle["close"] = round(bid, 2)
                        candle["last"] = ts.isoformat()
                        candle["n"] = int(candle["n"]) + 1
        except Exception as exc:
            print(f"[bm_tick_publisher] arquivo {path.name} ignorado: {exc}")
            continue
        for key, candle in file_days.items():
            previous = days.get(key)
            days[key] = candle if previous is None else _merge_arquivo(previous, candle)
    return days


def _seed_days(symbol: str) -> dict[str, dict[str, Any]]:
    """Arquivo ao vivo primeiro. Pregao que o add-on fechou em trade real prevalece."""
    days = _candles_from_depth(symbol)
    for key, candle in _load_sessions(symbol).items():
        if candle.get("source") == "live" or key not in days:
            days[key] = candle
    return days


def _arm_saved_lines(addon: Any, alias: str) -> None:
    meta = _instruments.get(alias)
    if not meta:
        return
    state = meta["levels"]
    symbol = meta.get("symbol") or alias
    today = datetime.now(_session_tz()).date()
    found = _level_prices(state["days"], today)
    if found is None:
        closed = _closed_days(state["days"], today)
        print(
            "[bm_tick_publisher] faltam duas velas diarias fechadas no arquivo ao vivo. "
            f"symbol={symbol} fechadas={closed}"
        )
        state["missing_logged"] = True
        return
    prices, yesterday, linhao = found
    _log_levels(symbol, prices, yesterday, linhao)
    state["last_log_key"] = (
        yesterday,
        linhao,
        tuple(prices[name] for name, *_rest in _LEVEL_SPECS),
    )
    state["missing_logged"] = False
    windows = ", ".join(
        f"{key} {state['days'][key].get('first')} -> {state['days'][key].get('last')}"
        for key in (linhao, yesterday)
    )
    print(f"[bm_tick_publisher] velas do arquivo ao vivo: {windows}")
    _ensure_indicators(addon, alias, prices)


def _load_sessions(symbol: str) -> dict[str, dict[str, Any]]:
    try:
        if not LINHAO_PATH.exists():
            return {}
        with _sessions_lock:
            raw = json.loads(LINHAO_PATH.read_text(encoding="utf-8"))
        stored = raw.get(symbol) if isinstance(raw, dict) else None
        if not isinstance(stored, dict):
            return {}
        days: dict[str, dict[str, Any]] = {}
        for key, candle in stored.items():
            if isinstance(candle, dict) and candle.get("open") is not None:
                days[str(key)] = dict(candle)
        return days
    except Exception as exc:
        print(f"[bm_tick_publisher] leitura das velas falhou: {exc}")
        return {}


def _save_sessions(symbol: str, days: dict[str, dict[str, Any]]) -> None:
    try:
        with _sessions_lock:
            raw: dict[str, Any] = {}
            if LINHAO_PATH.exists():
                loaded = json.loads(LINHAO_PATH.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    raw = loaded
            raw[symbol] = days
            LINHAO_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp = LINHAO_PATH.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
            tmp.replace(LINHAO_PATH)
    except Exception as exc:
        print(f"[bm_tick_publisher] gravacao das velas falhou: {exc}")


def _note_trade(alias: str, price: float) -> None:
    meta = _instruments.get(alias)
    if not meta or price <= 0:
        return
    state = meta["levels"]
    if not state["history_done"]:
        buckets: dict[int, dict[str, Any]] = state["buckets"]
        index = int(state["interval_index"])
        bucket = buckets.setdefault(index, _empty_candle())
        _apply_trade(bucket, price, None)
        if not state["clock_started"]:
            state["trades_before_clock"] = int(state["trades_before_clock"]) + 1
        return
    now = datetime.now(_session_tz())
    key = now.date().isoformat()
    candle = state["days"].setdefault(key, _empty_candle())
    _apply_trade(candle, price, now)
    candle["source"] = "live"
    state["dirty"] = True


def _finalize_history(alias: str) -> None:
    meta = _instruments.get(alias)
    if not meta:
        return
    state = meta["levels"]
    if state["history_done"]:
        return
    buckets: dict[int, dict[str, Any]] = state["buckets"]
    dropped = False
    first = buckets.get(0)
    untimed = int(state["trades_before_clock"]) >= 30 and not state["saw_fast_interval"]
    burst = first is not None and int(first.get("n") or 0) >= UNTIMED_BURST_TRADES and len(buckets) > 10
    if untimed or burst:
        buckets.pop(0, None)
        dropped = True
    anchor = datetime.now(_session_tz())
    rebuilt = _rebuild_days_from_buckets(buckets, anchor, int(state["interval_index"]))
    today = anchor.date()
    for key, candle in rebuilt.items():
        try:
            day = date.fromisoformat(key)
        except ValueError:
            continue
        previous = state["days"].get(key)
        if day < today:
            if not _span_ok(candle):
                continue
            if previous and previous.get("source") in ("live", "arquivo"):
                continue
            state["days"][key] = candle
        else:
            state["days"][key] = _combine_candles(previous, candle)
    state["buckets"] = {}
    state["history_done"] = True
    state["dirty"] = False
    symbol = meta.get("symbol") or alias
    _save_sessions(symbol, state["days"])
    if dropped:
        print(
            "[bm_tick_publisher] historico chegou sem horario de pregao; "
            f"esse bloco nao entrou nas velas. symbol={symbol}"
        )
    closed = _closed_days(state["days"], today)
    if len(closed) < 2:
        print(
            "[bm_tick_publisher] faltam duas velas diarias fechadas "
            f"(America/Sao_Paulo). Linhas ainda nao desenhadas. symbol={symbol} "
            f"fechadas={closed}"
        )
        state["missing_logged"] = True
    else:
        windows = ", ".join(
            f"{key} {state['days'][key].get('first')} -> {state['days'][key].get('last')}"
            for key in closed[-2:]
        )
        print(f"[bm_tick_publisher] velas do grafico: {windows}")


def _log_levels(symbol: str, prices: dict[str, float], yesterday: str, linhao: str) -> None:
    def _fmt(group: str) -> str:
        names = [name for name, _field, grp, _c, _s in _LEVEL_SPECS if grp == group]
        return " ".join(f"{name.split()[-1]}={prices[name]:.2f}" for name in names)

    print(
        f"[bm_tick_publisher] linhas symbol={symbol} "
        f"ontem={yesterday} {_fmt('ontem')} | linhao={linhao} {_fmt('linhao')}"
    )


def _ensure_indicators(addon: Any, alias: str, prices: dict[str, float]) -> None:
    if bm is None:
        return
    meta = _instruments.get(alias)
    if not meta:
        return
    state = meta["levels"]
    if state["registered"]:
        return
    for name, _field, _group, color, style in _LEVEL_SPECS:
        req_id = _next_req()
        _level_requests[req_id] = (alias, name)
        bm.register_indicator(
            addon,
            alias,
            req_id,
            name,
            "PRIMARY",
            color=color,
            line_style=style,
            initial_value=float(prices[name]),
            show_line_by_default=True,
        )
    state["registered"] = True


def _publish_levels(addon: Any, alias: str) -> None:
    meta = _instruments.get(alias)
    if not meta or bm is None:
        return
    state = meta["levels"]
    today = datetime.now(_session_tz()).date()
    found = _level_prices(state["days"], today)
    symbol = meta.get("symbol") or alias
    if found is None:
        if not state["missing_logged"]:
            closed = _closed_days(state["days"], today)
            print(
                "[bm_tick_publisher] faltam duas velas diarias fechadas "
                f"(America/Sao_Paulo). Linhas ainda nao desenhadas. symbol={symbol} "
                f"fechadas={closed}"
            )
            state["missing_logged"] = True
        return
    prices, yesterday, linhao = found
    state["missing_logged"] = False
    log_key = (yesterday, linhao, tuple(prices[name] for name, *_rest in _LEVEL_SPECS))
    if log_key != state["last_log_key"]:
        _log_levels(symbol, prices, yesterday, linhao)
        state["last_log_key"] = log_key
    _ensure_indicators(addon, alias, prices)
    for name, _field, _group, _color, _style in _LEVEL_SPECS:
        indicator_id = state["level_ids"].get(name)
        if indicator_id is None:
            continue
        bm.add_point(addon, alias, int(indicator_id), float(prices[name]))


def _handle_indicator_response(addon: Any, request_id: int, indicator_id: int) -> None:
    try:
        found = _level_requests.get(int(request_id))
        if not found:
            return
        alias, name = found
        meta = _instruments.get(alias)
        if not meta:
            return
        meta["levels"]["level_ids"][name] = int(indicator_id)
        if len(meta["levels"]["level_ids"]) >= len(_LEVEL_SPECS):
            _publish_levels(addon, alias)
    except Exception as exc:
        print(f"[bm_tick_publisher] resposta do indicador falhou: {exc}")


def handle_subscribe_instrument(
    addon: Any,
    alias: str,
    full_name: str,
    is_crypto: bool,
    pips: float,
    size_multiplier: float,
    instrument_multiplier: float,
    supported_features: dict[str, Any],
) -> None:
    """Chamado quando o add-on é ativado no gráfico."""
    _instruments[alias] = {
        "full_name": full_name,
        "symbol": _derive_symbol(alias, full_name),
        "pips": float(pips),
        "size_multiplier": float(size_multiplier) if size_multiplier else 1.0,
        "is_crypto": bool(is_crypto),
        "best_bid": None,
        "best_ask": None,
        "bids": {},  # price_level -> size_level
        "asks": {},
        "levels": _empty_level_state(),
    }
    symbol = _instruments[alias]["symbol"]
    try:
        _instruments[alias]["levels"]["days"] = _seed_days(symbol)
        _arm_saved_lines(addon, alias)
    except Exception as exc:
        print(f"[bm_tick_publisher] velas do arquivo falharam: {exc}")
    # Trades + depth (para BBO / Lee-Ready)
    bm.subscribe_to_trades(addon, alias, _next_req())
    bm.subscribe_to_depth(addon, alias, _next_req())
    print(
        f"[bm_tick_publisher] subscribe alias={alias!r} full_name={full_name!r} "
        f"symbol={_instruments[alias]['symbol']!r} pips={pips}"
    )


def handle_unsubscribe_instrument(addon: Any, alias: str) -> None:
    meta = _instruments.pop(alias, None)
    if meta:
        try:
            symbol = meta.get("symbol") or alias
            days = meta.get("levels", {}).get("days") or {}
            if days:
                _save_sessions(symbol, days)
        except Exception as exc:
            print(f"[bm_tick_publisher] salvar velas no unsubscribe falhou: {exc}")
    print(f"[bm_tick_publisher] unsubscribe {alias}")


def handle_depth(
    addon: Any,
    alias: str,
    is_bid: bool,
    price_level: int,
    size_level: int,
) -> None:
    meta = _instruments.get(alias)
    if not meta:
        return
    book = meta["bids"] if is_bid else meta["asks"]
    if size_level <= 0:
        book.pop(price_level, None)
    else:
        book[price_level] = size_level
    pips = meta["pips"]
    if meta["bids"]:
        meta["best_bid"] = max(meta["bids"].keys()) * pips
    if meta["asks"]:
        meta["best_ask"] = min(meta["asks"].keys()) * pips


def handle_trades(
    addon: Any,
    alias: str,
    price_level: float,
    size_level: int,
    is_otc: bool,
    is_bid: bool,
    is_execution_start: bool,
    is_execution_end: bool,
    aggressor_order_id: Optional[str],
    passive_order_id: Optional[str],
) -> None:
    meta = _instruments.get(alias)
    if not meta:
        return
    pips = float(meta["pips"])
    size_mult = float(meta["size_multiplier"]) or 1.0
    # Bookmap: price_level * pips; size_level / size_multiplier
    price = float(price_level) * pips
    volume = float(size_level) / size_mult
    if volume <= 0:
        return

    bid = meta.get("best_bid")
    ask = meta.get("best_ask")
    # Fallback: sintetiza BBO a partir do lado do agresssor (Lee-Ready no engine)
    if bid is None or ask is None:
        if is_bid:  # compra (agressor no ask)
            ask = price
            bid = price - pips
        else:
            bid = price
            ask = price + pips

    symbol = meta.get("symbol") or _derive_symbol(alias, meta.get("full_name", ""))

    line = (
        json.dumps(
            {
                "timestamp": _iso_utc_now(),
                "symbol": symbol,
                "price": round(price, 8),
                "volume": round(volume, 8),
                "bid": round(float(bid), 8),
                "ask": round(float(ask), 8),
            },
            separators=(",", ":"),
        )
        + "\n"
    )
    _broadcast(line)
    try:
        _note_trade(alias, price)
    except Exception as exc:
        print(f"[bm_tick_publisher] vela diaria falhou: {exc}")


def on_interval(addon: Any, alias: str) -> None:
    """Relógio do gráfico: 100 ms. Não pode derrubar o publisher de ticks."""
    try:
        meta = _instruments.get(alias)
        if not meta:
            return
        state = meta["levels"]
        now_mono = time.perf_counter()
        previous = state["last_interval_mono"]
        state["clock_started"] = True
        is_realtime = False
        if previous is not None:
            gap = now_mono - float(previous)
            if gap < REALTIME_GAP_MIN_S:
                state["saw_fast_interval"] = True
                state["realtime_streak"] = 0
            elif gap <= REALTIME_GAP_MAX_S:
                state["realtime_streak"] = int(state["realtime_streak"]) + 1
                is_realtime = True
            else:
                state["realtime_streak"] = 0
        state["last_interval_mono"] = now_mono
        state["interval_index"] = int(state["interval_index"]) + 1

        just_finalized = False
        if not state["history_done"] and int(state["realtime_streak"]) >= REALTIME_STREAK:
            _finalize_history(alias)
            just_finalized = True

        state["point_tick"] = int(state["point_tick"]) + 1
        # O arquivo ao vivo ja tem os pregões fechados: a linha sai no ao vivo,
        # sem esperar o grafico carregar dois dias.
        if (state["history_done"] or is_realtime) and (
            just_finalized or int(state["point_tick"]) % 10 == 0
        ):
            _publish_levels(addon, alias)

        if state["dirty"] and (now_mono - float(state["last_save_mono"])) >= 30.0:
            symbol = meta.get("symbol") or alias
            _save_sessions(symbol, state["days"])
            state["dirty"] = False
            state["last_save_mono"] = now_mono
    except Exception as exc:
        print(f"[bm_tick_publisher] linhas do linhao falharam: {exc}")


def _write_depth_snapshots() -> None:
    """Foto do book (níveis perto do preço) em JSONL, separada do fluxo de ticks do engine."""
    now = _iso_utc_now()
    for alias, meta in list(_instruments.items()):
        try:
            pips = float(meta["pips"])
            size_mult = float(meta["size_multiplier"]) or 1.0
            bids = list(meta["bids"].items())
            asks = list(meta["asks"].items())
            best_bid = meta.get("best_bid")
            best_ask = meta.get("best_ask")
            if not bids or not asks or best_bid is None or best_ask is None:
                continue
            mid_level = (best_bid + best_ask) / 2.0 / pips
            lo, hi = mid_level - DEPTH_SNAPSHOT_LEVELS, mid_level + DEPTH_SNAPSHOT_LEVELS
            rec = {
                "timestamp": now,
                "symbol": meta.get("symbol") or _derive_symbol(alias, meta.get("full_name", "")),
                "bid": round(best_bid, 8),
                "ask": round(best_ask, 8),
                "bids": [[round(p * pips, 8), round(s / size_mult, 4)] for p, s in bids if lo <= p <= hi],
                "asks": [[round(p * pips, 8), round(s / size_mult, 4)] for p, s in asks if lo <= p <= hi],
            }
            DEPTH_DIR.mkdir(parents=True, exist_ok=True)
            day = datetime.now(timezone.utc).strftime("%Y%m%d")
            path = DEPTH_DIR / f"{rec['symbol']}_{day}_depth.jsonl"
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
        except Exception as exc:  # nunca derruba o publisher de ticks
            print(f"[bm_tick_publisher] depth snapshot falhou: {exc}")


def main() -> None:
    stop = threading.Event()
    acceptor = threading.Thread(target=_accept_loop, args=(stop,), daemon=True)
    acceptor.start()

    addon = bm.create_addon()
    bm.add_depth_handler(addon, handle_depth)
    bm.add_trades_handler(addon, handle_trades)
    bm.add_on_interval_handler(addon, on_interval)
    bm.add_indicator_response_handler(addon, _handle_indicator_response)
    bm.start_addon(addon, handle_subscribe_instrument, handle_unsubscribe_instrument)
    print(
        "[bm_tick_publisher] running — ative o add-on no gráfico Bookmap. "
        f"Engine: --source bookmap (tcp://localhost:{TCP_PORT})"
    )
    try:
        # Mantém o script vivo; Bookmap dirige os callbacks
        while True:
            time.sleep(DEPTH_SNAPSHOT_SECONDS)
            _write_depth_snapshots()
            with _clients_lock:
                n_cli = len(_clients)
            if _ticks_sent and _ticks_sent % 500 == 0:
                print(f"[bm_tick_publisher] ticks_sent={_ticks_sent} clients={n_cli}")
    except KeyboardInterrupt:
        pass
    finally:
        stop.set()
        with _clients_lock:
            for c in list(_clients):
                try:
                    c.close()
                except OSError:
                    pass
            _clients.clear()


if __name__ == "__main__":
    main()
