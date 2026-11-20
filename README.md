# Bot Filtro Blindado — Czech Liga Pro (v5)

Bot de Telegram que analisa **somente a Czech Liga Pro** (tênis de mesa), 24 horas,
madrugada inclusive. A entrada sai **cerca de 5 minutos antes de cada bloco de início**
(:00, :30 ou qualquer outro minuto), em qualquer modo. Se o bloco tiver jogos e nenhum
passar, a mensagem é `HH:MM — Sem entrada`.
Bloco sem jogos da liga não gera mensagem. GREEN/RED, resumo diário às 22:30,
resumo das entradas às 00:05 (dia anterior, em unidades), saudações
e comandos (/placar /semana /mes /entradas /ajuda /id) continuam iguais.

Fontes: ScoreMondo (jogos, placar ao vivo e resultados — páginas públicas) e MoviOdds
(odds e resultados finalizados). Outras ligas são ignoradas.

## Filtro rígido — forma na janela móvel

O alvo é quem tem o **melhor `score_forma`**, não o favorito da casa. A conta usa só
os últimos 2 ou 3 jogos finalizados nas **últimas 4 horas** (pesos: 3-0 = +3,0,
3-1 = +2,0, 3-2 = +0,5, 2-3 = −0,5, 1-3 = −2,0, 0-3 = −3,0). `jogos_hoje` conta os
finalizados nas últimas 3 horas. Para sinalizar, nesta ordem:

1. Os dois jogadores têm pelo menos 1 jogo finalizado nas últimas 3 h. Senão: sem dados do dia.
2. A odd do alvo está entre 1,25 e 1,85 (inclusive).
3. O alvo não perdeu o último jogo e tem pelo menos 2 vitórias limpas seguidas (3-0 ou 3-1).
4. O último jogo do alvo não foi 5 sets terminado há menos de 45 minutos.
5. O alvo não começou outro jogo nos 45 minutos anteriores a este apito (horário anterior,
   por exemplo 17:30 e agora 18:00). Vale o início gravado e a grade, mesmo sem placar.
6. Bônus de adversário comum nas últimas 3 h: alvo venceu C por 3-0/3-1 e o adversário
   perdeu para C por 0-3/1-3 → +2,0; alvo venceu C por 3-0 e o jogo do adversário com C
   foi a 5 sets → +1,0. Entra se `gap = score_alvo − score_adv + bônus` for pelo menos
   5,0 e o adversário tiver score ≤ 0. Os dois com score ≥ 3,0 são descartados.

Vários aprovados no mesmo bloco saem ordenados pelo maior gap. O Telegram leva só
a entrada: horário, `Alvo x Adversário`, em quem apostar e a odd. Se ninguém passar,
a mensagem é `HH:MM — Sem entrada`. Score, gap, bônus e o motivo de cada jogo ficam
no log. Sem odds, ou com cache de odds acima de 20 minutos, não há entrada.

Os resultados ficam em `DATA_DIR/forma_dia_v5.json`, com início e fim de cada jogo.
Se a API não manda o fim, usamos o início mais 15, 20 ou 25 minutos (3, 4 ou 5 sets).
Se só há o fim, o início é o fim menos essa duração. Arquivo antigo só com `quando`
trata esse campo como início. A lista não zera à meia-noite: guarda as últimas 8 horas.

## Odds e resultados (MoviOdds)

São **160 consultas por dia** na grade (odds + resultados), **4.960 em 31 dias**, abaixo de 5.000.
Uma consulta de odds traz todos os jogos futuros, então odds saem a cada 15 minutos.
A primeira do dia é **00:00**.

| Por hora | Minutos | Chamadas |
|---|---|---|
| Odds | :00, :15, :30, :45 | 96 |
| Resultados | :10 e :40; :22 nas horas em que `hora % 3 != 2` | 64 |

96 + 64 = 160. No envio (~5 min antes do apito) o cache de odds tem no máximo 13 minutos,
abaixo dos 20. Nos outros minutos o cache vale. Se a API falha, o mesmo slot tenta de
novo depois de cerca de 60 segundos (no máximo 2).

O cache de odds fica em `DATA_DIR` (`odds_cache_v5.json`). No reinício, uma lista com
menos de 20 minutos é reaproveitada. Sem odds frescas e com jogo começando em até 30
minutos, o bot faz **uma** consulta imediata naquele dia (o teste do dia aceita ≤161).

Cada slot (`YYYY-MM-DD|HH:MM`) da grade é consultado uma vez. Uma lista vazia sem erro,
ou a falta de chave, não é tentada de novo. Os resultados finalizados acumulam em
`forma_dia_v5.json`. A grade está em `agenda_moviodds()`. Cada consulta grava `INFO`:
`[ODDS] consulta HH:MM -> N jogos` ou `[RESULTADOS] consulta HH:MM -> N jogos`.
Cada bloco grava `[ENTRADA YYYY-MM-DD|HH:MM] N jogos avaliados, X aprovados`.
As entradas aprovadas ficam em `DATA_DIR/entradas_v5.json` (dia, horário, confronto,
alvo, adversário e odd). O resultado sai dos placares que o MoviOdds e o
SportsAPI365 já gravaram, sem consulta extra. Às 00:05 Europe/Prague sai um
resumo do dia anterior, uma vez: `Resumo DD/MM`, totais e saldo (green = odd−1,
red = −1). Sem entradas: `Resumo DD/MM — nenhuma entrada`. Pendente não entra
no saldo; se fechar depois, aparece no resumo seguinte.
O jogo aprovado no Telegram mostra horário, alvo x adversário e a odd. O detalhe fica no log.

## Resultados anteriores (SportsAPI365)

Fonte opcional, só de contexto. A chave fica em `SPORTSAPI365_KEY` (RapidAPI, plano
gratuito, **50 requisições por dia**). Sem a variável o recurso fica desligado em
silêncio: não há aviso, não há linha nova e o filtro de hoje não muda.

Depois das **00:30 Europe/Prague**, uma vez por dia, o bot baixa os jogos já terminados
de ontem da Czech Liga Pro (no máximo 3 páginas de 100) e guarda em
`DATA_DIR/historico_sportsapi365.json`, mantendo **14 dias**. No primeiro arranque, sem
esse arquivo, busca até **7 dias**. O teto do recurso é **40 chamadas por dia**; o
contador fica em `DATA_DIR/sportsapi365_contador.json` e também obedece
`x-ratelimit-requests-remaining` (para com 10 de folga sob as 50). HTTP 429 ou 403
desliga a fonte até o reset. A chave não entra no código nem no log. Não há consulta
por jogo nem por jogador: o log lê só o cache.

No log de cada bloco, cada jogador com casamento único de nome ganha
`Histórico 7d: X V / Y D (Z% limpas)`. Z é o percentual de jogos desses 7 dias que
foram vitórias limpas (3-0 ou 3-1). Se os dois se enfrentaram nos 14 dias:
`H2H 14d: A x B`. Nome no formato `Bilek Z.` só casa com um nome da MoviOdds (por
exemplo `Zdenek Bilek`) quando não existe outro casamento possível. Sem casamento
único, o histórico daquele jogador fica de fora.

Essas linhas não vão para o Telegram e o H2H não bloqueia a entrada. As 160
consultas do MoviOdds continuam iguais.

## Configuração (variáveis de ambiente)
Veja `.env.example`. **Nunca** coloque tokens no código nem faça commit do `.env`.

| Variável | Uso |
|---|---|
| `TELEGRAM_TOKEN` | token do bot (obrigatório) |
| `TELEGRAM_CHAT_ID` | chat privado do dono/admin (obrigatório) |
| `TELEGRAM_GROUP_ID` | canal/grupo onde saem entradas, resultados, resumo e saudações |
| `TELEGRAM_DISCUSSION_ID` | grupo de discussão ligado ao canal (conversa e comandos) |
| `TELEGRAM_OWNER_ID` | id do admin (padrão = `TELEGRAM_CHAT_ID`) |
| `MOVIODDS_KEY` | chave do MoviOdds (odds e resultados) |
| `MOVIODDS_KEY_2` | chave reserva do MoviOdds (opcional; usada por 30 min se a principal falhar) |
| `SPORTSAPI365_KEY` | resultados anteriores (SportsAPI365 / RapidAPI, opcional). Sem ela, o bot segue igual |
| `DATA_DIR` | pasta persistente dos dados (ex.: `/data`) |

## Deploy
Railway/Render/Fly usam o `Dockerfile` (ou `Procfile`: `worker: python bot_filtro_blindado_v5.py`).
Monte um volume em `/data`.

## Testes
```
pip install -r requirements.txt
python tests/test_v5.py && python tests/test_v5_discussao.py && python tests/test_v5_filtro.py && python tests/test_v5_moviodds.py && python tests/test_v5_odds_agenda.py && python tests/test_v5_sportsapi365.py && python tests/test_v5_forma.py && python tests/test_v5_resumo.py
```

🔞 +18 · Aposte com responsabilidade.
