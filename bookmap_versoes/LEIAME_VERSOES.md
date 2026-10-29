# Versões das configurações do Market Pulse (Bookmap)

Cada versão tem uma pasta com a cópia de `bookmap_config_v22.json` (onde o Bookmap
guarda as configurações dos widgets) e os valores anotados abaixo.

Arquivo vivo: `C:\Users\Administrator\AppData\Local\Bookmap\Config\bookmap_config_v22.json`

## Como voltar para uma versão
1. Feche o Bookmap normalmente (ele grava a configuração ao fechar).
2. Copie `bookmap_versoes\<versão>\bookmap_config_v22.json` por cima do arquivo vivo.
3. Abra o Bookmap.
Alternativa sem copiar arquivo: digitar os valores da tabela direto no widget (menu ⋮ do widget).

## v0_original (antes de qualquer ajuste, copiado em 21/10/2026)
Widgets no gráfico WDOX26@CC, painel "Panel 1".

| Widget | Algoritmo | Half-life | Training | Threshold | Outros |
|---|---|---|---|---|---|
| WDOX-VP | volumePressureEMS/TP (Volume Pressure) | 2 | 4 | 0.7 | soundSpeedMultiplier 15, soundDuration 3, soundInterval 2, historicalDataPeriod 0, volume 50 |
| WDOX-PC | priceChange (Price Change) | n/a | 4 | 0.7 | prioritizeEstimate true, soundSpeedMultiplier 15, soundDuration 3, soundInterval 2, historicalDataPeriod 0, volume 50 |
| Multi Algo | multiAlgo (combina VP + PC) | n/a | n/a | n/a | desabilitado |

Observação: a unidade de half-life e training não está explícita na documentação.

## Unidades reais (confirmadas na janela Settings do widget, 21/10/2026)
Os valores guardados na configuração (half-life 2, training 4) correspondem a:
Half-life = 10 s, Training = 5 min. (Antes eu tinha suposto minutos para a meia-vida: estava errado.)

## v1 (21/10/2026 10:08) — widget duplicado "VP v1"
Criado com "Duplicate" no menu do WDOX-VP. O WDOX-VP original continua rodando com os valores da v0, para comparar ao vivo.

| Widget | Half-life | Training | Threshold |
|---|---|---|---|
| WDOX-VP (original, v0) | 10 s | 5 min | 70 |
| **VP v1** | **1 min** | **20 min** | 70 |
| WDOX-PC (original, v0, inalterado) | n/a | 5 min | 70 |
| **PC v1** (criado às 10:15, duplicando o WDOX-PC) | n/a | **20 min** | 70 |

Motivo: a meia-vida de 10 s deixa o Volume Pressure com memória curta demais, e ele vira de lado a cada força nova.
Hipótese a testar: com 1 min / 20 min ele deve virar menos e acompanhar melhor o CVD, reagindo um pouco mais tarde.
Resultado observado: (preencher depois de uma sessão)
Backup em arquivo: (copiar bookmap_config_v22.json para v1_... depois de fechar o Bookmap, que é quando ele grava)

Par de comparação: VP v1 + PC v1 usam a mesma escala de tempo de referência (20 min) para o training.
O Price Change mede o desvio do último preço em relação à média do intervalo de training; por isso o PC v1
precisa do mesmo intervalo do VP v1 para os dois falarem da mesma escala.

## Observações de 21/10/2026
- 10:29 — Tentativa de ligar o Absorption indicator no WDOX26@CC: o Bookmap mostrou uma tela de prévia em vez de ativar.
  Texto da tela: modo ao vivo exige o pacote Global+; sem ele só funciona gratuitamente em instrumentos com dados atrasados.
  Conclusão: o add-on NÃO está ativo no WDOX26. A conta atual parece não ter Global+ (a suposição anterior estava errada).
- 10:16–10:25 — Queda de ~5030 para ~5021 sobre os blocos de compra de 5022 (2.194) e 5020,5 (1.672), com recuperação rápida
  para 5030. CVD seguiu negativo (-6.589) enquanto o preço subiu: sugere absorção por liquidez passiva. Não confirmado
  pelo Absorption indicator, que não pôde ser ligado.
- PC original (5 min) -21% e PC v1 (20 min) +17% no mesmo momento: o sinal do Price Change depende da escala da média.

## Leitura de 11:47 (v1 com ~1h40 de vida; amostra de fotos pontuais, não contagem contínua)
Contexto: preço subiu de ~5032 (10:37) até ~5042 (por volta de 11:43) e recuou para ~5031,5 às 11:47.
CVD: -4.502 (10:37) -> -8.003 (11:41) -> -10.737 (11:45) -> -12.436 (11:47).

| Hora | VP v0 (vendas/compras) | VP v1 (vendas/compras) | PC v0 | PC v1 |
|---|---|---|---|---|
| 11:41 | 10,44m / 0,84m (12,5x venda) | 23,84m / 9,00m (2,6x venda) | -81% | -32% |
| 11:41 (2) | 3,11m / 0,64m (4,8x venda) | 20,25m / 7,77m (2,6x venda) | -63% | -30% |
| 11:45 | 5,21m / 2,09m (2,5x venda) | 20,66m / 11,77m (1,75x venda) | -92% | -98% |
| 11:47 | 1,57m / 1,52m (1,03x, equilibrado) | 16,12m / 8,59m (1,9x venda) | -67% | -87% |

Observações:
- VP v1 ficou entre 1,75x e 2,6x de venda nos quatro registros, sempre do mesmo lado do CVD e do preço (queda).
  O VP v0 foi de 12,5x para 1,03x em 6 minutos, enquanto o preço seguia caindo e o CVD seguia piorando: esquece depressa.
- Par PC: inconclusivo. O PC v1 NÃO ficou mais calmo nessa janela (foi de -30% para -98%): com o preço longe da média de 20 min,
  o desvio fica grande. O PC v0 (média de 5 min) ficou entre -63% e -92%.
- Amostra: cerca de dez leituras manuais; ainda não contei viradas de lado de forma contínua.
- Tradermap Pro segue desabilitado por erro de licença; Absorption indicator bloqueado (exige Global+ no ao vivo).

Recomendação do momento: o VP v1 parece mais estável que o v0 e coerente com CVD/preço. Candidata a próxima rodada: v2a
(meia-vida 3 min, só essa variável) a partir do VP v1. Só criar com confirmação do usuário.

## Limpeza do subgráfico (21/10/2026 11:52) — mudança só visual, a pedido do usuário
- Motivo: o subgráfico do WDOX26 tinha uns 8 a 10 traços sobrepostos (CVD + linhas de percentual dos 4 widgets) e ficou ilegível.
- WDOX-VP (original): desmarcado "Percentage" em Subchart settings (antes: marcado). Half-life 10s / training 5min / threshold 70 inalterados.
- WDOX-PC (original): desmarcado "Percentage" em Subchart settings (antes: marcado). Training 5min / threshold 70 inalterados.
- VP v1: desmarcado "Percentage" às 11:56 (antes: marcado). Half-life 1min / training 20min inalterados.
- PC v1: desmarcado "Percentage" às 12:00 (antes: marcado). Training 20min inalterado. Subgráfico agora só com a linha do CVD.
- 12:01 — CVD -19.745 (era -12.436 às 11:47) com o preço estável/subindo em ~5035: divergência persistente de ~1h30 (preço sobe, CVD cai).
  VP v1 e CVD usam a mesma classificação de agressor do feed, então não são confirmações independentes entre si.
- Bookmap abriu maximizado às 11:57 depois de reativar a janela; havia uma só instância (PID 10168 + JVM 3932, ambas de 09:01).
- Para voltar: abrir Settings do widget (menu ⋮) e marcar "Percentage" de novo.
- O passo "desmarcar Separar compradores/vendedores no CVD Grandes" não se aplicou: o CVD Grandes só existia no gráfico do ES
  (que já não está aberto). No WDOX26 o CVD tem uma aba só ("CVD"), sem filtro de tamanho, faixa "Intervalo de sessões".

## Mapa de calor — versão original (21/10/2026 12:20), gráfico WDOX26@CC
Modo percentil (automático). Valores lidos em Configurações de estudos > Mapa de calor:
- % do corte inferior: 80 (tamanho exato: desmarcado, campo 0)
- % do corte superior: ~96 (tamanho exato: desmarcado, campo 1)
- Suavização/média vertical: Auto
- Mapa de cores: padrão do Bookmap (preto, azul, amarelo, vermelho)
- Exibir controle deslizante de corte inferior na barra de ferramentas: marcado; Otimização do zoom out: marcada
Cópia em arquivo: bookmap_versoes\v0_original\bookmap_config_v22.json (gravada às 09:00, antes de qualquer mudança no mapa de calor).
Referência do usuário (Profit): escala de 500 a 3000 contratos, uma cor por faixa; vermelho = 2000 e 3000? e rosa = 3000? (a confirmar).
Para voltar: desmarcar "Tamanho exato" e pôr os cortes em 80 e ~96, ou usar o botão RESTAURAR da janela.

## Mapa de calor v1 (21/10/2026 12:29) — tamanho exato em contratos
Backup antes da mudança: bookmap_versoes\v0b_antes_mapa_calor\bookmap_config_v22.json
(o arquivo vivo só é regravado quando o Bookmap fecha; a data dele ainda era 09:00, então reflete o mapa em percentil original).
Mudança: "Tamanho exato" marcado nos dois cortes: inferior = 500, superior = 3000 (antes: percentil 80 / ~96).
Efeito observado: o mapa ficou quase todo escuro/azul; só apareceram marcações fracas (ex.: bloco pequeno perto de 5030).
Hipótese: o mapa de calor usa o tamanho por nível de preço, e quase nenhum nível chega a 500 com o corte superior em 3000
(no COB os maiores níveis têm ~1.100 a 2.300). Não há cores por faixa no Bookmap, só um degradê entre os dois cortes.
Como voltar: Configurações de estudos > Mapa de calor: desmarcar os dois "Tamanho exato" e pôr os cortes em 80 e ~96 (ou botão RESTAURAR).
O controle deslizante de corte inferior da barra de ferramentas ficou desativado enquanto o tamanho exato está ligado.

Resultado: NÃO funcionou (avaliação do usuário). Revertido às 12:32: "Tamanho exato" desmarcado nos dois cortes;
sliders de volta a 80 e ~96 e controle da barra de ferramentas reativado. O mapa de calor está de novo na versão original (percentil).

## CVD v1 — "CVD 1h" (21/10/2026 13:12), gráfico WDOX26@CC
CVD original: inalterado (aba "CVD": sem filtro de tamanho, Intervalo de sessões, sem pontos de referência).
Novo CVD (aba "CVD 1h"): sem filtro de tamanho, Intervalo de sessões, ponto de referência: primeira reinicialização
2026-10-21 13:12:23, repetir a cada 1 h. Cores: positivo azul, negativo vermelho (padrão).
Opções de repetição disponíveis no Bookmap: nunca, 10/30 seg, 1 a 5 min, 10, 15, 20, 30 min, 1 h, 2 h, 4 h, 12 h, 1 dia.
Confirmado: o CVD 1h zerou às 13:12 (marcava 143 contra -15.193 do original).
Observação: os reinícios caem a cada hora a partir de 13:12:23 (14:12:23, 15:12:23...), não na hora cheia.
Para voltar: Configurar complementos > Cumulative Volume Delta > aba "CVD 1h" > botão Remover.
Resultado observado: (preencher depois de algumas horas, comparando com o CVD original e com o preço)

## CVD original removido do gráfico (21/10/2026 13:16), a pedido do usuário
Motivo: a sessão inteira mostrou uma resposta diferente do preço (CVD preso na queda da manhã, divergência de horas).
Fica só o "CVD 1h" no gráfico WDOX26@CC.
Como recriar o original: Configurar complementos > Cumulative Volume Delta > aba "+" > Nome "CVD" > Criar;
depois deixar Faixa de indicadores = "Intervalo de sessões", sem filtro de tamanho e sem pontos de referência.
Última leitura do original antes de remover: ~-15.200 (13:16: -18.930 por flutuação do feed ao vivo).
Backup em arquivo: bookmap_versoes\v0_original e v0b_antes_mapa_calor (contêm a configuração anterior às mudanças de hoje).

## Como voltar para a v0 sem arquivo
Apagar os widgets "VP v1" e "PC v1" (X no cabeçalho de cada um) e usar o WDOX-VP e o WDOX-PC originais, que não foram alterados.

## CVD v2 — "CVD 30m" criado ao lado do "CVD 1h" (21/10/2026 13:56), gráfico WDOX26@CC
Decisão do usuário: manter os dois CVDs (1h e 30m) para comparar. Nenhum foi removido.
"CVD 30m": criado em Configurar complementos > Cumulative Volume Delta > aba "+" (sem filtro de tamanho, Intervalo de sessões).
PENDENTE: ponto de referência de reinício a cada 30 min (o diálogo "Adicionar ponto" ficou aberto atrás do Panel 1).
Enquanto não houver ponto de referência, o CVD 30m acumula desde a criação (13:56) e não zera.
Para configurar: Adicionar... > primeira reinicialização em horário redondo (ex.: 14:00:00) > repetir a cada 30 min.
Resultado observado: (preencher depois de algumas horas, comparando CVD 1h x CVD 30m x preço)

### Correção do CVD 30m (21/10/2026 15:08)
O ponto de referência (2026-10-21 13:56:24) tinha sido criado com "Repetir: nunca", então o CVD 30m acumulou ~1h10 (-30.885)
sem zerar. Corrigido para "Repetir: 30 min": o medidor caiu para -9.886 (último reinício 14:56:24 + 30 min). Reinícios caem
em :26:24 e :56:24 de cada hora. CVD 1h continua reiniciando em X:12:23. Leituras do CVD 30m anteriores às 15:08 não valem como 30 min.

## CVD v3 (21/10/2026 16:15) — ERRO ao remover o "CVD 1h": o add-on Cumulative Volume Delta inteiro foi removido
Pedido: remover só o "CVD 1h" (baixo volume do WDO, leitura tardia). Antes disso, o "CVD 15m" ficou com ponto de referência
2026-10-21 16:05:17, Repetir 15 min (estava "nunca").
O botão "Remover" no rodapé da janela Configurar complementos remove o ADD-ON INTEIRO (as três abas: 1h, 30m e 15m), não a aba.
Para remover só uma aba, usar o "X" ao lado do nome da aba. Resultado: CVD sumiu do gráfico WDOX26@CC e da lista de complementos.
Para recriar: Configurar complementos > Adicionar... > Cumulative Volume Delta; abas "CVD 30m" (ponto 13:56:24, repetir 30 min) e
"CVD 15m" (ponto 16:05:17, repetir 15 min), ambas com Intervalo de sessões e sem filtro de tamanho. Sem "CVD 1h".

### Recuperação (21/10/2026 16:22)
O plugin Cumulative Volume Delta v0.11 foi reinstalado em Definições > Configurar complementos > Gerenciar complementos > Disponível para instalação > Instalar.
As abas e pontos de referência voltaram sozinhos (a config das abas ficou guardada). Depois removi SÓ a aba "CVD 1h" pelo "X" da aba.
Estado final: "CVD 30m" (ponto 13:56:24, repetir 30 min) e "CVD 15m" (ponto 16:05:17, repetir 15 min), Intervalo de sessões.
Motivo de tirar o 1h: volume baixo do WDO, leitura tardia. Lembrete: "Remover" no rodapé = add-on inteiro; "X" na aba = só a aba.

### CVD religado (22/10/2026 10:46)
Ao abrir o Bookmap em 22/10 (agora em inglês/PT misto), o add-on Cumulative Volume Delta não estava mais na lista de complementos
do WDOX26@CC e o painel/medidores de CVD tinham sumido. Causa não confirmada (reinício do Bookmap?). Obs.: o Tradermap Pro avisa
que não deve ser usado com outros add-ons (seus dados filtrados podem interferir).
Reinstalado: Gerenciar plug-ins > Complementos Bookmap (L1) > Disponível para instalação > Cumulative Volume Delta v0.11 > Instalar.
As abas voltaram sozinhas com a configuração guardada, conferida na tela:
- CVD 30m: ponto 2026-10-21 13:56:24, repetir 30 min, Intervalo do gráfico.
- CVD 15m: ponto 2026-10-21 16:05:17, repetir 15 min, Intervalo de sessões.
Medidores às 10:46: CVD 15m +14.8k, CVD 30m +14.0k (ambos comprador, depois do fundo ~5031 de 10:2x).
Nota: as duas abas usam faixa de indicadores diferente (30m = gráfico, 15m = sessões); igualar se quiser comparar de forma justa.

## Regra de leitura v1 (22/10/2026)
Leitura do usuário: Pulse + volume + CVD (CVD 15m principal, CVD 30m contexto). Sinal só vale quando os três concordam;
se um discordar, esperar. Os limiares são sugestão e devem ser ajustados pelo usuário.

| Indicador | Compra | Venda |
|---|---|---|
| Pulse | VP v1 e PC v1 compradores, acima de 70 | vendedores, abaixo de -70 |
| Volume | barras/bolhas agressoras compradoras | vendedoras |
| CVD 15m | positivo, longe de zero e subindo | negativo, longe de zero e caindo |
| CVD 30m | mesmo sinal do 15m (contexto) | mesmo sinal do 15m |

Cuidados: os três derivam dos mesmos trades (não são fontes independentes); Pulse em extremos (>95%) costuma desacelerar;
CVD 15m e 30m estão com faixa de indicadores diferente (15m = sessões, 30m = gráfico).

### Tabela de observações (preencher a cada ocorrência)
| Data/hora | Pulse | Volume | CVD 15m | CVD 30m | Preço / nível | O que o preço fez depois | Acertou? |
|---|---|---|---|---|---|---|---|
| 22/10 10:10-10:14 | VP v1 47m/22m, PC -85% a -99% | bolhas vermelhas grandes | (CVD off) | (CVD off) | faixas 5043 e 5040 atravessadas, 5038 (fech. anterior) atingido | fundo ~5031 às ~10:30, depois subiu | venda confirmada até o fundo |
| 22/10 10:47-10:49 | VP v1 34,97m/15,06m a 42,08m/17,13m, PC 99%->59%, PC v1 97%->79% | barras verdes crescentes | +20.0k -> +27.3k | +19.3k -> +26.6k | subindo de 5031 a 5044,5, faixa grossa 5043-5046 à frente | (preencher) | (preencher) |

### Hipótese a testar: fechamento do dia anterior
Usuário guarda imagens de 13/10 a 21/10 (7 pregões) em que o preço buscou o fechamento do dia anterior; 22/10 também (5038, ~10:13).
Para ter valor: definir "buscou" (toque exato / a 1 ponto), anotar horário e se rebateu ou passou, e comparar com a taxa-base.

## CVD 10m adicionado (22/10/2026 11:07), gráfico WDOX26@CC
Pedido do usuário: ter um CVD de 10 min para antecipar movimentos em relação ao Pulse. Criado como aba "CVD 10m" no add-on
Cumulative Volume Delta (sem filtro de tamanho, Intervalo de sessões), ponto de referência 2026-10-22 11:06:19, repetir 10 min
(estava "nunca" depois de criado; corrigido na tabela). Reinícios em :06:19, :16:19, :26:19... de cada hora.
Abas ativas agora: CVD 30m (13:56:24 / 30 min, gráfico), CVD 15m (16:05:17 / 15 min, sessões), CVD 10m (11:06:19 / 10 min, sessões).
Cuidado: janela de 10 min com volume baixo do WDO oscila e vira de sinal fácil; usar como antecipação, não como gatilho sozinho.
Hipótese a testar: o CVD 10m vira de sinal antes do VP v1/PC v1? Anotar horários das viradas na tabela de observações.

## CVD 5m adicionado (22/10/2026 11:43)
Pedido do usuário: conjunto de CVD curtos (5m, 10m, 15m) para antecipar viradas junto com Pulse e mapa de calor.
Criada a aba "CVD 5m" (sem filtro de tamanho, Intervalo de sessões), ponto de referência 2026-10-22 11:42:56, repetir 5 min
(saiu com "nunca"; corrigido na tabela). Reinícios em :x2:56 e :x7:56 de cada hora.
O CVD 30m foi MANTIDO (o usuário ainda não decidiu removê-lo). Abas ativas: 30m, 15m, 10m, 5m.
Se o usuário decidir tirar o 30m: usar o "X" da aba (nunca o "Remover" do rodapé, que apaga o add-on inteiro).
Cuidado: janela de 5 min com o volume do WDO oscila muito; usar como aviso antecipado, não como gatilho sozinho.
Conclusão do usuário em 22/10: operar quando Pulse, volume e CVD concordam (Regra de leitura v1). Ainda sem taxa de acerto medida.

## Ordem dos medidores de CVD (22/10/2026 12:04)
Pedido: ordenar do menor para o maior (5m, 10m, 15m, 30m). Arrastar abas não reordena. Os medidores seguem a ORDEM ALFABÉTICA
pelo nome ("CVD 10m" < "CVD 15m" < "CVD 30m" < "CVD 5m"). Solução: a aba de 5 min foi removida (pelo "X" da aba) e recriada como
"CVD 05m" (zero à esquerda), que ordena primeiro. Ordem agora: CVD 05m, 10m, 15m, 30m.
CVD 05m: ponto 2026-10-22 12:03:50, repetir 5 min, Intervalo de sessões (saiu com "nunca"; corrigido). Os outros 3 não foram alterados.
Histórico do CVD 5m anterior (criado 11:42:56) foi perdido ao recriar.
Para futuros CVDs: usar nomes com zero à esquerda (ex.: "CVD 05m", "CVD 60m") se quiser manter a ordem numérica.

## VP com treino de 5/10/15 min (22/10/2026 12:57-13:00) — EM ANDAMENTO
Objetivo: validar o Pulse junto com os CVD 05m/10m/15m usando as mesmas escalas de tempo. Só o treino muda; meia-vida fica em 1 min (a do VP v1).
Configuração do VP v1 confirmada nas Settings: Threshold 70, Volume 50, Half-life 1 min, Training 20 min, Load historical data 0 s.
Feito: duplicado o VP v1 (menu ⋮ > Duplicate) -> renomeado "VP 05m" (nome com zero à esquerda para ordenar) e treino mudado de 20 para 5 min
(slider + APPLY). O Bookmap recalculou os indicadores com o histórico ("eventos importados 2 mi/10 mi") e voltou ao normal.
Feito também: segunda cópia do VP 05m (Duplicate), AINDA com nome "VP 05m" e treino 5 min; precisa virar "VP 10m" (treino 10 min).
Falta: "VP 15m" (treino 15 min). Depois, organizar a ordem dos widgets no painel.
Treino no slider: clicar no controle e usar seta esquerda/direita (passos 20 > 10 > 5 min); depois APPLY ao lado do slider.
Incidente: um open_application("Bookmap") abriu uma SEGUNDA instância do Bookmap (tela "Reading main config..." e aviso com botão "Sair");
não clicar em nada nela sem ler o aviso; fechar com cuidado pela própria janela dela, sem fechar a instância principal.

## VP simplificado: WDOX-05M, WDOX-10M, WDOX-20M (22/10/2026 13:10)
Decisão do usuário: simplificar a leitura do Pulse e remover os outros VP.
Removidos (pelo X do widget): VP v1 (meia-vida 1 min / treino 20 min) e WDOX-VP original (10 s / 5 min). Podem ser recriados com esses valores.
Mantidos: PC v1 (treino 20 min) e WDOX-PC (treino 5 min).
Painel agora: PC v1, WDOX-PC, WDOX-05M, WDOX-10M, WDOX-20M. VP novos: Volume Pressure, limiar 70, volume 50, meia-vida 1 min,
treino 5 / 10 / 20 min, histórico 0 s, instrumento WDOX26@CC.
O slider de treino NÃO tem 15 min (passos 5, 10, 20): por isso o terceiro é WDOX-20M e não 15M. Setas esquerda/direita mudam o passo; clique no slider é impreciso.
Após cada APPLY o Bookmap recalcula o histórico e o painel fica instável por alguns segundos.
Pendente: segunda instância do Bookmap aberta por engano ("Initializing UI..." com botão "Sair") ainda na tela; fechar sem fechar a principal.
Observação: a ordem dos widgets no painel é a de criação; CVD usa a mesma lógica de escala (05m, 10m, 15m, 30m).

## Nomes curtos dos VP e incidente com o Multi Algo (22/10/2026 13:17)
Os nomes WDOX-05M/10M/20M apareciam cortados no painel ("WDOX-0...") e o usuário não sabia qual era qual. Renomeados para
"VP 05m", "VP 10m" e "VP 20m" (cabem inteiros). Configuração: Volume Pressure, limiar 70, volume 50, meia-vida 1 min, treino 5/10/20 min.
Incidente: ao tentar abrir o menu de um widget, o painel tinha mudado de tamanho e um clique caiu em "Start MA": criou um widget
"Multi Algo" e o WDOX-PC (Price Change, treino 5 min, limiar 70) SUMIU do painel. Cliquei em "Stop MA": o Multi Algo foi desfeito, mas o
WDOX-PC não voltou. Painel agora: PC v1, VP 05m, VP 10m, VP 20m. Para restaurar o WDOX-PC: Duplicate no PC v1 e treino 5 min (ou Create widget).
Observação importante: os três VP mostram valores IDÊNTICOS nas barras (ex.: 5,85m / 5,68m). O treino parece afetar só a calibração
(percentual/limiar), não o valor absoluto da pressão; quem muda o valor é a meia-vida. Para diferenciar de fato, variar a meia-vida
ou habilitar "Percentage" no subgráfico.
Lembrete: tirar uma foto do painel antes de clicar; o painel muda de tamanho e os cliques erram.

### WDOX-PC restaurado (22/10/2026 13:23)
Duplicado o PC v1 (menu ⋮ > Duplicate) e configurado: nome "WDOX-PC", Price Change, limiar 70, volume 50, treino 5 min (slider: clicar e seta esquerda 2x a partir de 20).
Painel agora: Multi Algo (voltou sozinho/Start MA ligado; não foi religado de propósito), PC v1 (20 min), VP 05m, VP 10m, VP 20m, WDOX-PC (5 min).

## PC organizado por tempo (22/10/2026 13:30)
Pedido: PC com o mesmo padrão do VP (um widget por tempo, o tempo no nome). Renomeados: PC v1 -> "PC 20m" (treino 20 min); WDOX-PC -> "PC 05m" (treino 5 min).
Criado "PC 10m" duplicando o PC 05m e subindo o treino para 10 min (no slider o passo salta 5 -> 20; voltar uma vez com a seta esquerda dá 10).
Todos: Price Change, limiar 70, volume 50, histórico 0 s, instrumento WDOX26@CC.
Painel agora (ordem de criação): Multi Algo, PC 20m, VP 05m, VP 10m, VP 20m, PC 05m, PC 10m.
Não reordenei os widgets (a ordem é a de criação; não achei como arrastar). Para ter VP e PC agrupados 05m/10m/20m, seria preciso recriar na ordem desejada.
Multi Algo continua no painel (voltou depois do incidente das 13:15); remover pelo X do widget se não for usado.

## Estudo do Multi Algo (22/10/2026 14:53) — só leitura, nada alterado
Settings do Multi Algo: Algorithm = Multi Algo (desabilitado/cinza), Instrument = "PC 10m, PC 05m, VP 10m, VP 20m, PC 20m, VP 05m"
(lista cinza, NÃO editável: clique não abre seletor), Threshold 70, Volume 50, Load historical data 0 s, Percentage marcado, nome em branco,
sons 101P/101N. Não tem meia-vida nem treino próprios.
Conclusão: o Multi Algo combina TODOS os VP e PC do painel (agora os 6). Valor segue o conjunto (ex.: 73%, 83%, 80%, -13%).
Duplicá-lo por tempo não funciona como pretendido: a lista de widgets não é editável, então cada cópia combinaria os mesmos 6 e mostraria o mesmo número.
Para ter um agregado por tempo seria preciso um painel/instrumento separado só com os widgets daquele tempo (não testado).
Alternativa para reduzir a tela: manter o Multi Algo como resumo único e esconder/remover os VP/PC que não forem usados; ou manter só VP+PC de 2 tempos.
Observação: o Multi Algo depende dos widgets; remover um VP/PC muda o Multi Algo.

### PC 20m sumiu do painel (22/10/2026 15:01)
Às 14:52 o PC 20m ainda estava na lista "Instrument" do Multi Algo; às 15:01 o painel tinha só: Multi Algo, VP 05m, VP 10m, VP 20m, PC 05m, PC 10m.
Causa NÃO confirmada (último clique meu foi fechar as Settings do Multi Algo; não vi remoção do PC 20m). Para restaurar: Duplicate no PC 10m ou 05m,
nome "PC 20m", Price Change, limiar 70, treino 20 min (slider: seta direita a partir de 10 pula para 20).

### Observação 22/10 15:10 -> 15:18 (venda; momento de confluência completa segundo o usuário)
| Hora | CVD 05m / 10m / 15m / 30m | PC 05m / 10m / 20m | VP (vendas/compras) | Multi Algo | Preço / mapa |
|---|---|---|---|---|---|
| 15:10 | +169 / -1.579 / -4.935 / -154 | +10% / -32% / -22% | 11,84m / 11,00m (equilibrado) | -10% | 5051; faixas abaixo 5046-5047 e 5043 (1.885) |
| 15:18 | -1.062 / -1.281 / -4.929 / -148 | -85% / -49% / -71% | 10,07m / 5,97m (1,7x venda) | -57% | 5049; faixas 5047-5049, 5045 e 5043 (1.904); acima 5055 |
Virada dos curtos (CVD 05m e PC 05m para venda) entre 15:10 e 15:18. Usuário considera 15:18 o momento ideal. Resultado do preço depois: (preencher).
Pergunta do usuário: remover o CVD 05m por ruído? Recomendação dada: manter por alguns dias como CONFIRMAÇÃO (foi o último a virar e completou o sinal), contar falsos sinais antes de decidir.

## Gráfico WDO-TM@TM.Pro (23/10/2026)
- A aba do TM.Pro tinha sumido porque o gráfico estava PARADO (não apagado). Religado em Definições > Configurar complementos > Tradermap Pro > botão ▶
  ao lado de WDOX26@CC (só fica ativo com o mercado aberto; fora do pregão mostra "Waiting for MBO data"). O TM.Pro é um gráfico separado, o CVD e o Pulse ficam na aba WDOX26@CC.
- 09:27: ligado o Cumulative Volume Delta também no gráfico do TM.Pro (com a aba do TM.Pro à frente: Configurar complementos (WDO-TM@TM.Pro) > marcar Cumulative Volume Delta).
  Criou só a aba padrão "CVD" (acumulado da sessão, sem pontos de referência): marcava -30.950 às 09:27 e -30.304 às 09:28.
  NÃO ligar o bm_tick_publisher neste gráfico (duplicaria a publicação na porta 5558). O Panel (VP, PC, Multi Algo) é compartilhado.
- Pendente: criar as abas de CVD 05m/10m/15m no TM.Pro com os pontos de referência (decisão do usuário) e comparar valores com o CVD do WDOX26@CC
  (o Tradermap Pro avisa que seus dados filtrados podem interferir em outros add-ons).

### CVD 05m/10m/15m criados no WDO-TM@TM.Pro (23/10/2026 09:32)
Gráfico WDO-TM@TM.Pro (add-on Cumulative Volume Delta v0.12 neste gráfico; no WDOX26@CC é v0.11). Abas: "CVD" (padrão, acumulado da sessão), "CVD 05m", "CVD 10m", "CVD 15m"; todas Intervalo de sessões, sem filtro de tamanho.
Pontos de referência (NÃO os mesmos do WDOX26@CC: o diálogo "Adicionar ponto" usa a hora atual e não editei a data):
- CVD 05m: 2026-10-23 09:30:18, repetir 5 min
- CVD 10m: 2026-10-23 09:31:26, repetir 10 min
- CVD 15m: 2026-10-23 09:32:02, repetir 15 min
Todos saíram com "nunca" e foram corrigidos na tabela. Reinícios diferentes dos do WDOX26@CC (05m: :x3:50/:x8:50; 10m: :x6:19...; 15m: :05:17, :20:17, :35:17, :50:17), então os valores não batem entre os dois gráficos.
Janela do Bookmap maximizada para tentar ver os medidores; só 3 medidores aparecem (CVD, CVD 05m e CVD 10m); o de 15m não estava visível.
O OK do diálogo "Adicionar ponto" fica na borda superior da tela (aprox. x=78, y=129).

## Observação 23/10/2026 — fundo no 5040 sem liquidez abaixo e faixa forte em 5056 (hipótese do usuário)
Hipótese do usuário: com a faixa em ~5040-5041 e nada abaixo dela no mapa de calor, não faz sentido o preço ir lá; "o preço precisa comprar" porque há
uma faixa vermelha muito forte em ~5056-5057 (outras em ~5059-5061). Hipótese complementar: esperar até as 10h permite saber se a mínima/máxima das
primeiras horas é o fundo/topo do dia. Ressalvas dadas: ausência de liquidez abaixo não impede o preço de furar; só o fluxo (CVD/Pulse) sustenta; um fundo só
é confirmado depois; o perfil CVP mostra volume já negociado (vazio abaixo da mínima por definição), não liquidez de ordens.

Linha do tempo (WDOX26@CC; mínima do dia ~5040,5-5041,5; fundo testado ~09:30, ~10:00 e ~10:13):
| Hora | Preço | CVD 05m / 10m / 15m / 30m | VP (vendas/compras) | PC 05m / 10m / 20m | Multi Algo |
|---|---|---|---|---|---|
| 09:34 | 5042,5 | +575 / +149 / -626 / (sessão -37.637) | 25,81m / 19,85m | -18% / -31% / -46% | -24% |
| 10:10 | 5046 | +749 / +1.291 / -2.433 / -1.498 | 14,61m / 18,38m | +57% / +26% / -10% | +18% |
| 10:18 | 5046 | -3.640 / -4.763 / -6.318 / -5.383 | 23,56m / 15,15m | +13% / +12% / +14% | -13% |
| 10:23 | 5048,5 | +5.463 / +700 / +4.839 / +80 | 12,78m / 21,72m | +54% / +63% / +37% | +49% |
| 10:25 | 5049 | +701 / +3.011 / +7.150 / +2.391 | 13,06m / 20,85m | +24% / +61% / +41% | +42% |
Alvo da hipótese: faixa vermelha ~5056-5057. Resultado (preço chegou? rebateu? furou o 5040?): (preencher). 
Obs.: neste dia o fluxo oscilou entre vendedor (10:18) e comprador (10:10, 10:23-10:25) com o preço lateral 5042-5050; todos os CVD só ficaram positivos juntos às 10:25.

### Colunas sugeridas para a tabela de observações dos próximos dias
Dia | fechamento anterior | mínima das primeiras horas (até 10h) e nº de testes | máxima das primeiras horas | amplitude do dia (pontos) | horário da mínima e da máxima do dia | fundo sem liquidez abaixo: rebateu ou furou? | CVD 05m/10m no momento

### Nota 23/10 10:30 — significado do 5056 (informado pelo usuário, NÃO verificado no Bookmap)
Usuário: "5056 é o preço de fechamento / da mínima de ontem" (ambiguidade: fechamento de 22/10 ou mínima de 22/10 — a confirmar no Profit). Coincide com a faixa vermelha larga do mapa em ~5056-5057.
Reforça a hipótese anterior (preço busca o fechamento do dia anterior), com a liquidez no mesmo nível. Conferir no Profit: fechamento e mínima de 22/10, e se o preço tocou 5056 hoje.

### Nota 23/10 10:35 — referência de ontem (informada pelo usuário, do Profit; não verificada no Bookmap)
Última vela de 10m de ontem (22/10) fechou em 5.062,08. Portanto o fechamento de ontem = ~5062,08 (e o 5056 NÃO é o fechamento; significado do 5056 ainda a esclarecer).
Zona acima do preço (mapa): faixa vermelha larga ~5056-5057, faixas ~5059-5061, fechamento de ontem 5062,08 logo acima.
Obs.: o feed do Profit e o da Cedro no Bookmap podem diferir alguns centavos/pontos.

## CVD do WDOX26@CC replicado no WDO-TM@TM.Pro (23/10/2026 10:52)
Pedido: levar todas as configurações de CVD do WDOX26@CC para o TM.Pro. Abas agora no TM.Pro (todas sem filtro de tamanho, cores padrão verde/vermelho restauradas com o botão de seta de cada cor):
| Aba | Faixa | Ponto de referência (alinhado ao WDOX26@CC) | Repetir |
|---|---|---|---|
| CVD 05m | sessões | 2026-10-23 10:43:50 (:x3:50 / :x8:50) | 5 min |
| CVD 10m | sessões | 2026-10-23 10:36:19 (:x6:19) | 10 min |
| CVD 15m | sessões | 2026-10-23 10:35:17 (:05:17 :20:17 :35:17 :50:17) | 15 min |
| CVD 30m (nova) | gráfico | 2026-10-23 10:26:24 (:26:24 / :56:24) | 30 min |
O campo de data aceita digitação: clicar, ctrl+a, digitar "AAAA-MM-DD HH:MM:SS", Enter. Nome com zero à esquerda (05m) mantém a ordem.
Ainda existe no TM.Pro a aba padrão "CVD" (acumulado da sessão) que NÃO existe no WDOX26@CC; mantida (decisão do usuário pendente). Add-on v0.12 no TM.Pro e v0.11 no CC.
Valores devem ficar próximos dos do CC (mesmos horários de reinício), mas o TM.Pro filtra dados e pode diferir.
