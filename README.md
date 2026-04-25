# Telegram Searcher SaaS v1.2

Interface web em Flask para buscar grupos/canais públicos no Telegram usando Telethon.

## Rodar

```bash
pip install -r requirements.txt
copy .env.example .env   # Windows PowerShell: Copy-Item .env.example .env
python app.py
```

Abra:

```text
http://127.0.0.1:5878
```

## O que mudou na v1.2

- Corrigido filtro que podia excluir resultados demais.
- Adicionado modo de busca:
  - `Públicos novos`: exclui grupos/canais onde você já participa.
  - `Públicos + meus`: não exclui seus grupos/canais.
- Adicionado painel de debug com contadores: bruto, duplicados, sem username, meus grupos removidos, filtrados.
- Busca pública usa múltiplas fontes: `SearchGlobalRequest`, `contacts.SearchRequest` e variações por username.

## Observação importante

O Telegram pode limitar resultados públicos dependendo da sessão, termo buscado, idioma, flood/rate limit e privacidade. Termos muito específicos como artista, marca ou gírias podem retornar pouco. Tente termos genéricos e desative filtros pesados.
