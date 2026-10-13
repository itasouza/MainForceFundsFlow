# Prompt para o Cursor — Painel GC Main Force Flow

## Contexto
Painel em **Streamlit** (v1.65) que monitora o fluxo do Main Force no ouro (GC) em tempo real.
Fluxo: NinjaTrader (TCP :5556) → engine Python incremental → `signal_state.json` → painel em `http://localhost:8501`.

- Pasta do projeto: `gc_main_force/`
- Arquivos do painel:
  - `dashboard/app.py` — layout da página, sidebar, tema, abas, atualização automática.
  - `dashboard/components.py` — cartões, seção do footprint, gráficos Plotly, tabela de log.
- Tema base: `.streamlit/config.toml` (escuro).
- Iniciar (a partir de `gc_main_force`):
  `python -m streamlit run dashboard/app.py --server.port 8501 --server.headless true`
- Estado atual já commitado no `main` (commit `0f728bb`). Parta dele.

## Como o painel está organizado hoje
- Barra compacta no topo: título, status LIVE, etiqueta do sinal composto, horário (Brasília) e 5 blocos (Preço, Sessão, Regime IA, Sinal pausado, Thresholds).
- Seletor de tema (5 paletas escuras) na tela principal, canto direito do cabeçalho.
- Abas: **Operação** (multi-timeframe + footprint), **Gráficos** (preço 10m + sinais), **Log de sinais**.
- Footprint: botões de timeframe `10m / 30m / 1H`, card de leitura com etiqueta do timeframe, blocos de números e gráfico de net MF por preço.
- Sidebar: controles recolhidos em expanders (Thresholds, Footprint, IA / Kill Switch) e filtro de sessão.
- Horários exibidos em `America/Sao_Paulo` (`fmt_br` e `_series_br` em `components.py`). Os dados internos continuam em UTC.
- Stop / Deploy / menu "⋮" ocultos por CSS. O botão de reabrir a sidebar fica dentro de `stToolbar`, **não esconder `stToolbar`**.

## Regras para não quebrar
1. Não mudar a lógica do engine (`python_engine/`), só a apresentação.
2. Cores: verde = compra, vermelho = venda, cinza = neutro. Não inverter.
3. Manter o painel compacto e legível; evitar blocos grandes e textos longos.
4. O padrão é tema escuro. Se mexer nas cores, testar nas 5 paletas.
5. Depois de editar `components.py`, reiniciar o Streamlit se a tela não atualizar (cache de módulo).
6. Não commitar nem fazer push sem eu pedir.

## O que eu quero agora
<!-- Escreva aqui o pedido. Exemplos: -->
<!-- - Salvar a escolha do tema para o painel lembrar após F5. -->
<!-- - Mostrar um alerta sonoro quando o sinal composto mudar. -->
<!-- - Juntar o gráfico de preço e o footprint lado a lado na aba Gráficos. -->

## Como validar
Abrir `http://localhost:8501`, conferir as três abas, trocar o tema e o timeframe do footprint, e checar que não aparece nenhum erro vermelho na tela.
