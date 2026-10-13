# Edição Halloween — revisão local

Pré-visualização: **http://127.0.0.1:8013/preview?theme=halloween**

O servidor usa exclusivamente `.local/halloween/preview.db` (SQLite), criado vazio.
Não foram criadas semanas. Nenhuma base de dados de produção é usada por este processo.
Não foi feito push, merge ou deploy.

## Experimentar

- Vencedor: `/preview?theme=halloween&demo=1&stage=winner`
- Submissões: `/preview?theme=halloween&demo=1&stage=submissions`
- Votação: `/preview?theme=halloween&demo=1&stage=voting`
- Visual normal: `/preview?theme=&demo=1`
- Italian e Netflix: substituir `theme=halloween` por `theme=italian` ou `theme=netflix`.

Os dados de demonstração só aparecem em `/preview`, com um aviso visível.
O servidor devolve fixtures de leitura: filmes reais, votos fictícios e um vencedor
de exemplo. Não são resultados do clube. Os identificadores são negativos para
evitar colisões com registos reais. Votos, submissões e reações de demonstração
são recusados antes do envio. A autenticação mantém o fluxo existente e, neste
servidor, só usa a base SQLite local. A ficha do filme usa os dados disponíveis,
sem inventar sinopses, elenco ou classificações.

Com semanas locais existentes, `/preview?theme=halloween` usa os dados reais
locais. `demo=1` força a demonstração; `demo=0` desativa-a. O botão
**Pré-visualizar** no admin usa o campo `newWeekTheme` e não chama `/admin/weeks`.
Quando for decidido publicar, a criação normal de uma semana com
`theme: "halloween"` usa o campo `Week.theme` existente, sem migração.

Para voltar a arrancar, executar na raiz:

```powershell
.\scripts\start_halloween_preview.ps1
```

O script define explicitamente `DATABASE_URL` antes de importar o backend e
escuta apenas em `127.0.0.1:8013`. Os ficheiros de `.env` não substituem esta URL.
Se o servidor já estiver ativo, não iniciar uma segunda instância na mesma porta.

## Composição e implementação

As referências fornecidas orientaram o preto de tinta, o laranja intenso, a
hierarquia tipográfica dos flyers, os retratos contrastados e a serif de posters
clássicos. A edição usa `#151512`, `#F4511E` e `#EEEBDD`, sem acrescentar slogans
ou datas. A fonte condensada é servida localmente.

O masthead ocupa uma linha em desktop e duas em mobile, com um “de” em serif. O 67 mantém os dois grupos
animados e a área de hover estacionária, com acabamento em laranja e creme.
Nosferatu ocupa um espaço reservado no cabeçalho da seleção; o Fantasma da Ópera
aparece numa divisória. São retratos editoriais em duotone, com enquadramentos
apertados, não recortes com transparência. Nenhum deles é transformado em candidato
ou vencedor. As decorações têm `aria-hidden` e `pointer-events: none`.

O vencedor mantém título, ano, realizador, poster e o backdrop escolhido pelo
sistema existente de TMDB. A edição só modifica a composição e aplica um filtro
de impressão à fotografia. Os posters dos candidatos recuperam a cor original
no hover ou foco para facilitar a identificação. As imagens têm dimensões ou
áreas reservadas. Não há som, flashes ou animações decorativas contínuas.

O CSS está isolado em `frontend/static/css/themes/halloween.css`, importado
depois de `chrome-edition.css`. A função `applyTheme()` remove classes, retratos,
divisórias, bandeiras, marcas Netflix e a janela italiana ao mudar ou limpar o
tema. Um parâmetro `theme=` vazio permite regressar explicitamente ao visual normal.
O cache do service worker foi atualizado; respostas `/preview` não são guardadas.

## Origem dos assets

Obtidos para esta revisão em 13 de outubro de 2026. Os JPEG são cópias dos
ficheiros originais; o duotone, a retícula e os recortes são feitos em CSS.

| Asset local | Origem e indicação da fonte |
| --- | --- |
| `frontend/static/images/halloween/nosferatu.jpg` | [Max Schreck como Count Orlok, Nosferatu (1922), Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Max_Schreck_as_Count_Orlok_in_Nosferatu_%E2%80%93_Eine_Symphonie_des_Grauens_(1922).jpg). Fotograma creditado a F. W. Murnau; a página identifica-o como domínio público, com etiquetas PD-old-75-expired e Public Domain Mark. |
| `frontend/static/images/halloween/phantom.jpg` | [Lon Chaney em The Phantom of the Opera (1925), Wikimedia Commons](https://commons.wikimedia.org/wiki/File:ChaneyPhantomoftheOpera.jpg). Scan de fotograma, fonte indicada Doctor Macro; a página identifica-o como domínio público nos EUA (PD-US-expired). |
| `frontend/static/images/halloween/six-caps-400.ttf` | [Six Caps, Google Fonts](https://github.com/google/fonts/tree/main/ofl/sixcaps). SIL Open Font License 1.1; cópia de `six-caps-OFL.txt` na mesma pasta. A revisão tipográfica usa o peso regular real (400), com síntese de peso desativada e sem compressão horizontal. |
| `frontend/static/images/halloween/barlow-condensed-900.ttf` | [Barlow Condensed, Google Fonts](https://github.com/google/fonts/tree/main/ofl/barlowcondensed). Mantida nos numerais e elementos secundários existentes; SIL Open Font License 1.1, em `OFL.txt`. |
| Imagens dos filmes de demonstração | TMDB: [Alien, 348](https://www.themoviedb.org/movie/348-alien), [The Thing, 1091](https://www.themoviedb.org/movie/1091-the-thing), [Psycho, 539](https://www.themoviedb.org/movie/539-psycho), [Halloween, 948](https://www.themoviedb.org/movie/948-halloween). Os URLs de posters e do backdrop de Alien estão em `backend/app/preview_demo.py` e são servidos pelo CDN de imagens do TMDB; não são retratos decorativos nem imagens geradas. |

As referências anexadas pelo utilizador foram analisadas visualmente e não são
redistribuídas como assets do site.

## Verificação

Testes de rotas, assets, sintaxe CSS, persistência de `Week.theme` e isolamento
dos dados de demonstração:

```powershell
cd backend
..\.venv\Scripts\python.exe -m unittest discover -s tests -p test_frontend.py
```

Revisão no Chromium com Playwright instalado, usando apenas o servidor local:

```powershell
python scripts/check_halloween_preview.py
python scripts/check_halloween_interactions.py
```

As capturas ficam em `.local/halloween/`, com nomes como `winner-1440.png`,
`winner-390.png` e `winner-dark-390.png`. O script verifica desktop, tablet e
mobile (1440, 768, 390 e 320 px), três fases, claro/escuro, carregamento de imagens,
overflow, áreas clicáveis, fichas, login, submissões, chat, reações, teclado, limpeza
de temas, o hover do 67 e movimento reduzido. O teste do admin interceta as leituras
de autenticação e verifica que a pré-visualização não envia pedidos de escrita.

Verificação concluída: 16 testes de frontend passaram. Foram também verificados
os pedidos de votação, submissão e chat com uma sessão autenticada simulada,
intercetando todas as escritas no browser; o campo `halloween` enviado pelo admin,
as reações, a ficha original do vencedor e a posição personalizada do backdrop
foram confirmados. O texto e os controlos amostrados, em claro e escuro, tiveram
contraste mínimo de 5,26:1 após terminar a transição de tema. A base local continua
sem semanas, filmes, votos ou mensagens de chat.

## Ajuste tipográfico

O masthead e os títulos de secção usam agora Six Caps Regular (400), uma família
naturalmente alta e estreita. Tamanho, entrelinha e espaçamento foram ajustados
sem `scaleX`, contorno ou síntese de peso. O “de” mantém Georgia itálica, mais pequeno;
o título do vencedor e “Edição Halloween” mantêm a serif expressiva. Textos pequenos
e botões continuam em Archivo. Barlow Condensed permanece nos numerais existentes.
Composição, paleta, fotografias e funcionalidades não foram alteradas nesta revisão.

Capturas desta revisão: `.local/halloween/typography-1440-light.png`,
`typography-390-light.png` e `typography-390-dark.png`. O encaixe foi verificado
em 1440, 768, 390 e 320 px, incluindo o carregamento da fonte e a ausência de
scroll horizontal. O cache foi atualizado para disponibilizar a nova fonte local.

## Reequilíbrio do masthead

Em desktop, “CLUBE de CINEMA” ocupa uma linha, com o 67 ao lado. O tamanho da fonte
acompanha a largura disponível; o espaço vertical e o padding foram reduzidos.
Em mobile (até 560 px), “CLUBE de” e “CINEMA” formam duas linhas com espaçamento
próprio. A família Six Caps, as cores, a navegação e a animação do 67 mantêm-se.

Capturas atuais: `.local/halloween/masthead-1440.png` e `masthead-390.png`.
Foram verificados 320, 390, 560, 561, 768, 801, 1024, 1280 e 1440 px, sem overflow
horizontal nem sobreposição entre o nome e o 67.
