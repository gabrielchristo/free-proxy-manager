# test-client

Cliente Python para validar proxies do **free-proxy-manager** acessando uma URL externa (default: Google).

## O que faz

1. **10×** `GET /proxy` — cada proxy retornado é testado contra a URL alvo.
2. **1×** `GET /proxies` — busca até 100 candidatos `protocol=https`, `status=HEALTHY`, `anonymous=true`, ordena por nível de anonimidade (`elite` / `high_anonymous` > `anonymous`) e score, pega **10** e testa cada um.

Total: **20 probes** com relatório individual (OK/FAIL, tempo, HTTP status, metadados).

## Setup

```bash
cd test-client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Certifique-se de que o **free-proxy-manager** está rodando (ex.: `http://localhost:8000`).

## Uso

```bash
python main.py
```

Opções úteis:

```bash
python main.py --manager-url http://localhost:8000 --target-url https://www.google.com/
python main.py --json report.json
python main.py --concurrency 3 --timeout 20
```

Variáveis de ambiente:

| Variável | Default |
|----------|---------|
| `PROXY_MANAGER_URL` | `http://localhost:8000` |
| `TEST_TARGET_URL` | `https://www.google.com/` |
| `TEST_TIMEOUT` | `15` |

## Saída

Relatório no terminal com **diagnóstico do pool** antes dos testes (`/health`, contagem por status, quantos batem no filtro da lista).

Se não houver proxies `HEALTHY`, os 10 slots de `/proxies` viram **1 linha SKIP** (não 10 repetidas).

### Pool vazio / checker ainda aquecendo

`/proxy` só devolve `HEALTHY`. Se o checker ainda não validou ninguém:

```bash
python main.py --wait-seconds 300
```

Aguarda até aparecer pelo menos 1 `HEALTHY` (poll a cada 5s).

Exit codes: `0` = todos os testes executados passaram; `1` = algum falhou; `2` = nenhum teste executado.
