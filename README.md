# Revisão de roteiro

API Python 3.12 e SQLite, só biblioteca padrão. Guarda versões e revisões sem apagar o histórico. Cada entrada em `versions` expõe `state`: `pending_review` sem revisão, ou a decisão histórica `changes_requested`/`approved`; criar uma versão nova não muda o estado das antigas.

## Rodar e testar

```sh
python3.12 main.py
python3.12 -m unittest discover -s tests -v
```

Escuta em `127.0.0.1:8000`. `PORT` muda a porta; `SCRIPT_REVIEW_DB` muda o banco, por padrão `data/review.sqlite3`.

## API e exemplos

`POST /scripts` com `{"creator_id":"creator-17","content":"Abertura\nOferta"}` cria roteiro e versão 1. Resposta 201 (trecho): `{"script":{"id":"id-gerado","state":"pending_review","current_version":1}}`.

`POST /scripts/{id}/reviews` com `{"decision":"changes_requested","reason":"Explique a oferta.","deadline_date":"2026-10-12"}` retorna 200 (trecho): `{"script":{"state":"changes_requested","change_request":{"reason":"Explique a oferta.","deadline_date":"2026-10-12","status":"open"}}}`. Prazo é dia civil em America/Sao_Paulo: seu último instante ainda vale. Motivo vazio, prazo ausente, inválido ou passado retorna 400. Texto com surrogate isolado também retorna 400, sem escrita parcial; Unicode válido é preservado.

`POST /scripts/{id}/versions` com `{"content":"Nova versão"}` retorna 201 com `current_version: 2` e estado `pending_review`. `POST /scripts/{id}/reviews` com `{"decision":"approved"}` retorna 200 e estado terminal `approved`. Depois disso, nova versão ou revisão válida retorna 409. `GET /scripts/{id}` retorna a visão completa, incluindo versões, reviews, timestamps e pedido atual; ausente retorna 404.

## Escolhas e limites

Versão nova só é aceita em changes_requested e até o prazo; pedido vencido aparece como expired, mas não pode ser reaberto nesta demo. A marca só revisa pending_review. Essas restrições adicionais são escolhas reversíveis; eu definiria com produto a recuperação após expiração.

Escritas usam BEGIN IMMEDIATE e leituras usam snapshot. Carregar V versões e R revisões custa O(V+R) em tempo e memória. Ficaram fora autenticação, papéis, UI, upload, serviços externos e migrações de schema. O fuso depende da base IANA instalada.

Veja [AI-USAGE.md](AI-USAGE.md) para uso de IA e revisão e [REVIEW-NOTE.md](REVIEW-NOTE.md) para o roteiro de avaliação.
