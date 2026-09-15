# Frontend

HTML, CSS e JavaScript sem etapa de build. O FastAPI serve as páginas e os assets.

```text
frontend/
  pages/                  # HTML das páginas
  static/
    css/
      styles.css          # Entrada: importa os módulos pela ordem da cascata
      base.css            # Variáveis, temas claro/escuro e componentes de base
      components/         # Chat, reações, Letterboxd, etc.
      pages/              # Perfil, cinema e trailers
      themes/             # Italian, Netflix e Portugal
      responsive.css      # Ajustes para ecrãs pequenos
      utilities.css       # Superfícies e utilitários partilhados
    js/
      pages/              # Código de cada página; app.js corresponde à semana
      shared/             # Código transversal, como o aviso de servidor a acordar
    images/               # Imagens referenciadas por páginas ou temas
    icons/                # Favicons e ícones da PWA
    manifest.json
    sw.js
```

## Onde mexer

O visual claro e rosa está em `static/css/editorial.css`, carregado depois dos
módulos existentes. Usa Barlow, botões retangulares e uma grelha de seis posters
em ecrãs largos. Os módulos base continuam a suportar as funcionalidades e temas.
O comportamento partilhado da janela de submissão e da acessibilidade do chat está
em `static/js/shared/editorial.js`.

- HTML: `pages/<página>.html`.
- Comportamento: `static/js/pages/`; os scripts continuam clássicos, com `defer`.
- Visual: o módulo correspondente em `static/css/`. Preservar a ordem dos imports
  em `styles.css`, porque regras posteriores podem sobrepor regras anteriores.
- Portugal carrega também `static/css/themes/portugal.css` depois do CSS comum.
- Rotas HTML e escolha do tema da semana: `backend/app/frontend.py`.
- API e regras de negócio: `backend/app/main.py`.

As URLs públicas das páginas continuam iguais (`/`, `/archive`, `/watch`, etc.).
Os assets usam `/static/css/…`, `/static/js/…`, `/static/images/…` e `/static/icons/…`.
O service worker continua disponível em `/sw.js`, com âmbito na raiz do site.
Ao mudar os assets em cache, atualizar a versão e a lista `STATIC` nesse ficheiro.

## Fichas dos filmes

Os botões «Saber mais» abrem uma ficha dentro do site, com sinopse, duração,
géneros, realização e elenco. A ligação para o Letterboxd fica dentro da ficha.
Os posters do destaque da semana também abrem esta janela.

- Comportamento: `static/js/shared/movie-details.js`.
- Visual: `static/css/components/movie-details.css`.
- Dados: `backend/app/movie_details.py`, através de `/films/{id}/details`
  para submissões do clube e `/movies/{tmdb_id}/details` para resultados TMDB.

Para obter informação real localmente, copiar `backend/.env.example` para
`backend/.env`, preencher `TMDB_API_KEY` e reiniciar o servidor. A chave fica
no backend. Sem chave ou durante uma falha do serviço, a ficha conserva os
dados do clube e a ligação para o Letterboxd. Os testes usam respostas simuladas
e não precisam de uma chave.

## Experimentar sem publicar

Trabalhar numa branch de desenvolvimento e executar o servidor localmente seguindo
o README da raiz. Usar uma base de dados de desenvolvimento, sem configurar
`DATABASE_URL` com a base de produção. O SQLite local é o comportamento por defeito.

Uma branch local não altera o site publicado. Para testar noutro dispositivo ou
partilhar uma versão de teste, configurar uma instância separada com a sua própria
base de dados. Uma branch, por si só, não cria uma instância privada.

`/preview` serve a página neutra e `/preview?theme=netflix` permite ver esse tema.
Estas rotas continuam a usar os assets e a API da mesma instância: não constituem
um ambiente isolado nem uma área privada.

## Validação

Os prazos são configurados na administração. A página da semana mostra apenas o
prazo da fase atual e atualiza-se nas transições previstas. As horas são sempre
de Lisboa, sem etiquetas de fuso horário. O backend aplica os
limites mesmo que a página esteja desatualizada. Durante a votação, qualquer
membro autenticado e sem restrição pode votar sem ter submetido um filme.

Na raiz, com o ambiente virtual ativo:

```powershell
python -m pip install -r backend/requirements-dev.txt
cd backend
python -m unittest discover -s tests -v
```

Executar a suite num processo novo. Usa SQLite temporário e testa páginas, escolha
de temas, referências a assets, imports CSS e respostas do service worker.

## Limpeza de imagens

Foram removidas por não terem referências no código: `cr7.png`, `cr77.png`,
`estreladamadora.png`, `felix.png`, `kikas.png`, `paulomoreira.png`, `portugal.gif`
e `ronaldo.gif` (5 945 849 bytes). As imagens usadas nos temas sazonais foram mantidas.
Os ficheiros removidos continuam recuperáveis no histórico Git.

Este refactoring organiza ficheiros e separa o routing HTML. A lógica existente de
`app.js` mantém-se; a divisão dessa lógica em módulos funcionais é trabalho distinto.
