# Prompt — linhas do linhão no gráfico do Bookmap

Implemente no add-on Python que já roda no Bookmap. Não crie um projeto novo.

Arquivo: `gc_main_force/bookmap_addon/bm_tick_publisher.py`

## O que fazer

Desenhar **8 linhas horizontais no gráfico de preço do Bookmap** (painel principal, não num subpainel). O script de hoje só publica trades no TCP `5558` e grava fotos de profundidade. Isso continua igual. As linhas entram no mesmo add-on, no mesmo gráfico em que ele já está ativo.

As linhas são a abertura, a máxima, a mínima e o fechamento de **dois pregões já encerrados**. Não é média, pivô nem cálculo novo.

### Quatro linhas de ontem (as que o usuário desenha à mão no Profit)

| Nível | Nome no indicador |
|---|---|
| Fechamento de ontem | `Ontem fechamento` |
| Abertura de ontem | `Ontem abertura` |
| Máxima de ontem | `Ontem maxima` |
| Mínima de ontem | `Ontem minima` |

Exemplo real do pregão estudado (não gravar estes números no código; servir só para conferir):

- fechamento 5.348,50
- abertura 5.354,00
- máxima 5.401,50
- mínima 5.313,00

### Quatro linhas do linhão amarelo (o que o indicador do Profit já traz)

São a abertura, a máxima, a mínima e o fechamento do **pregão anterior a ontem**.

| Nível | Nome no indicador |
|---|---|
| Fechamento | `Linhao fechamento` |
| Abertura | `Linhao abertura` |
| Máxima | `Linhao maxima` |
| Mínima | `Linhao minima` |

Exemplo do mesmo estudo (também não gravar no código):

- fechamento 5.357,00
- abertura 5.417,00
- máxima 5.418,00
- mínima 5.310,00

## Como o preço usou essas linhas (contexto, não é regra de ordem)

No aberto, o preço foi primeiro no fechamento de ontem (5.348,50). Depois apoiou no fechamento do linhão (5.357,00) e usou esse nível como trampolim na direção da máxima de ontem (5.401,50). O add-on só desenha os níveis. Não emite sinal de compra nem de venda.

## Cálculo

1. Cada trade que o Bookmap entregar (histórico já carregado no gráfico e, depois, o ao vivo) entra numa vela diária.
2. O dia é o **pregão de mini dólar em America/Sao_Paulo**, não a meia-noite UTC. Um trade das 21:00 UTC ainda pertence ao pregão do mesmo dia civil em São Paulo enquanto o pregão B3 estiver aberto; o que importa é a data local do pregão.
3. Cada vela diária guarda abertura, máxima, mínima e fechamento.
4. A vela do dia de hoje, ainda aberta, **não** vira linha. As oito linhas saem das duas últimas velas **fechadas**: a mais recente é “ontem”; a anterior é o linhão.
5. Quando o pregão vira, as linhas passam para o novo “ontem” e o novo “dia anterior”. Não deixar o nível de anteontem congelado para sempre.
6. Preço no Bookmap vem como `price_level * pips`, do mesmo jeito que `handle_trades` já faz.

## Desenho no Bookmap

Antes de chamar a API, abra o módulo `bookmap` instalado na máquina e use as funções reais de indicador (nomes do tipo `register_indicator` / `add_indicator` no painel `PRIMARY`, e publicação de ponto com o preço do nível). Não invente um nome de função.

Uma linha horizontal é o mesmo preço publicado ao longo do tempo, no painel de preço. Uma função de indicador por nível, oito no total.

A cor o Bookmap escolhe na configuração do indicador. Não prometa rosa, roxa, vermelha, azul e amarela iguais ao Profit. O nome da linha é o que distingue ontem do linhão.

A linha passa a existir com o add-on ligado e segue para a direita. Se a API não pintar o passado do gráfico, não force um desenho falso: publique o nível e deixe a linha correr.

Se o gráfico não tiver histórico de dois pregões, não invente preço. Escreva no log que faltam velas e só desenhe quando as duas velas fechadas existirem.

## O que não pode quebrar

- TCP `0.0.0.0:5558`, JSON de tick com `timestamp`, `symbol`, `price`, `volume`, `bid`, `ask`.
- Profundidade e o arquivo em `gc_main_force/data_depth`.
- `_derive_symbol` e o símbolo curto que o engine já recebe.
- Um erro ao desenhar a linha não pode derrubar o publisher de ticks nem o snapshot de profundidade.

## Como provar que ficou certo

1. No Bookmap, parar o script e dar Run de novo em `bm_tick_publisher.py`, com o add-on ativo no gráfico do WDO que tem histórico de pelo menos dois pregões.
2. No log do add-on, as oito linhas com os quatro preços de ontem e os quatro do pregão anterior.
3. No gráfico, oito linhas horizontais no painel de preço, cada uma com o nome acima.
4. O engine em `--source bookmap` continua recebendo ticks na porta 5558.
