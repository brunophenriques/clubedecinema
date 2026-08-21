# Clube de Cinema

Aplicação web para gerir semanas de submissão e votação de filmes entre membros.

Consulta [read.md](read.md) para a documentação técnica completa e [DEPLOY.md](DEPLOY.md) para instruções de publicação.

## Desenvolvimento local

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn app.main:app --reload
```

Por defeito é criada uma base SQLite em `backend/cinema_club.db`. Em produção, define `DATABASE_URL` e `TMDB_API_KEY`.
