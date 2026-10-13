# Instalação — GC Tick Publisher ZMQ (NinjaTrader 8)

Add-On de produção: **ConcurrentQueue + worker + NetMQ PUB** (não bloqueia `OnMarketData`).

- Endpoint: `tcp://*:5556`
- Tópico: `gc_ticks`
- JSON: `timestamp, symbol, price, volume, bid, ask` (UTC)

> **Import Add-On (ZIP)** da loja **não** serve. Este arquivo vai em `Custom\AddOns\`.

## 1. Dependências (NetMQ + AsyncIO)

1. **Feche o NinjaTrader.**
2. Baixe NuGet **NetMQ 4.0.1.13** e **AsyncIO 0.1.69**.
3. Extraia e copie para:
   ```
   Documentos\NinjaTrader 8\bin\Custom\NetMQ.dll      (lib\net47 ou net48)
   Documentos\NinjaTrader 8\bin\Custom\AsyncIO.dll    (lib\net40)
   ```
4. (Opcional) No `NinjaTrader.Custom.csproj`, dentro do `ItemGroup` de `PackageReference` / `Reference`:

```xml
<Reference Include="NetMQ">
  <HintPath>C:\Users\SEU_USUARIO\Documents\NinjaTrader 8\bin\Custom\NetMQ.dll</HintPath>
  <Private>True</Private>
</Reference>
<Reference Include="AsyncIO">
  <HintPath>C:\Users\SEU_USUARIO\Documents\NinjaTrader 8\bin\Custom\AsyncIO.dll</HintPath>
  <Private>True</Private>
</Reference>
```

### Via UI do NinjaTrader

1. Abra o NinjaTrader.
2. **New → NinjaScript Editor**.
3. Clique direito no explorador → **References…** (ou **Tools → References**, conforme a build).
4. **Add** → navegue até `Documents\NinjaTrader 8\bin\Custom\NetMQ.dll`.
5. Repita para `AsyncIO.dll`.
6. OK → **Compile (F5)**.

`Newtonsoft.Json` normalmente já está referenciado no NT8; este Add-On **não depende** dele (JSON montado com `string.Format` + `InvariantCulture`).

## 2. Instalar o código

1. Copie `GcTickPublisher.cs` para:
   ```
   Documentos\NinjaTrader 8\bin\Custom\AddOns\GcTickPublisher.cs
   ```
2. **NinjaScript Editor → F5 (Compile)**.
3. Sem erros CS0246 de NetMQ.

## 3. Abrir o Add-On

1. No **Control Center**: **New → GC Tick Publisher ZMQ**
2. Janela deve mostrar **CONNECTED (PUB)** e `Published/sec` subindo.
3. Abra um gráfico **GC** (garante fluxo de Last/Bid/Ask).

## 4. Python

Em `python_engine/config.py`:

```python
"nt_tick_transport": "zmq",
"nt_zmq_subscribe": "tcp://localhost:5556",
"nt_zmq_topic": "gc_ticks",
```

```powershell
cd c:\MainForceFundsFlow\gc_main_force
python -m python_engine.main --mode live
streamlit run dashboard\app.py
```

## 5. Fallback sem NetMQ

Se NetMQ não compilar, use o indicador TCP:

- `Indicators\GcTickPublisherIndicator.cs`
- `nt_tick_transport`: `"tcp"`

## Troubleshooting

| Erro | Solução |
|------|---------|
| CS0246 NetMQ | DLL + Reference; feche NT antes de copiar DLL; recompile |
| Address in use 5556 | Feche o Indicator TCP ou outro PUB na mesma porta |
| Published/sec = 0 | Abra gráfico GC; confira conexão de dados |
| Python sem ticks | `nt_tick_transport=zmq`; tópico `gc_ticks`; PUB antes do SUB |
| NT trava | Você não deve publicar ZMQ dentro de OnMarketData — este Add-On usa fila |
