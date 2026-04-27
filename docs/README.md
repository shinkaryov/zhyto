# Ukraine Invest Assistant (ЖИТО)

ЖИТО is a RAG investment assistant built as:
- FastAPI backend
- React frontend
- Chroma vector store
- Azure Cosmos DB for user data
- Azure OpenAI / Foundry OpenAI for LLM + embeddings

## Supported Run Modes

1. **Cloud mode**: manual GitHub Actions deploy workflows only
2. **Local mode**: Docker Compose (`docker compose up --build`)

## Documentation Map

- Architecture: [ARCHITECTURE.md](https://github.com/shinkaryov/zhyto/blob/master/docs/ARCHITECTURE.md)
- Cloud deploy: [DEPLOYMENT.md](https://github.com/shinkaryov/zhyto/blob/master/docs/DEPLOYMENT.md)
- Local development: [LOCAL_DEVELOPMENT.md](https://github.com/shinkaryov/zhyto/blob/master/docs/LOCAL_DEVELOPMENT.md)
- Data artifact handling: [DATA_ARTIFACTS.md](https://github.com/shinkaryov/zhyto/blob/master/docs/DATA_ARTIFACTS.md)
- General development notes: [DEVELOPMENT.md](https://github.com/shinkaryov/zhyto/blob/master/docs/DEVELOPMENT.md)
