# Deploy - Clube de Cinema

Guia pratico para publicar a app FastAPI + frontend estatico.

## Variaveis obrigatorias

```text
DATABASE_URL
TMDB_API_KEY
```

`DATABASE_URL` deve apontar para a base de dados de producao, por exemplo Supabase/Postgres.

`TMDB_API_KEY` e usada para pesquisa, posters e matching de filmes.

## Instalar dependencias

```bash
cd backend
pip install -r requirements.txt
```

## Migracoes

Antes de iniciar a app numa base nova, ou depois de deploy com migracoes novas:

```bash
cd backend
alembic upgrade head
```

Antes de migracoes grandes, faz backup da base de dados.

## Start command

Exemplo simples:

```bash
cd backend
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Em Render, um start command comum e:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Se a plataforma nao definir `PORT`, usa uma porta fixa:

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Render Free

No plano gratuito, o servidor pode adormecer quando nao ha trafego.

E esperado que o primeiro request depois de algum tempo demore mais. O frontend mostra uma mensagem amigavel:

```text
A acordar o servidor... isto pode demorar uns segundos.
```

## Validacao apos deploy

1. Abrir:

```http
GET /health
```

Resposta esperada:

```json
{"ok": true}
```

2. Confirmar que a homepage abre:

```text
/
```

3. Testar:

```http
GET /weeks/current
```

4. Fazer login.

5. Abrir:

```text
/admin
```

6. Confirmar que users nao-admin sao bloqueados/redirecionados.

7. Confirmar que o arquivo carrega por paginas:

```text
/archive
```

8. Se existir Letterboxd ligado, testar uma sync manual.

## Monitorizacao

Depois de deploy, verificar:

- logs da aplicacao;
- erros 500;
- respostas 429 por rate limit;
- logs `db_response`;
- Supabase Usage, especialmente `Shared Pooler Egress`.

Endpoints mais importantes para vigiar:

- `/weeks/current`
- `/weeks`
- `/weeks/{week_id}/chat`
- `/letterboxd/activity`
- `/letterboxd/film/{tmdb_id}`
- `/api/leaderboard`
- `/users/{username}/profile`
- `/admin/letterboxd/sync-all`

## Supabase e egress

A app usa:

- paginacao;
- limites;
- cache curta;
- SQL aggregation;
- chat incremental;
- rate limiting;
- indices para queries frequentes.

Mesmo assim, se o egress subir:

1. verificar se ha bots ou refreshs agressivos;
2. verificar endpoints mais chamados nos logs;
3. evitar clicar repetidamente em sync Letterboxd global;
4. confirmar que o frontend nao esta em loop;
5. considerar cache externa se houver varios workers.

## Rollback

Rollback de codigo:

```bash
git revert <commit>
git push
```

Rollback de plataforma:

- usar a funcionalidade de rollback do Render/GitHub deploy, se disponivel.

Rollback de migracoes:

```bash
cd backend
alembic downgrade -1
```

Usar downgrade com cuidado. Fazer backup antes de mexer em schema em producao.

## Checklist rapido

- `DATABASE_URL` definido.
- `TMDB_API_KEY` definido.
- Dependencias instaladas.
- `alembic upgrade head` executado.
- `/health` ok.
- Login ok.
- `/weeks/current` ok.
- `/admin` protegido.
- Logs sem erros inesperados.
- Supabase egress monitorizado apos deploy.
