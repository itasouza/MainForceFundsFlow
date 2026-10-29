# Prompt — instalar o indicador do linhão no Bookmap

Instale o add-on que já está no projeto. Não crie outro script e não reescreva a lógica das linhas.

Origem (a versão nova):

`C:\MainForceFundsFlow\gc_main_force\bookmap_addon\bm_tick_publisher.py`

Destino, que é a pasta de scripts Python do Bookmap nesta máquina:

`C:\Users\Administrator\AppData\Local\Bookmap\Python\bm_tick_publisher.py`

O Bookmap lista e executa o arquivo dessa pasta. O arquivo em `tmp\bm_tick_publisher\script.py` é só a cópia que ele faz ao dar Run. Não edite o `tmp`.

## O que fazer

1. Confirme que a origem existe e contém as oito linhas no painel `PRIMARY`: `Ontem fechamento`, `Ontem abertura`, `Ontem maxima`, `Ontem minima`, `Linhao fechamento`, `Linhao abertura`, `Linhao maxima`, `Linhao minima`. Também deve conter `_candles_from_depth` e a porta TCP `5558`.
2. Se o destino já existir, copie-o para `bm_tick_publisher.py.bak` na mesma pasta antes de substituir. Não apague `bm_tick_publisher.py.bak_20261020`.
3. Copie a origem por cima do destino.
4. Confirme que o destino tem o mesmo tamanho da origem e as mesmas oito strings acima.

## O que não fazer

- Não mate o processo `python.exe` cujo comando contém `Bookmap\Python\tmp\bm_tick_publisher\script.py`. Esse processo é do Bookmap. Encerrar daqui derruba o tick e a porta que o Bookmap abriu para o script.
- Não dê `python bm_tick_publisher.py` por fora. Sem o Bookmap o módulo `bookmap` não existe, e um segundo processo na porta `5558` mistura ou bloqueia o tick do engine.
- Não reinicie o engine nem o painel. Os dois continuam como estão.
- Não faça commit.

## O que só a pessoa faz no Bookmap

O Cursor não clica na janela do Bookmap. Ao terminar a cópia, diga para ela:

1. No editor da Python API, parar o script que está rodando.
2. Abrir de novo `C:\Users\Administrator\AppData\Local\Bookmap\Python\bm_tick_publisher.py`. Se a aba antiga continuar aberta, o Run grava o texto velho por cima.
3. Run. No log: `LISTENING TCP 0.0.0.0:5558` e `velas do arquivo ao vivo` com os oito preços.
4. Ativar o add-on no gráfico do WDO, um gráfico só.

As linhas ficam no painel de preço com os nomes acima. A cor inicial pode ser trocada pelo Bookmap. O nome é o que separa ontem do linhão.
