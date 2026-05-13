# Telegram Finder SaaS

Interface web em Flask para buscar grupos e canais públicos do Telegram usando Telethon, com filtros avançados, histórico local, exportação de resultados e painel de debug visual.

> Status: projeto funcional em estágio inicial/experimental. Serve bem como ferramenta local ou base para um SaaS, mas ainda precisa de ajustes de segurança, autenticação e configuração por ambiente antes de produção.

---

## O que este projeto faz

O **Telegram Finder SaaS** permite pesquisar grupos e canais públicos do Telegram por palavra-chave e visualizar os resultados em uma interface web limpa, com Bootstrap.

Ele foi pensado para evitar aquela caça manual no Telegram, onde você pesquisa, abre um grupo, fecha outro, perde o fio da meada e no fim parece que está minerando carvão com colher de sobremesa.

Com ele você pode:

- Buscar grupos e canais públicos por termo.
- Filtrar por idioma, tipo, quantidade mínima/máxima de membros e verificação.
- Excluir grupos/canais nos quais a conta já participa.
- Ver resultados em cards com título, tipo, membros e link direto para o Telegram.
- Salvar automaticamente o histórico das buscas em SQLite.
- Reabrir buscas antigas.
- Exportar resultados em CSV, JSON ou TXT.
- Ver um painel de debug formatado com contagens, filtros aplicados, métodos usados e avisos.

---

## Principais recursos

### Busca no Telegram

O projeto usa a biblioteca **Telethon** para conectar em uma conta Telegram e executar buscas públicas.

Atualmente ele tenta encontrar resultados por três caminhos:

1. **Busca global de mensagens/chats** usando `SearchGlobalRequest`.
2. **Busca de contatos/chats** usando `contacts.SearchRequest`.
3. **Variações de username** com base no termo pesquisado, como versões com `_`, sem espaço e, em português, sufixos como `_br` e `_brasil`.

Os resultados são deduplicados por ID e ordenados por número de membros.

---

## Filtros disponíveis

Na tela de busca, o usuário pode configurar:

- **Telefone Telegram** usado para autenticação.
- **Termo da busca**.
- **Idioma**: qualquer, português, inglês ou espanhol.
- **Tipo**: todos, grupos ou canais.
- **Mínimo de membros**.
- **Máximo de membros**.
- **Limite de resultados**.
- **Excluir grupos em que já participo**.
- **Apenas verificados**.

O filtro de idioma usa `langdetect` com base no título e descrição do grupo/canal, quando houver texto suficiente para análise.

---

## Histórico local

Cada busca é salva em um banco SQLite local:

```text
data/history.db
```

A tabela `searches` guarda:

- Data da busca.
- Telefone usado.
- Termo pesquisado.
- Total de resultados finais.
- Total bruto antes dos filtros.
- Total filtrado.
- JSON de debug.
- JSON dos resultados.

Isso permite abrir buscas antigas pela tela de histórico sem precisar consultar o Telegram novamente.

---

## Exportação

Os resultados da última busca podem ser exportados em:

- CSV: `/export/csv`
- JSON: `/export/json`
- TXT: `/export/txt`

O TXT sai formatado em colunas com título, username, número de membros e link.

---

## Painel de debug

O projeto inclui um painel de debug dentro da própria interface.

Ele mostra:

- Termo pesquisado.
- Quantidade de resultados brutos.
- Quantidade de resultados depois dos filtros.
- Quantidade de itens excluídos.
- Filtros aplicados.
- Métodos de busca que retornaram dados.
- Avisos e erros de conexão.
- Diagnóstico rápido quando a busca retorna zero.

Rotas relacionadas:

```text
/debug
/search/<id>
```

Ao abrir uma busca antiga, a interface redireciona para o dashboard com o painel de debug destacado.

---

## Estrutura do projeto

```text
telegram_searcher_saas-main/
├── app.py
├── telegram_group_searcher.py
├── requirements.txt
├── README.md
├── data/
│   └── history.db
├── static/
│   ├── css/
│   │   └── app.css
│   └── js/
│       └── app.js
└── templates/
    ├── base.html
    ├── dashboard.html
    ├── history.html
    ├── debug.html
    └── _debug_panel.html
```

---

## Tecnologias usadas

- Python
- Flask
- Telethon
- SQLite
- Bootstrap 5
- Langdetect
- HTML/CSS/JavaScript simples

---

## Como rodar localmente

### 1. Clone o repositório

```bash
git clone https://github.com/SEU_USUARIO/telegram_searcher_saas.git
cd telegram_searcher_saas
```

### 2. Crie um ambiente virtual

No Windows:

```bash
python -m venv .venv
.venv\Scripts\activate
```

No Linux/macOS:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

### 4. Configure suas credenciais do Telegram

O projeto usa `API_ID` e `API_HASH` do Telegram.

Você pode obter essas credenciais em:

```text
https://my.telegram.org/apps
```

O ideal é mover essas informações para variáveis de ambiente ou um arquivo `.env`.

Exemplo recomendado:

```env
TELEGRAM_API_ID=123456
TELEGRAM_API_HASH=sua_api_hash_aqui
TELEGRAM_PHONE=+5519999999999
FLASK_PORT=5888
```

> Atenção: não suba `API_HASH`, telefone real, banco com histórico ou arquivos `.session` para repositório público.

### 5. Rode o app

```bash
python app.py
```

Abra no navegador:

```text
http://127.0.0.1:5888
```

---

## Primeiro login no Telegram

Na primeira execução, o Telethon pode pedir autenticação da conta Telegram.

Normalmente o fluxo envolve:

1. Informar o telefone.
2. Receber um código no Telegram.
3. Digitar o código no terminal.
4. Gerar um arquivo de sessão local.

Depois disso, a sessão pode ser reutilizada.

---

## Rotas principais

| Rota | Função |
|---|---|
| `/` | Dashboard principal com formulário de busca e resultados |
| `/history` | Histórico das buscas salvas |
| `/debug` | Painel de debug da última busca |
| `/search/<id>` | Abre uma busca antiga no dashboard |
| `/export/csv` | Exporta a última busca em CSV |
| `/export/json` | Exporta a última busca em JSON |
| `/export/txt` | Exporta a última busca em TXT |

---

## Pontos importantes de segurança

Antes de publicar ou transformar em SaaS real, corrija estes pontos:

### 1. Remover credenciais hardcoded

Atualmente o código define `API_ID` e `API_HASH` diretamente em `telegram_group_searcher.py`.

Isso deve virar variável de ambiente.

### 2. Remover arquivos de sessão do Git

Arquivos como este não devem estar no repositório:

```text
*.session
```

Eles representam uma sessão autenticada do Telegram. É praticamente a chave do carro. Não deixa no capô.

### 3. Remover banco local com dados reais

Evite subir:

```text
data/history.db
```

Ele pode conter termos buscados, telefone usado e resultados encontrados.

### 4. Criar `.gitignore`

Sugestão:

```gitignore
.venv/
__pycache__/
*.pyc
*.session
*.session-journal
.env
data/*.db
instance/
.DS_Store
```

### 5. Desligar debug em produção

No `app.py`, o projeto roda com:

```python
app.run(debug=True, host="127.0.0.1", port=APP_PORT)
```

Para produção, use `debug=False` e um servidor como Gunicorn/Uvicorn/Waitress, dependendo do ambiente.

---

## Limitações atuais

- Não possui login de usuários no painel web.
- Não possui painel administrativo multiusuário.
- Não possui controle de permissões.
- Usa sessão local do Telegram.
- Configurações sensíveis ainda estão no código.
- Histórico é local em SQLite.
- Exporta apenas a última busca carregada na memória da aplicação.
- A busca depende dos limites e comportamento da própria API/cliente Telegram.
- O filtro de idioma depende da qualidade do texto disponível no título/descrição.

---

## Melhorias recomendadas

Para evoluir este projeto para algo mais robusto:

- Mover configurações para `.env`.
- Criar autenticação no painel Flask.
- Separar usuários e sessões Telegram.
- Criar página de configurações.
- Adicionar paginação nos resultados.
- Adicionar busca dentro do histórico.
- Exportar buscas antigas diretamente pelo ID.
- Criar fila assíncrona para buscas maiores.
- Adicionar logs estruturados.
- Adicionar Dockerfile.
- Adicionar modo produção para Railway/Render.
- Criar testes básicos para filtros, banco e exportações.

---

## Exemplo de uso

1. Abra o dashboard.
2. Informe o telefone Telegram.
3. Digite um termo, por exemplo:

```text
python brasil
```

4. Ajuste os filtros.
5. Clique em **Buscar agora**.
6. Veja os resultados.
7. Exporte em CSV, JSON ou TXT.
8. Consulte o debug se vier zero resultado.

---

## Aviso ético

Este projeto deve ser usado apenas para buscar grupos e canais públicos, respeitando os termos do Telegram, privacidade de terceiros e leis aplicáveis.

Nada de virar vilão de filme B. Ferramenta boa é bisturi, não marreta.

---

## Licença

Defina uma licença antes de publicar oficialmente.

Sugestões comuns:

- MIT, se quiser liberar de forma simples.
- Apache 2.0, se quiser algo mais detalhado.
- Privado/proprietário, se a intenção for transformar em SaaS comercial.

---

## Resumo curto

O **Telegram Finder SaaS** é uma aplicação Flask para encontrar grupos e canais públicos do Telegram com filtros, histórico, exportação e debug visual. Ainda não está pronto para produção, mas já é uma boa base para uma ferramenta de pesquisa e descoberta de comunidades públicas.
