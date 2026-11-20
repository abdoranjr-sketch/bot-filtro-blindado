# Bot Filtro Blindado — Czech Liga Pro (v5)

Bot de Telegram que analisa **somente a Czech Liga Pro** (tênis de mesa), 24 horas,
madrugada inclusive. A entrada sai **cerca de 5 minutos antes de cada bloco de início**
(:00, :30 ou qualquer outro minuto), em qualquer modo. Se o bloco tiver jogos e nenhum
passar, a mensagem diz `Entrada: NENHUMA — sem desnível claro nesta rodada`.
Bloco sem jogos da liga não gera mensagem. GREEN/RED, resumo diário às 22:30, saudações
e comandos (/placar /semana /mes /entradas /ajuda /id) continuam iguais.

Fontes: ScoreMondo (jogos, placar ao vivo e resultados — páginas públicas) e MoviOdds
(odds e resultados finalizados). Outras ligas são ignoradas.

## Filtro rígido — forma do dia

O favorito é só a odd pré-jogo **deste** jogo (máximo 1.65). Entram todos os jogos já
finalizados de cada jogador desde 00:00 CET (Europe/Madrid, o fuso do dia no bot).
Para sinalizar, as condições valem juntas:

1. O favorito não perdeu hoje. Qualquer derrota descarta a odd (`❌ favorito … já perdeu hoje`).
2. Pelo menos 2 vitórias limpas (3-0 ou 3-1). Uma vitória 3-2 é alerta amarelo e bloqueia.
   Com só 1 vitória limpa, a entrada espera (`⏳ … precisa de 2`).
3. O adversário tem pelo menos uma derrota feia hoje (0-3 ou 1-3).
4. Se ninguém passar, o bloco diz `Entrada: NENHUMA` e lista o motivo de cada jogo.

Os vetos de vencedor x vencedor e perdedor x perdedor continuam. Sem odds, ou com cache
de odds acima de 20 minutos, não há entrada. Os resultados do dia vêm do MoviOdds
(`/results`) e ficam em `DATA_DIR` (`forma_dia_v5.json`) para não repetir chamada fora da grade.

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
por jogo nem por jogador: a mensagem lê só o cache.

Na mensagem de cada bloco, nos aprovados e na lista "Sem entrada", cada jogador com
casamento único de nome ganha:

`<b>Nome</b> — Histórico 7d: X V / Y D (Z% limpas)`

Z é o percentual de jogos desses 7 dias que foram vitórias limpas (3-0 ou 3-1). Se os
dois se enfrentaram nos 14 dias: `H2H 14d: A x B` (vitórias de quem aparece primeiro no
anúncio, depois as do adversário). Nome no formato `Bilek Z.` só casa com um nome da
MoviOdds (por exemplo `Zdenek Bilek`) quando não existe outro casamento possível. Sem
casamento único, o histórico daquele jogador fica de fora.

Critério extra, só de bloqueio: se o favorito perdeu os 2 confrontos diretos mais
recentes contra esse adversário nos 14 dias, a entrada não sai
(`❌ H2H: favorito perdeu os 2 últimos para X`). As quatro regras da forma do dia e as
160 consultas do MoviOdds continuam iguais.

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
python tests/test_v5.py && python tests/test_v5_discussao.py && python tests/test_v5_filtro.py && python tests/test_v5_moviodds.py && python tests/test_v5_odds_agenda.py && python tests/test_v5_sportsapi365.py
```

🔞 +18 · Aposte com responsabilidade.
