# Clube de Cinema - documentacao atual do projeto

Data de referencia: 2026-06-20

Este documento descreve o estado atual da aplicacao, como as pecas se ligam, quais sao os fluxos principais, que endpoints existem, como a base de dados esta modelada e que cuidados operacionais devem ser tidos em conta.

## Visao geral

O Clube de Cinema e uma aplicacao web para gerir semanas de votacao de filmes entre membros.

Funcionalidades principais:

- registo e login de utilizadores por username/password;
- criacao e gestao de semanas por admins;
- submissao de filmes por membros;
- votacao em filmes da semana;
- escolha/fecho de vencedor;
- arquivo de semanas;
- leaderboard;
- perfis publicos;
- integracao com Letterboxd;
- reacoes por emoji em filmes;
- chat por semana;
- pagina de pesquisa/visualizacao de filmes;
- temas visuais especiais, incluindo Portugal/Italian.
- restrições temporárias de participação geridas por admins;
- auto-desbanimento após validação de filmes obrigatórios no Letterboxd.

## Restrições de participação

O painel admin inclui uma lista de contas. Um admin pode impedir temporariamente qualquer conta, incluindo outra conta admin ou a sua própria, de submeter filmes e votar, sem bloquear o acesso às restantes áreas do site. Um admin restringido mantém acesso ao painel e pode desbanir-se.

Ao aplicar a restrição, o admin pode definir um motivo e até 20 filmes obrigatórios. O membro recebe um aviso inicial e mantém um lembrete acessível no site. Se tiver Letterboxd ligado, pode pedir uma sincronização e verificação automática. O auto-desbanimento só acontece quando todos os filmes surgem no diário com data igual ou posterior ao banimento. Sem filmes obrigatórios, apenas um admin pode desbanir.

Endpoints:

```http
GET  /admin/users
POST /admin/users/{user_id}/ban
POST /admin/users/{user_id}/unban
POST /auth/ban/check
```

A app e servida por um backend FastAPI que tambem serve os ficheiros estaticos do frontend.

## Estrutura do repositorio

```text
backend/
  app/
    main.py          # FastAPI app, endpoints, auth, integracoes e serving do frontend
    db.py            # configuracao SQLAlchemy e engine DB
    models.py        # modelos SQLAlchemy
    __init__.py
  alembic/
    env.py           # configuracao Alembic
    versions/        # migracoes
  create_admin.py    # helper para criar/promover admin
  requirements.txt   # dependencias Python

frontend/
  index.html         # pagina principal da semana atual
  app.js             # logica principal: auth, semana, votos, Letterboxd, chat
  archive.html/js    # arquivo, hall of fame, cinema
  admin.html/js      # painel admin
  leaderboard.html/js
  profile.html/js
  watch.html/js      # pesquisa de filmes
  portugal.html/js/css
  styles.css
  sw.js              # service worker
  assets de imagem/icon

README.md            # atualmente minimal
read.md              # este documento
```

## Stack tecnica

Backend:

- FastAPI
- Uvicorn
- SQLAlchemy
- Alembic
- Requests
- RapidFuzz
- python-dotenv
- psycopg2-binary

Frontend:

- HTML estatico
- CSS
- JavaScript sem framework
- Service Worker simples

Base de dados:

- SQLite por defeito em desenvolvimento local;
- Postgres/Supabase em producao quando `DATABASE_URL` esta definido.

## Configuracao da base de dados

Ficheiro: `backend/app/db.py`

`DATABASE_URL` e lido do ambiente.

Se nao existir, usa SQLite local:

```text
backend/cinema_club.db
```

Se `DATABASE_URL` comecar por `postgres://`, e normalizado para `postgresql://`.

Se usar Postgres sem driver explicito, e convertido para:

```text
postgresql+psycopg2://...
```

Para Supabase/Postgres, a pool SQLAlchemy esta configurada com:

- `pool_size = 5`
- `max_overflow = 5`
- `pool_pre_ping = True`
- `pool_recycle = 300`

Isto e importante porque o Supabase Free Plan/session pooler tem limites apertados de conexoes.

## Variaveis de ambiente

Variaveis usadas diretamente:

```text
DATABASE_URL
TMDB_API_KEY
```

`DATABASE_URL`:

- define a base de dados;
- em producao deve apontar para Supabase/Postgres.

`TMDB_API_KEY`:

- usada para pesquisar filmes no TMDB;
- usada tambem para matching automatico de filmes submetidos.

## Modelos de dados

Ficheiro: `backend/app/models.py`

### User

Tabela:

```text
users
```

Campos principais:

- `id`
- `username`
- `password_hash`
- `is_admin`
- `letterboxd_username`
- `letterboxd_avatar_url`
- `letterboxd_synced_at`
- `avatar_url`

Relacoes:

- `sessions`
- `letterboxd_entries`

Notas:

- `username` e unico.
- `password_hash` usa PBKDF2 no backend.
- `avatar_url` definido pelo utilizador tem prioridade sobre o avatar vindo do Letterboxd.

### Session

Tabela:

```text
sessions
```

Campos:

- `id`
- `user_id`
- `token`
- `created_at`
- `expires_at`

Serve para auth por bearer token.

TTL atual:

```text
30 dias
```

### Week

Tabela:

```text
weeks
```

Campos:

- `id`
- `title`
- `is_open`
- `is_ready`
- `winner_film_id`
- `is_special`
- `theme`

Significado:

- `is_open`: semana aberta ou fechada;
- `is_ready`: votacao ativa ou ainda em preparacao;
- `winner_film_id`: filme vencedor quando a semana fecha;
- `is_special`: usado para semanas/entradas especiais de cinema;
- `theme`: permite temas visuais especiais.

### Film

Tabela:

```text
films
```

Campos:

- `id`
- `week_id`
- `title`
- `year`
- `director`
- `poster_url`
- `submitter_key`
- `submitted_title`
- `submitted_year`
- `tmdb_id`
- `match_score`
- `needs_review`

Notas:

- `title/year/poster_url/tmdb_id` podem ser normalizados via TMDB.
- `submitted_title/submitted_year` guardam o que o user submeteu originalmente.
- `needs_review` marca filmes que o matching TMDB nao apanhou com confianca.
- `submitter_key` e usado para regras de voto/submissao; atualmente corresponde ao `user.id` como string.

### Vote

Tabela:

```text
votes
```

Campos:

- `id`
- `week_id`
- `film_id`
- `voter_key`

Constraint:

```text
unique_vote_per_week_per_voter
```

Ou seja, um votante so pode votar uma vez por semana.

### LetterboxdEntry

Tabela:

```text
letterboxd_entries
```

Campos:

- `id`
- `user_id`
- `tmdb_id`
- `film_title`
- `film_year`
- `rating`
- `watched_date`
- `letterboxd_url`
- `is_rewatch`

Serve como cache local das entradas RSS do Letterboxd dos membros.

Constraint:

```text
uq_lb_entry_user_tmdb
```

### Reaction

Tabela:

```text
reactions
```

Campos:

- `id`
- `user_id`
- `film_id`
- `emoji`

Constraint:

```text
uq_reaction_user_film
```

Um user so pode ter uma reacao ativa por filme.

### ChatMessage

Tabela:

```text
chat_messages
```

Campos:

- `id`
- `week_id`
- `user_id`
- `content`
- `created_at`

Serve para chat/discussao por semana.

## Migracoes Alembic

Migracoes atuais:

```text
efe9de7c931d_initial_schema.py
b3f1a2c4d5e6_letterboxd_integration.py
c4e2b1d3f5a7_user_avatar.py
d5e6f7a8b9c0_reactions_chat.py
f6a7b8c9d0e1_egress_query_indexes.py
```

A migracao mais recente adiciona indices para queries frequentes:

- `films.submitter_key`
- `films.week_id`
- `votes.voter_key`
- `votes.week_id`
- `votes.film_id`
- `chat_messages.week_id, chat_messages.id`
- `letterboxd_entries.user_id, letterboxd_entries.watched_date`

Para aplicar migracoes:

```bash
cd backend
alembic upgrade head
```

## Backend - app FastAPI

Ficheiro principal:

```text
backend/app/main.py
```

Responsabilidades:

- configura a app FastAPI;
- serve frontend estatico;
- gere auth;
- expõe endpoints publicos;
- expõe endpoints admin;
- integra TMDB;
- integra Letterboxd;
- gere chat/reacoes/perfis/leaderboard;
- adiciona rate limiting/logging/cache.

## Middleware e protecoes

Existe middleware HTTP que:

- ignora ficheiros estaticos principais;
- aplica rate limit por IP e path;
- devolve `429` se exceder o limite;
- loga requests com:
  - path;
  - metodo;
  - status;
  - tempo de resposta.

Limites atuais:

```text
RATE_LIMIT_WINDOW = 60 segundos
RATE_LIMIT_DEFAULT = 180 requests por janela
RATE_LIMIT_AUTH = 40 requests por janela para /auth/*
```

Tambem existe cache em memoria:

- `_response_cache`;
- `cache_get`;
- `cache_set`;
- `clear_response_cache`.

A cache e limpa automaticamente apos `commit` SQLAlchemy.

Nota importante:

- esta cache e por processo;
- se houver multiplos workers/processos, cada um tem a sua propria cache;
- para varios workers, Redis/Upstash seria mais consistente.

## Auth

### Registo

Endpoint:

```http
POST /auth/register
```

Body:

```json
{
  "username": "rita",
  "password": "1234"
}
```

Regras:

- username obrigatorio;
- 3 a 32 caracteres;
- apenas letras, numeros, `_`, `.`, `-`;
- password minimo 4 caracteres.

Resposta:

- user;
- token.

### Login

Endpoint:

```http
POST /auth/login
```

Resposta:

- user;
- token.

### Sessao atual

Endpoint:

```http
GET /auth/me
Authorization: Bearer <token>
```

Resposta inclui:

- id;
- username;
- is_admin;
- letterboxd_username;
- avatar_url;
- synced_at.

### Alterar username

Endpoint:

```http
PATCH /auth/username
```

Protegido por login.

### Avatar

Endpoint:

```http
PATCH /auth/avatar
```

Aceita:

- URL HTTP/HTTPS;
- data URI `data:image/...`.

Limite aproximado para base64:

```text
2.5 MB
```

### Logout

Endpoint:

```http
POST /auth/logout
```

Remove a sessao/token se existir.

## Fluxo principal de semanas

### Semana atual

Endpoint:

```http
GET /weeks/current
```

Devolve:

- id;
- title;
- is_open;
- is_ready;
- winner_film_id;
- theme;
- lista de filmes com votos agregados.

A query carrega apenas colunas necessarias e usa agregacao SQL para votos.

### Listar semanas

Endpoint:

```http
GET /weeks?page=1&limit=50
```

Limite maximo:

```text
100
```

Usado pelo arquivo e pela secao "visto pelo clube".

### Listar semanas cinema

Endpoint:

```http
GET /weeks/cinema?page=1&limit=50
```

Usado pela vista cinema no arquivo.

### Obter semana especifica

Endpoint:

```http
GET /weeks/{week_id}
```

### Submeter filme

Endpoint:

```http
POST /weeks/{week_id}/submissions
Authorization: Bearer <token>
```

Body:

```json
{
  "title": "Strange Days",
  "year": 1995,
  "director": "Kathryn Bigelow"
}
```

Regras:

- semana tem de existir;
- semana tem de estar aberta;
- user so pode submeter um filme por semana;
- titulo e obrigatorio;
- se nao for dado poster manual, tenta matching TMDB.

### Votar

Endpoint:

```http
POST /weeks/{week_id}/vote
Authorization: Bearer <token>
```

Body:

```json
{
  "film_id": 123
}
```

Regras:

- semana tem de estar aberta;
- `is_ready` tem de ser true;
- so submitters da semana podem votar;
- user nao pode votar no proprio filme;
- um voto por semana por user.

## Admin

Pagina:

```text
/admin
```

O frontend chama `/auth/me` e redireciona se o user nao for admin.

### Endpoints admin de semanas

```http
GET    /admin/weeks/current
GET    /admin/weeks?page=1&limit=50
POST   /admin/weeks
DELETE /admin/weeks/{week_id}
POST   /admin/weeks/{week_id}/start-voting
POST   /admin/weeks/{week_id}/stop-voting
POST   /admin/weeks/{week_id}/close
POST   /admin/weeks/{week_id}/open
POST   /admin/weeks/{week_id}/winner
```

Operacoes:

- criar semana;
- abrir/fechar semana;
- iniciar/parar votacao;
- fechar semana e calcular vencedor;
- reabrir semana;
- apagar semana;
- definir vencedor manualmente.

### Endpoints admin de filmes

```http
POST   /admin/weeks/{week_id}/films
PATCH  /admin/films/{film_id}
DELETE /admin/films/{film_id}
POST   /admin/films/{film_id}/rematch
GET    /admin/films/needs-review
```

Operacoes:

- adicionar filme manualmente;
- editar filme;
- apagar filme;
- refazer matching TMDB;
- listar filmes que precisam de revisao.

### Sync Letterboxd de todos

Endpoint:

```http
POST /admin/letterboxd/sync-all?limit=50
Authorization: Bearer <token_admin>
```

Pagina admin:

- secao `Letterboxd`;
- botao `Sincronizar todos`;
- area de status com resumo.

Comportamento:

- seleciona users com `letterboxd_username`;
- processa sequencialmente;
- limite por pedido, default 50, maximo 100;
- nao apaga entradas existentes antes do sync em massa;
- devolve resumo por user.

Resposta:

```json
{
  "ok": true,
  "attempted": 3,
  "synced_total": 42,
  "errors": 0,
  "started_at": 123,
  "finished_at": 124,
  "results": [
    {
      "user_id": 1,
      "username": "rita",
      "letterboxd_username": "rita",
      "synced": 12,
      "error": null,
      "letterboxd_synced_at": 123
    }
  ]
}
```

## TMDB

Usado para:

- procurar filmes;
- obter poster;
- obter ano canonico;
- obter `tmdb_id`;
- avaliar match automatico.

Funcoes principais:

- `tmdb_search_candidates`
- `pick_best_tmdb_match`

Endpoint de pesquisa:

```http
GET /search/movies?q=<texto>&page=1
```

Usado pela pagina `/watch`.

Matching:

- usa RapidFuzz;
- compara titulo submetido com `title` e `original_title`;
- considera ano;
- calcula `match_score`;
- marca `needs_review` se a confianca for baixa.

## Letterboxd

### Ligar username

Endpoint:

```http
PATCH /auth/letterboxd
Authorization: Bearer <token>
```

Body:

```json
{
  "letterboxd_username": "username"
}
```

Ao ligar:

- guarda username;
- faz sync inicial;
- tenta descobrir avatar;
- guarda entradas RSS na tabela `letterboxd_entries`.

### Sync individual

Endpoint:

```http
POST /auth/letterboxd/sync
Authorization: Bearer <token>
```

Este endpoint apaga as entradas existentes do user e volta a sincronizar.

### Sync interno

Funcao:

```text
fetch_and_sync_letterboxd(db, user)
```

Passos:

1. le username Letterboxd;
2. pede RSS;
3. tenta ler avatar da pagina publica;
4. parseia XML;
5. pre-carrega entradas existentes do user;
6. pre-carrega lookup de filmes locais com `tmdb_id`;
7. insere/atualiza entradas;
8. atualiza `letterboxd_synced_at`;
9. faz commit.

Limites:

- 500 entradas existentes por user;
- 1000 filmes no lookup TMDB local.

### Watchers de um filme

Endpoint:

```http
GET /letterboxd/film/{tmdb_id}?limit=100
```

Devolve membros que viram aquele filme, com:

- user;
- letterboxd username;
- avatar;
- rating;
- watched_date;
- url;
- rewatch.

Usado nas cards da semana e na secao "visto pelo clube".

### Membros com Letterboxd

Endpoint:

```http
GET /letterboxd/members?limit=100
```

Devolve membros e metadata Letterboxd.

## Reacoes

Emojis permitidos no backend:

```text
👍
😐
67
🇮🇱
```

Endpoints:

```http
GET  /films/{film_id}/reactions
GET  /films/{film_id}/reactions/me
POST /films/{film_id}/reactions
GET  /films/{film_id}/reactions/detail
```

Comportamento:

- user tem no maximo uma reacao por filme;
- clicar no mesmo emoji remove a reacao;
- clicar noutro troca a reacao;
- contagens sao agregadas em SQL.

## Chat

Endpoints:

```http
GET    /weeks/{week_id}/chat?limit=50
GET    /weeks/{week_id}/chat?since_id=123&limit=50
POST   /weeks/{week_id}/chat
DELETE /chat/{message_id}
```

Regras:

- qualquer pessoa pode ler chat;
- so users autenticados podem postar;
- mensagem maximo 500 caracteres;
- user pode apagar a sua mensagem;
- admin pode apagar qualquer mensagem.

Frontend:

- abre painel lateral;
- primeira leitura traz ultimas 50 mensagens;
- polling a cada 12 segundos;
- polling incremental com `since_id`;
- mantem no maximo 100 mensagens em memoria no cliente.

## Perfis

Pagina:

```text
/profile/{username}
```

API:

```http
GET /users/{username}/profile
```

Devolve:

- user publico;
- estatisticas;
- rank leaderboard;
- contagens de reacoes dadas;
- filmes submetidos;
- ultimas entradas Letterboxd.

Estatisticas:

- filmes submetidos;
- filmes vencedores;
- votos dados;
- reacoes dadas;
- win rate;
- rank.

## Leaderboard

Pagina:

```text
/leaderboard
```

API:

```http
GET /api/leaderboard
```

Ordenacao:

1. mais filmes ganhos;
2. maior win rate;
3. mais filmes submetidos.

O endpoint usa agregacoes SQL e cache curta.

## Frontend por pagina

### `/`

Ficheiros:

- `frontend/index.html`
- `frontend/app.js`

Mostra:

- semana atual;
- filmes;
- botoes de voto;
- formulario de submissao;
- reacoes;
- watchers Letterboxd;
- chat;
- auth;
- popup de perfil/Letterboxd;
- secao "visto pelo clube".

Se a semana aberta tiver `theme = portugal`, o backend serve `portugal.html`.

### `/portugal`

Ficheiros:

- `frontend/portugal.html`
- `frontend/portugal.js`
- `frontend/portugal.css`

E uma variante visual/tematica da pagina principal.

### `/archive`

Ficheiros:

- `frontend/archive.html`
- `frontend/archive.js`

Vistas:

- arquivo;
- Hall of Fame;
- cinema.

Usa:

- `/weeks?limit=100`;
- `/weeks/cinema?limit=100`.

### `/admin`

Ficheiros:

- `frontend/admin.html`
- `frontend/admin.js`

Permite:

- gerir semana atual;
- criar semana;
- adicionar filme;
- rever matches TMDB;
- sincronizar todos os Letterboxd;
- apagar/editar/fechar/reabrir.

### `/leaderboard`

Ficheiros:

- `frontend/leaderboard.html`
- `frontend/leaderboard.js`

Mostra:

- podium;
- tabela de ranking;
- links para perfis.

### `/profile/{username}`

Ficheiros:

- `frontend/profile.html`
- `frontend/profile.js`

Mostra:

- avatar;
- rank;
- estatisticas;
- filmes submetidos;
- entradas Letterboxd.

### `/watch`

Ficheiros:

- `frontend/watch.html`
- `frontend/watch.js`

Permite:

- pesquisar filmes via TMDB;
- abrir player/modal de visualizacao quando aplicavel.

## Service Worker

Ficheiro:

```text
frontend/sw.js
```

Responsabilidades:

- cache de assets estaticos;
- estrategia especifica para alguns requests;
- evita cache agressiva de rotas dinamicas como auth/chat/API.

## Egress e performance

O estado atual ja inclui varias protecoes para reduzir trafego com Supabase/Postgres:

- endpoints de listas paginados;
- limites maximos;
- queries com colunas projetadas;
- agregacoes SQL em vez de carregar rows completas;
- cache curta em endpoints publicos;
- cache no frontend para chamadas Letterboxd repetidas;
- chat incremental;
- rate limiting;
- indices para queries frequentes.

Endpoints mais sensiveis a egress:

- `/weeks`
- `/weeks/current`
- `/weeks/{week_id}/chat`
- `/letterboxd/film/{tmdb_id}`
- `/api/leaderboard`
- `/users/{username}/profile`
- `/admin/letterboxd/sync-all`

## Logs e diagnostico

O backend regista:

- requests HTTP;
- respostas DB em endpoints importantes;
- tamanho aproximado de payload;
- inicio de sync Letterboxd admin por user.

Logger usado:

```text
cinema_club.egress
```

Mensagens de DB incluem:

```text
path
purpose
rows
approx_payload_bytes
```

## Comandos uteis

Instalar dependencias:

```bash
cd backend
pip install -r requirements.txt
```

Aplicar migracoes:

```bash
cd backend
alembic upgrade head
```

Correr backend local:

```bash
cd backend
uvicorn app.main:app --reload
```

Criar admin:

```bash
cd backend
python create_admin.py
```

Checks de sintaxe usados:

```bash
python -m py_compile backend/app/main.py backend/app/db.py backend/app/models.py
node --check frontend/app.js
node --check frontend/archive.js
node --check frontend/profile.js
node --check frontend/admin.js
```

## Deploy

Antes/depois de deploy:

1. garantir `DATABASE_URL`;
2. garantir `TMDB_API_KEY`;
3. instalar dependencias;
4. correr `alembic upgrade head`;
5. iniciar app com Uvicorn/Gunicorn conforme plataforma;
6. validar `/health`;
7. validar login;
8. validar `/weeks/current`;
9. validar pagina `/admin`;
10. observar Supabase Usage e logs.

Endpoint de health:

```http
GET /health
```

Resposta esperada:

```json
{"ok": true}
```

## Pontos de atencao

### Cache em memoria

Boa para um processo simples.

Se houver varios workers:

- cada worker tera cache propria;
- invalidacao nao e global;
- considerar Redis/Upstash.

### Rate limiting em memoria

Tambem e por processo.

Se houver varios workers ou varias instancias:

- limites nao sao globais;
- considerar middleware externo, proxy ou Redis.

### Letterboxd

O Letterboxd nao e uma API oficial neste fluxo; usa RSS e HTML publico.

Pode falhar por:

- username errado;
- RSS indisponivel;
- HTML mudado;
- timeout;
- rate limiting externo.

### Supabase e pooler

Mesmo com queries otimizadas, e importante observar:

- numero de requests;
- bots;
- refreshs repetidos;
- endpoints admin usados em excesso;
- deploy com varios workers.

### Admin sync all

O sync all e manual e sequencial.

Nao deve ser carregado muitas vezes seguidas, porque faz chamadas externas ao Letterboxd e leituras/escritas na DB.

## Checklist de entendimento rapido

Se fores mexer no projeto, lembra:

- `main.py` tem quase toda a logica backend.
- `models.py` define o schema ORM.
- Alembic gere schema real.
- Frontend nao usa framework.
- Auth e por bearer token guardado em localStorage.
- Submitter/voter usam `user.id` como string.
- TMDB e usado para matching e posters.
- Letterboxd fica cacheado em `letterboxd_entries`.
- Chat e por semana.
- Admin e protegido por `is_admin`.
- Egress foi uma preocupacao central, por isso evita endpoints sem `limit`.

## Melhorias futuras recomendadas

- separar routers FastAPI por dominio;
- mover auth para modulo proprio;
- criar camada service para Letterboxd/TMDB;
- adicionar testes automatizados;
- adicionar rate limit persistente;
- usar cache externa se houver varios workers;
- adicionar paginacao real no UI do arquivo;
- adicionar timestamps `created_at/updated_at` em Week/Film/Vote;
- substituir ranking manual por query SQL/window function;
- adicionar dashboard interno de usage por endpoint;
- rever encoding/mojibake em alguns ficheiros antigos.
