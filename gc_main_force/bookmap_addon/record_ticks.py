"""
Grava os ticks do bm_tick_publisher (TCP :5558) em JSONL, um arquivo por dia.

Uso:
  python bookmap_addon/record_ticks.py [--host 127.0.0.1] [--port 5558] [--out data_ticks]

Reconecta sozinho se o publisher cair. Pode rodar junto com o engine (o publisher aceita vários clientes).
Saída: <out>/<SYMBOL>_<YYYYMMDD>.jsonl, a mesma linha JSON que o engine recebe.
"""

from __future__ import annotations

import argparse
import json
import socket
import time
from datetime import datetime, timezone
from pathlib import Path


def _open_out(out_dir: Path, symbol: str, day: str):
    out_dir.mkdir(parents=True, exist_ok=True)
    return open(out_dir / f"{symbol}_{day}.jsonl", "a", encoding="utf-8", buffering=1)


def record(host: str, port: int, out_dir: Path) -> None:
    files: dict[tuple[str, str], object] = {}
    total = 0
    while True:
        try:
            sock = socket.create_connection((host, port), timeout=10)
        except OSError as exc:
            print(f"[record_ticks] sem conexão ({exc}); nova tentativa em 5s")
            time.sleep(5)
            continue
        print(f"[record_ticks] conectado a {host}:{port}, gravando em {out_dir.resolve()}")
        sock.settimeout(60)
        buf = b""
        try:
            while True:
                chunk = sock.recv(65536)
                if not chunk:
                    break
                buf += chunk
                *lines, buf = buf.split(b"\n")
                for raw in lines:
                    if not raw.strip():
                        continue
                    try:
                        tick = json.loads(raw)
                    except ValueError:
                        continue
                    symbol = str(tick.get("symbol", "UNKNOWN"))
                    day = datetime.now(timezone.utc).strftime("%Y%m%d")
                    key = (symbol, day)
                    if key not in files:
                        files[key] = _open_out(out_dir, symbol, day)
                    files[key].write(raw.decode("utf-8").strip() + "\n")
                    total += 1
                    if total % 5000 == 0:
                        print(f"[record_ticks] {total} ticks gravados")
        except (OSError, socket.timeout) as exc:
            print(f"[record_ticks] conexão perdida ({exc}); reconectando")
        finally:
            sock.close()
        time.sleep(3)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5558)
    parser.add_argument("--out", default="data_ticks")
    args = parser.parse_args()
    try:
        record(args.host, args.port, Path(args.out))
    except KeyboardInterrupt:
        print("[record_ticks] encerrado")


if __name__ == "__main__":
    main()
