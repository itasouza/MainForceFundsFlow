# MainForceFundsFlow

## Sistema atual (recomendado): `gc_main_force/`

Uma fonte de ticks por vez → mesmo engine → mesmo painel:

| Fonte | Porta | Como ligar |
|-------|-------|------------|
| **NinjaTrader** (GC) | `:5556` | `--source ninjatrader --profile live_gc` |
| **Bookmap** (sim BTC ou live) | `:5558` | `--source bookmap --profile simulator_btc` |

- **Python** calcula Main Force Flow MTF e publica sinais (`:5555`)
- **Streamlit** dashboard (`:8501`)

👉 Guia NT: [`gc_main_force/README.md`](gc_main_force/README.md)  
👉 Guia Bookmap: [`gc_main_force/bookmap_addon/INSTALL_BOOKMAP.md`](gc_main_force/bookmap_addon/INSTALL_BOOKMAP.md)

```bash
cd gc_main_force
pip install -r requirements.txt

# NinjaTrader
python -m python_engine.main --mode live --source ninjatrader --profile live_gc

# Bookmap (simulador BTC no sábado)
python -m python_engine.main --mode live --source bookmap --profile simulator_btc

streamlit run dashboard/app.py
```

## Legado

A pasta `gold_mtf_flow/` contém a versão anterior (painel HTTP simples / MGC). Prefira `gc_main_force`.
