"""Standalone signal panel (web UI) — independent of MQL5 EA."""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from pathlib import Path

import pandas as pd

from gold_mtf_flow.config import apply_contract_defaults
from gold_mtf_flow.main import _generate_demo_ticks, process_and_publish
from gold_mtf_flow.panel_server import PanelServer
from gold_mtf_flow.signal_state import SignalStateStore
from gold_mtf_flow.zmq_subscriber import FlowSubscriber, run_subscriber_loop


def _engine_worker(
    ticks: pd.DataFrame,
    cfg: dict,
    store: SignalStateStore,
    replay_delay: float,
    stop_event: threading.Event,
) -> None:
    """Compute signals from ticks and push into the panel store."""
    payloads = process_and_publish(ticks, cfg, publisher=None)
    if not payloads:
        return
    for payload in payloads:
        if stop_event.is_set():
            break
        store.push(payload, "motor_python")
        if replay_delay > 0:
            time.sleep(replay_delay)
    # Keep last state visible after replay finishes
    store.push(payloads[-1], "motor_python")


def _zmq_worker(cfg: dict, store: SignalStateStore, stop_event: threading.Event) -> None:
    sub = FlowSubscriber(
        host=str(cfg["zmq_host"]),
        port=int(cfg["zmq_port"]),
    )
    try:
        def on_msg(p: dict) -> None:
            store.push(p, "zeromq")

        run_subscriber_loop(sub, on_msg, stop_event)
    finally:
        sub.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Painel web de sinais MTF (independente do EA MQL5)",
    )
    src = parser.add_mutually_exclusive_group(required=True)
    src.add_argument("--zmq", action="store_true", help="Ouvir publisher ZeroMQ (main.py)")
    src.add_argument("--demo", action="store_true", help="Motor interno com ticks sintéticos")
    src.add_argument("--csv", type=Path, help="Motor interno com CSV de ticks")
    parser.add_argument(
        "--replay-delay",
        type=float,
        default=0.0,
        help="Segundos entre atualizações no modo motor (0 = instantâneo)",
    )
    parser.add_argument("--host", default=None, help="Host do painel HTTP (padrão 127.0.0.1)")
    parser.add_argument("--port", type=int, default=None, help="Porta do painel (padrão 8765)")
    parser.add_argument("--no-browser", action="store_true", help="Não abrir navegador automaticamente")
    args = parser.parse_args()

    cfg = apply_contract_defaults()
    panel_host = args.host or str(cfg.get("panel_host", "127.0.0.1"))
    panel_port = args.port or int(cfg.get("panel_port", 8765))

    store = SignalStateStore()
    server = PanelServer(store, cfg, panel_host, panel_port)
    server.start()

    stop_event = threading.Event()
    workers: list[threading.Thread] = []

    if args.zmq:
        t = threading.Thread(
            target=_zmq_worker,
            args=(cfg, store, stop_event),
            daemon=True,
        )
        t.start()
        workers.append(t)
        mode = f"ZMQ → {cfg['zmq_host']}:{cfg['zmq_port']}"
    else:
        if args.csv:
            ticks = pd.read_csv(args.csv)
            mode = f"CSV → {args.csv}"
        else:
            ticks = _generate_demo_ticks()
            mode = "Demo sintético"
        t = threading.Thread(
            target=_engine_worker,
            args=(ticks, cfg, store, args.replay_delay, stop_event),
            daemon=True,
        )
        t.start()
        workers.append(t)

    url = server.url
    print(f"Painel: {url}")
    print(f"Modo: {mode}")
    print("Feche com Ctrl+C.")

    if not args.no_browser:
        webbrowser.open(url)

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        stop_event.set()
        server.stop()
        print("\nPainel encerrado.")


if __name__ == "__main__":
    main()
