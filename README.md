# MainForceFundsFlow

## Sistema atual (recomendado): NinjaTrader GC + Python + Streamlit

A arquitetura principal está em **`gc_main_force/`**:

- **NinjaTrader 8** publica ticks GC via ZeroMQ (`:5556`)
- **Python** calcula Main Force Flow MTF e publica sinais (`:5555`)
- **Streamlit** dashboard em tempo real (`:8501`)

👉 Guia completo: [`gc_main_force/README.md`](gc_main_force/README.md)

```bash
cd gc_main_force
pip install -r requirements.txt
python tests/test_pipeline.py
python -m python_engine.main --mode live
streamlit run dashboard/app.py
```

## Legado

A pasta `gold_mtf_flow/` contém a versão anterior (painel HTTP simples / MGC). Prefira `gc_main_force` para GC + NinjaTrader.
