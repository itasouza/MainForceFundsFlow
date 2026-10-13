# GC Main Force Flow — NinjaTrader 8 + Python + Streamlit

Sistema em tempo real para **Gold Futures (CME GC, 100 oz)**:

```
NinjaTrader 8 (ticks)  --ZMQ:5556-->  Python Engine  --ZMQ:5555-->  NT Strategy / consumers
                                         |
                                         +--> Streamlit Dashboard (:8501)
```

## Estrutura

```
gc_main_force/
├── ninjatrader_addon/
│   ├── GcTickPublisher.cs
│   └── INSTALL_INSTRUCTIONS.md
├── python_engine/
│   ├── config.py
│   ├── tick_receiver.py
│   ├── tick_processor.py
│   ├── mtf_aggregator.py
│   ├── signal_engine.py
│   ├── zmq_signal_publisher.py
│   ├── state_store.py
│   └── main.py
├── dashboard/
│   ├── app.py
│   └── components.py
├── backtest/
│   ├── run_backtest.py
│   └── sample_data/
├── tests/
│   └── test_pipeline.py
├── requirements.txt
└── README.md
```

## Thresholds GC (100 oz)

| Parâmetro | GC | Nota |
|-----------|-----|------|
| `mf_fixed_threshold_contracts` | **10** | ~1.000 oz notional institucional |
| Percentil dinâmico | top 10% (24h) | **AND** com o piso fixo |
| Símbolo | `GC` | NinjaTrader |

## Instalação Python

```bash
cd gc_main_force
pip install -r requirements.txt
```

## Passo 1 — Add-on NinjaTrader (recomendado: ZMQ + fila)

Siga `ninjatrader_addon/INSTALL_INSTRUCTIONS.md`:

1. Instale **NetMQ** + **AsyncIO** no Custom (DLL + References).
2. Copie `GcTickPublisher.cs` → `Documentos\NinjaTrader 8\bin\Custom\AddOns\`
3. Compile (F5). Abra **New → GC Tick Publisher ZMQ**.
4. Confirme **CONNECTED (PUB)**, `Published/sec` > 0, porta `5556`, tópico `gc_ticks`.
5. Python: `"nt_tick_transport": "zmq"` em `config.py`.

Fallback sem NetMQ: indicador `GcTickPublisherIndicator.cs` + `"nt_tick_transport": "tcp"`.

## Passo 2 — Engine Python (live)

```bash
cd gc_main_force
python -m python_engine.main --mode live
```

Por padrão usa o **engine incremental** (`live_engine: incremental` em `config.py`):
- **O(1)** por tick (sem reprocessar o buffer inteiro)
- Disco: heartbeat ~5s + gravação completa a cada **fechamento 10m**
- Fallback legado: `"live_engine": "batch"`

- SUB ticks: `tcp://localhost:5556`
- PUB sinais: `tcp://*:5555` (tópico `gold_mtf_flow`)
- Estado compartilhado: `signal_state.json`

## Passo 3 — Dashboard Streamlit

Em outro terminal:

```bash
cd gc_main_force
streamlit run dashboard/app.py --server.port 8501
```

Abra http://localhost:8501

O dashboard lê `signal_state.json` (escrito pelo engine) e também permite **Backtest Mode** com upload de CSV.

## Passo 4 — Testar sem NinjaTrader

```bash
cd gc_main_force
python tests/test_pipeline.py
```

Isso gera `backtest/sample_data/gc_ticks_sample.csv`, valida Lee-Ready/MF/MTF e ZeroMQ.

Backtest CLI:

```bash
python -m python_engine.main --mode backtest --csv backtest/sample_data/gc_ticks_sample.csv
python -m backtest.run_backtest backtest/sample_data/gc_ticks_sample.csv --output results.csv
```

Dashboard em backtest: selecione **Backtest Mode (CSV)** → upload → **Processar CSV**.

## Formato CSV

```csv
timestamp,price,volume,bid,ask
2026-10-13T14:32:01.123Z,2675.40,5,2675.30,2675.50
2026-10-13T14:32:01.450Z,2675.50,12,2675.40,2675.60
```

Timestamps em UTC. `bid`/`ask` opcionais (melhoram Lee-Ready).

## Payload de sinal (a cada fechamento 10m)

```json
{
  "timestamp": "2026-10-13T14:10:00Z",
  "symbol": "GC",
  "price": 2675.40,
  "timeframes": {
    "10m": {"mf_delta_norm": 0.45, "retail_delta_norm": -0.10, "mf_delta": 1250},
    "30m": {"mf_delta_norm": 0.32, "retail_delta_norm": 0.05, "mf_delta": 3200},
    "1H":  {"mf_delta_norm": 0.28, "retail_delta_norm": 0.12, "mf_delta": 8500}
  },
  "composite_signal": 1,
  "confidence_score": 0.85,
  "divergence_detected": false
}
```

- `1` = LONG bias para grid  
- `-1` = SHORT bias  
- `0` = NEUTRO — pausar novas entradas  

## Sessões (ET)

| Sessão | Horário ET |
|--------|------------|
| Asian | 18:00 – 01:00 |
| London | 01:00 – 08:00 |
| New York | 08:00 – 17:00 |

## Troubleshooting

| Problema | Ação |
|----------|------|
| Dashboard IDLE | Rode `python -m python_engine.main --mode live` (ou backtest) |
| LIVE sem ticks | Add-on NT conectado? Porta 5556 livre? Tópico `gc_ticks`? |
| Bind address in use | Encerre outro PUB na 5555/5556 |
| NetMQ compile error | NuGet NetMQ no `NinjaTrader.Custom.csproj` |
| Timezone barras | Engine força UTC; barras alinhadas ao relógio (:00/:10/:30) |

## Próximo passo

Criar a **NinjaScript Strategy** que assina `tcp://localhost:5555` e usa `composite_signal` para habilitar direção do grid (só compras / só vendas / pausa).
