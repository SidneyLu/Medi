# EDBuy RAG Prototype

Dockerized MVP for digital product competitor benchmarking with:

- FastAPI API
- Next.js frontend
- PostgreSQL for structured truth and timeline data
- ChromaDB for unstructured retrieval
- LangChain + DashScope compatible models for answer generation

## Quick start

1. Copy `.env.example` to `.env`.
2. Replace `DASHSCOPE_API_KEY` with a valid key.
3. Run:

```bash
docker compose up --build
```

## URLs

- Frontend: `http://localhost:3000/products`
- API docs: `http://localhost:8000/docs`
- ChromaDB: `http://localhost:8001`

## Seed import

The prototype ships with example phone data under [data/seed](/D:/EDBuy/data/seed) and processed sample documents under [data/processed](/D:/EDBuy/data/processed).

Trigger seed import after startup:

```bash
curl -X POST http://localhost:8000/admin/seed-import
```

Or from the worker container:

```bash
docker compose exec worker python /workspace/worker/runner.py import-seed
```

## Data contract

Expected input files are documented in [DATA.md](/D:/EDBuy/DATA.md). The importer supports the documented CSV files plus optional extra columns in `product_sku_seed.csv` for prototype-friendly snapshots such as `current_price`, `chipset`, `ram`, and `selling_points`.
