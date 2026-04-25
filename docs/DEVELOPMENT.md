# Development Guide

This guide is focused on local development. For cloud deployment, see [DEPLOYMENT.md](/Users/admin/PycharmProjects/PythonProject18 копія/docs/DEPLOYMENT.md).

## Prerequisites

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- GNU Make (optional)

## Recommended Local Start

```bash
docker compose up --build
```

See the detailed local runtime notes in [LOCAL_DEVELOPMENT.md](/Users/admin/PycharmProjects/PythonProject18 копія/docs/LOCAL_DEVELOPMENT.md).

## Local Process Mode (optional)

```bash
make install
make dev-backend   # terminal 1
make dev-frontend  # terminal 2
```

## Useful Commands

```bash
make help
make up
make down
make logs
make test
make lint
make format
```

## Testing and quality

```bash
make test
make lint
make format
```
