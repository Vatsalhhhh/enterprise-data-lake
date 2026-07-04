# Enterprise Data Lake

A working, end-to-end simulation of a multi-domain company data platform:
five business domains (Sales, HR, Finance, Inventory, Marketing) generate
raw data, it lands in an object-store lake, gets cataloged and cleaned,
flows into a warehouse star schema, and can be queried, visualized, and
asked cross-domain questions in plain English.

## Why this exists

Most portfolio "data lake" projects are a single Jupyter notebook that
loads a CSV. This one actually runs the full shape of a real platform
locally: a real S3-compatible object store, a real metadata catalog, real
data-quality checks, a real relational warehouse with a star schema, a
real API, and a real dashboard -- all launchable with Docker and a
handful of scripts, no cloud account required.

## Honest note on the AWS substitutions

This project is built to map directly onto an AWS data lake architecture,
but it does **not** run on AWS -- there's no AWS account involved, by
design, so anyone can clone and run it for free.

| In this repo | Stands in for | Why it's a fair substitute |
|---|---|---|
| **MinIO** (Docker) | **Amazon S3** | MinIO speaks the real S3 API. The ingestion code (`lake/ingest/land_to_lake.py`) uses `boto3` exactly as it would against real S3 -- bucket creation, `upload_file` (multipart-safe), prefix listing, `dt=`-partitioned keys. Point the `MINIO_ENDPOINT` env var at `s3.amazonaws.com` with real AWS credentials and the same code runs unmodified against S3. |
| **pandas / pyarrow / DuckDB** (`catalog/transform.py`) | **AWS Glue (PySpark ETL jobs)** | The transform logic -- schema coercion, null/dedupe/referential-integrity checks, curated Parquet output -- is the same logic a Glue PySpark job would run. At this data volume, DuckDB/pandas is a legitimate lightweight substitute for Spark; the transform functions are pure and would port to PySpark DataFrame operations with minimal changes. |
| **DuckDB catalog table** (`catalog/catalog_store.py`) | **AWS Glue Data Catalog** | Same purpose: table name, schema, partition keys, row counts, last-updated timestamp, queryable independently of the data itself. |
| **Postgres** (Docker) | **Amazon Redshift / Athena-queryable S3** | The star schema (`warehouse/schema.sql`) and cross-domain views are standard SQL; they would run as-is on Redshift, and the same curated Parquet in S3 could be queried directly via Athena without a warehouse load step at all. |
| **Streamlit** (`dashboard/app.py`) | **Power BI Desktop** | Streamlit gives a live, code-driven dashboard runnable in this environment. For anyone who wants an actual Power BI report, `dashboard/export_powerbi.py` writes clean, flat CSVs to `dashboard/exports/powerbi/` that load directly into Power BI Desktop via *Get Data > Text/CSV*. |

Nothing here claims to run on AWS. Everything here is written so that
swapping the I/O boundary (the `boto3` endpoint, the SQL dialect, the BI
tool) is the only thing that would need to change to run for real on AWS.

## Architecture

```
 ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐ ┌─────────────┐
 │    Sales    │ │     HR      │ │  Finance    │ │ Inventory   │ │ Marketing   │
 │ (generators)│ │ (generators)│ │(generators) │ │(generators) │ │(generators) │
 └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘ └──────┬──────┘
        │               │               │               │               │
        └───────────────┴───────┬───────┴───────────────┴───────────────┘
                                 ▼
                  ┌──────────────────────────────┐
                  │   MinIO (S3-compatible)      │
                  │   raw/<domain>/<dataset>/    │   <- landing zone (land_to_lake.py)
                  │   dt=YYYY-MM-DD/*.csv        │
                  └───────────────┬──────────────┘
                                  ▼
                  ┌──────────────────────────────┐
                  │  Catalog + Transform layer   │
                  │  (DuckDB catalog + pandas/   │   <- Glue-equivalent (catalog/transform.py)
                  │   pyarrow cleaning + DQ      │
                  │   checks + dedupe)           │
                  └───────────────┬──────────────┘
                                  ▼
                  ┌──────────────────────────────┐
                  │   MinIO curated/ zone        │
                  │   (Parquet, typed, deduped)  │
                  └───────────────┬──────────────┘
                                  ▼
                  ┌──────────────────────────────┐
                  │   Postgres warehouse         │
                  │   star schema: dim_date,     │   <- warehouse/load_warehouse.py
                  │   dim_department, dim_region │
                  │   + 5 domain fact tables     │
                  │   + cross-domain SQL views   │
                  └───────────────┬──────────────┘
                                  ▼
                 ┌────────────────┴────────────────┐
                 ▼                                 ▼
      ┌────────────────────┐          ┌─────────────────────────┐
      │   FastAPI (api/)    │          │   Streamlit dashboard    │
      │   /views/*          │◄────────►│   per-domain tabs +      │
      │   /analyze (LLM +   │          │   cross-domain chat tab  │
      │   deterministic     │          │   + Power BI CSV export  │
      │   fallback)         │          └─────────────────────────┘
      └────────────────────┘
```

## The engineered cross-domain story

The synthetic data isn't random noise -- there's a deliberate, discoverable
signal built in (see `generators/common.py`):

Starting **April 2024**, the **Customer Support** department in the
**NA-EAST** region ramps headcount and overtime, driving HR cost from
~$71K/month to ~$161K/month by December 2024. Starting **one quarter
later (July 2024)**, gross margin for that same department/region begins
eroding -- COGS creep plus a rise in discounted/refunded orders (support
strain leaking into customer-facing terms) push margin down even as HR
cost keeps climbing. This is exactly the kind of pattern the `/analyze`
endpoint and the dashboard's cross-domain tab are built to surface.

## Project layout

```
generators/       synthetic data generators for all 5 domains
lake/             docker-compose service definition + land_to_lake.py ingestion
catalog/          DuckDB metadata catalog + pandas/pyarrow transform + DQ checks
warehouse/        Postgres star schema (schema.sql) + load_warehouse.py
api/              FastAPI app: cross-domain view endpoints + /analyze
dashboard/        Streamlit app (domain tabs + cross-domain chat) + Power BI export
pipeline/         run_pipeline.py -- runs the whole thing end-to-end
tests/            pytest suite (catalog, transforms, SQL guard, views, fallback)
```

## Setup

Requires Docker and Python 3.11+.

```bash
git clone <this-repo>
cd enterprise-data-lake
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Bring up the object store and warehouse database:

```bash
docker compose up -d minio postgres
```

Run the full pipeline (generate data -> land in lake -> catalog/transform
-> load warehouse -> export Power BI CSVs):

```bash
python3 pipeline/run_pipeline.py
```

Or run each stage yourself:

```bash
python3 generators/run_all.py
python3 lake/ingest/land_to_lake.py
python3 catalog/transform.py
python3 warehouse/load_warehouse.py
python3 dashboard/export_powerbi.py
```

Start the API and dashboard:

```bash
cd api && python3 -m uvicorn main:app --reload &
cd ..
streamlit run dashboard/app.py
```

Or run everything (Postgres, MinIO, API, dashboard) in Docker:

```bash
docker compose up -d
```

MinIO console: http://localhost:9001 (minioadmin / minioadmin)
API docs: http://localhost:8000/docs
Dashboard: http://localhost:8501

## The `/analyze` endpoint

`POST /analyze` with `{"question": "Compare HR costs with revenue"}`
returns a grounded natural-language answer citing real warehouse numbers.

- If `OPENAI_API_KEY` is set in `.env`, the endpoint uses `langchain` +
  `openai` to pick the right pre-registered cross-domain view(s), generate
  a read-only SQL query, run it, and narrate the real result.
- If no key is set, a deterministic template engine picks the same views
  by keyword match, runs the same kind of read-only SQL, and formats the
  comparison with an f-string template -- so the whole project is fully
  testable and demoable at zero cost.
- Either way, every SQL statement passes through `api/sql_guard.py` first,
  which rejects anything that isn't a single, read-only `SELECT`/CTE
  statement (no DDL/DML, no stacked statements, no catalog probing).

## Running tests

```bash
python3 -m pytest tests/ -v
```

Tests that need a live warehouse (marked `requires_pg`) are automatically
skipped if Postgres isn't reachable, so `pytest` still runs cleanly without
Docker running -- but with Docker up and the pipeline run, all tests pass
against real data.

## License

MIT -- see `LICENSE`.
