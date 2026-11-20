# Bot Filtro Blindado — Czech Liga Pro (v5)

Bot de Telegram que analisa a Czech Liga Pro (tênis de mesa) e envia as entradas da 2ª rodada às
**08:55 · 12:55 · 16:55 · 20:55 (CET)**, com GREEN/RED de cada entrada, resumo diário às 22:30,
saudações com frases motivacionais e comandos (/placar /semana /mes /entradas /ajuda /id).

Fontes: ScoreMondo (jogos, resultados e placar ao vivo — páginas públicas) e MoviOdds (odds, opcional).

## Odds (MoviOdds)

O MoviOdds não é consultado a cada scrape. São **92 consultas por dia** (~2.760 por mês),
sempre no fuso CET (Europe/Madrid). A 1ª rodada de cada ciclo hh em 08, 12, 16 e 20
começa em hh:00, então a grade começa 12 minutos antes:

| Momento | Minutos | Consultas |
|---|---|---|
| Antes da 1ª rodada | (hh-1):48, (hh-1):54 | 2 |
| 1ª rodada | hh:00, :06, :12, :18, :20, :24, :30, :36, :42, :48 | 10 |
| Entrada | hh:55 | 1 |
| 2ª rodada | (hh+1):00, :06, :12, :18, :20, :24, :30, :36, :42, :48 | 10 |

23 por ciclo, 4 ciclos, 92 no dia. O :55 existe porque a entrada precisa de odds naquele
minuto; os :20 existem porque a grade de 6 minutos cai em :18 e :24. Nos minutos
intermediários a 1ª rodada, a entrada e a 2ª rodada reutilizam o cache.

Cada slot (`YYYY-MM-DD|HH:MM`) é consultado uma vez. Se a resposta vier vazia por erro
da API, o mesmo slot tem uma nova tentativa depois de cerca de 60 segundos (no máximo
2). Uma lista vazia sem erro, ou a falta de chave, não é tentada de novo. O resultado
fica em cache até o próximo slot e é o que a entrada (inclusive as retentativas das
hh:55–hh:59) e os scrapes de R1/R2 recebem. ScoreMondo, resultados e os intervalos de
scrape não mudam. A grade está em `MOVIODDS_MINUTOS`, como pares
`(deslocamento de hora a partir de HORAS_ENTRADA, minuto)`. Cada consulta grava uma
linha `INFO`: `[ODDS] consulta HH:MM -> N jogos`.

## Configuração (variáveis de ambiente)
Veja `.env.example`. **Nunca** coloque tokens no código nem faça commit do `.env`.

| Variável | Uso |
|---|---|
| `TELEGRAM_TOKEN` | token do bot (obrigatório) |
| `TELEGRAM_CHAT_ID` | chat privado do dono/admin (obrigatório) |
| `TELEGRAM_GROUP_ID` | canal/grupo onde saem entradas, resultados, resumo e saudações |
| `TELEGRAM_DISCUSSION_ID` | grupo de discussão ligado ao canal (conversa e comandos) |
| `TELEGRAM_OWNER_ID` | id do admin (padrão = `TELEGRAM_CHAT_ID`) |
| `MOVIODDS_KEY` | chave do MoviOdds (odds) |
| `MOVIODDS_KEY_2` | chave reserva do MoviOdds (opcional; usada por 30 min se a principal falhar) |
| `DATA_DIR` | pasta persistente dos dados (ex.: `/data`) |

## Deploy
Railway/Render/Fly usam o `Dockerfile` (ou `Procfile`: `worker: python bot_filtro_blindado_v5.py`).
Monte um volume em `/data`.

## Testes
```
pip install -r requirements.txt
python tests/test_v5.py && python tests/test_v5_discussao.py && python tests/test_v5_moviodds.py && python tests/test_v5_odds_agenda.py
```

🔞 +18 · Aposte com responsabilidade.
