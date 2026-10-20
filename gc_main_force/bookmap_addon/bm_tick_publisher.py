"""
Bookmap Python API add-on — publica trades em TCP JSON (mesmo contrato do NinjaTrader).

Uso no Bookmap:
  1. Abra o instrumento (ex.: BTC-USDT no simulador).
  2. Python API → cole / abra este script → Run.
  3. Ative o add-on no gráfico do instrumento.
  4. Engine: python -m python_engine.main --mode live --source bookmap --profile simulator_btc

Formato (uma linha por tick):
  {"timestamp":"...Z","symbol":"...","price":...,"volume":...,"bid":...,"ask":...}
"""

from __future__ import annotations

import json
import socket
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import bookmap as bm

# Porta dedicada ao Bookmap (NT usa 5556).
TCP_HOST = "0.0.0.0"
TCP_PORT = 5558

# Fotos do book (para estudar faixas de liquidez); não passam pela porta do engine.
DEPTH_DIR = Path(r"C:\MainForceFundsFlow\gc_main_force\data_depth")
DEPTH_SNAPSHOT_SECONDS = 5.0
DEPTH_SNAPSHOT_LEVELS = 40  # níveis de preço para cada lado do meio

# Estado por instrumento (alias Bookmap)
_instruments: dict[str, dict[str, Any]] = {}
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
    }
    # Trades + depth (para BBO / Lee-Ready)
    bm.subscribe_to_trades(addon, alias, _next_req())
    bm.subscribe_to_depth(addon, alias, _next_req())
    print(
        f"[bm_tick_publisher] subscribe alias={alias!r} full_name={full_name!r} "
        f"symbol={_instruments[alias]['symbol']!r} pips={pips}"
    )


def handle_unsubscribe_instrument(addon: Any, alias: str) -> None:
    _instruments.pop(alias, None)
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


def on_interval(addon: Any, alias: str) -> None:
    # Status leve a cada ~0.1s * N — só log periódico via contador
    pass


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
