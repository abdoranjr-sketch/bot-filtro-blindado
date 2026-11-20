# Bot Filtro Blindado — Czech Liga Pro (v5)

Bot de Telegram que analisa **somente a Czech Liga Pro** (tênis de mesa), 24 horas,
madrugada inclusive. Em todo **hh:55 (CET)** avalia os jogos da hora seguinte. Se houver
jogos e nenhum passar, a mensagem diz `Entrada: NENHUMA — sem desnível claro nesta rodada`.
Hora sem jogos da liga não gera mensagem. GREEN/RED, resumo diário às 22:30, saudações
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
4. Se ninguém passar, o hh:55 diz `Entrada: NENHUMA` e lista o motivo de cada jogo.

Os vetos de vencedor x vencedor e perdedor x perdedor continuam. Sem odds, ou com cache
de odds acima de 20 minutos, não há entrada. Os resultados do dia vêm do MoviOdds
(`/results`) e ficam em `DATA_DIR` (`forma_dia_v5.json`) para não repetir chamada fora da grade.

## Odds e resultados (MoviOdds)

São **160 consultas por dia** (odds + resultados), **4.960 em 31 dias**, abaixo de 5.000.
A grade cobre as 24 horas. 07:48 continua, mas a primeira consulta do dia é **00:10**.

| Por hora | Minutos | Tipo |
|---|---|---|
| Resultados | :10, :30, :48 e, em 16 horas, :20 | forma do dia |
| Odds antes do envio | :40 e :52 (cache &lt; 20 min no :55) | odds |
| Entrada | :55 | odds |

72 odds + 88 resultados = 160. Nos outros minutos o cache vale. Se a API falha, o mesmo
slot tenta de novo depois de cerca de 60 segundos (no máximo 2).

Cada slot (`YYYY-MM-DD|HH:MM`) é consultado uma vez. Se a resposta vier vazia por erro
da API, o mesmo slot tem uma nova tentativa depois de cerca de 60 segundos (no máximo
2). Uma lista vazia sem erro, ou a falta de chave, não é tentada de novo. As odds ficam
em cache até o próximo slot de odds (no máximo 20 minutos) e alimentam a entrada,
inclusive as retentativas das hh:55–hh:59. Os resultados finalizados acumulam em
`forma_dia_v5.json`. A grade está em `agenda_moviodds()` (também `MOVIODDS_MINUTOS_ODDS`
e `MOVIODDS_MINUTOS_RESULTADOS`). Cada consulta grava `INFO`:
`[ODDS] consulta HH:MM -> N jogos` ou `[RESULTADOS] consulta HH:MM -> N jogos`.

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
| `DATA_DIR` | pasta persistente dos dados (ex.: `/data`) |

## Deploy
Railway/Render/Fly usam o `Dockerfile` (ou `Procfile`: `worker: python bot_filtro_blindado_v5.py`).
Monte um volume em `/data`.

## Testes
```
pip install -r requirements.txt
python tests/test_v5.py && python tests/test_v5_discussao.py && python tests/test_v5_filtro.py && python tests/test_v5_moviodds.py && python tests/test_v5_odds_agenda.py
```

🔞 +18 · Aposte com responsabilidade.
