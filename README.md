# Telegram Finder SaaS v1.5

Interface Flask para buscar grupos/canais públicos do Telegram com filtros, histórico, exportação e debug formatado na UI.

## Rodar

```bash
pip install -r requirements.txt
python app.py
```

Abra:

```text
http://127.0.0.1:5888
```

## Exportações

- `/export/csv`
- `/export/json`
- `/export/txt`

## Debug

O debug aparece na própria interface:
- no Dashboard, abaixo dos resultados
- no menu lateral "Debug"
- ao abrir uma busca antiga pelo botão "ver"
