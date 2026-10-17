# Bookmap → GC Main Force Flow

Publica ticks do Bookmap no **mesmo formato JSON** do NinjaTrader. O engine e o painel não mudam.

```
Bookmap (sim BTC ou live) → TCP :5558 → Python engine → Streamlit :8501
```

## Requisitos

- Bookmap instalado (ex.: `F:\Bookmap`)
- **Python API** já instalada: Settings → Manage plugins → Bookmap Add-ons (L1)
- Python 3.7+ no Windows
- Pacote `bookmap` (vem com a API / plugin)

## Passo a passo (simulador BTC no sábado)

1. Abra o Bookmap e conecte o **simulador** com **BTC-USDT** (ou o par que estiver usando).
2. Abra o gráfico desse instrumento.
3. Abra o editor da **Python API** no Bookmap.
4. Carregue / cole o script:
   `gc_main_force/bookmap_addon/bm_tick_publisher.py`
5. **Run** o script. Deve aparecer: `LISTENING TCP 0.0.0.0:5558`
6. **Ative o add-on** no gráfico do instrumento (senão não chega trade).
7. Em outro terminal:

```bash
cd gc_main_force
python -m python_engine.main --mode live --source bookmap --profile simulator_btc
```

8. Painel:

```bash
streamlit run dashboard/app.py --server.port 8501
```

Quando o tape do Bookmap se mover, o painel deve sair de IDLE / tick_count subir.

## Depois (plano de dados ao vivo)

1. No Bookmap, troque a conexão do simulador para o feed live.
2. Abra o símbolo desejado (GC, BTC, etc.).
3. Rode o **mesmo** `bm_tick_publisher.py`.
4. No engine, troque o perfil:

```bash
# Exemplo GC ao vivo via Bookmap
python -m python_engine.main --mode live --source bookmap --profile live_gc

# Ou continue no NinjaTrader
python -m python_engine.main --mode live --source ninjatrader --profile live_gc
```

## Portas

| Fonte        | Porta | Config                         |
|--------------|-------|--------------------------------|
| NinjaTrader  | 5556  | `--source ninjatrader`         |
| Bookmap      | 5558  | `--source bookmap`             |
| Sinais ZMQ   | 5555  | (saída do engine)               |
| Dashboard    | 8501  | Streamlit                      |

Não rode NT e Bookmap na mesma porta. Use uma fonte por vez.

## Calibração

O simulador serve para validar o **pipeline**. Limiares MF de `simulator_btc` são iniciais — ajuste `mf_fixed_threshold_contracts` e `tick_size` olhando o volume típico do seu feed.

## Limitação da Python API

A API Python **não** suporta alguns providers (ex.: Bookmap Data / dxFeed). Se o seu plano live for um desses, será preciso Java API ou outro caminho. O simulador costuma funcionar com a Python API.

## Problemas comuns

| Sintoma | Ação |
|---------|------|
| Engine IDLE, 0 ticks | Add-on ativo no gráfico? Script Run? Porta 5558 livre? |
| `Connection refused` | Rode o publisher **antes** do engine |
| Volume sempre estranho | Ajuste `size_multiplier` / limiar MF no perfil |
| Símbolo errado no painel | Normal: o publisher deriva o nome do alias Bookmap |
