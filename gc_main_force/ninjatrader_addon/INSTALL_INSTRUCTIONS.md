# Instalação — GC Tick Publisher (NinjaTrader 8)

**Forma recomendada: Indicator** (aparece na lista de indicadores do gráfico).  
Não usa NetMQ. Publica ticks em **TCP porta 5556** (JSON por linha).

> Não use **Import Add-On (ZIP)** — isso é para pacotes da loja.

## Pré-requisitos

- NinjaTrader 8
- Market data do símbolo **GC**

## Instalação (Indicator)

1. Arquivo já em:
   ```
   Documentos\NinjaTrader 8\bin\Custom\Indicators\GcTickPublisherIndicator.cs
   ```
2. Abra o NinjaTrader.
3. **New → NinjaScript Editor** → **F5 (Compile)**.
4. Abra um **gráfico de GC**.
5. Clique com botão direito no gráfico → **Indicators…**
6. Procure **GC Tick Publisher (TCP)** → **Add** → **OK**.
7. No canto superior direito do gráfico deve aparecer: `LISTENING` + ticks.

## Validar no Python

Com o add-on LISTENING:

```powershell
cd c:\MainForceFundsFlow\gc_main_force
python -m python_engine.main --mode live
```

A janela do add-on deve mostrar **Python clients: 1** e ticks/sec > 0.

## Troubleshooting

| Problema | Solução |
|----------|---------|
| Instrument not found | Confirme o nome GC no NT (contrato contínuo / front month) |
| Porta 5556 em uso | Feche outro processo na porta ou altere `_port` no `.cs` |
| Sem ticks | Abra gráfico GC; confira conexão de dados |
| Compile CS0246 NetMQ | Você está com arquivo antigo — use a versão TCP deste repositório |
