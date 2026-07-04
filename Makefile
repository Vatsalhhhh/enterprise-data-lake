.PHONY: up down generate land catalog warehouse export pipeline test api dashboard clean

up:
	docker compose up -d minio postgres

down:
	docker compose down

generate:
	python3 generators/run_all.py

land:
	python3 lake/ingest/land_to_lake.py

catalog:
	python3 catalog/transform.py

warehouse:
	python3 warehouse/load_warehouse.py

export:
	python3 dashboard/export_powerbi.py

pipeline: up
	python3 pipeline/run_pipeline.py

test:
	python3 -m pytest tests/ -v

api:
	cd api && python3 -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload

dashboard:
	streamlit run dashboard/app.py

clean:
	rm -rf generators/output catalog/catalog.duckdb dashboard/exports/powerbi/*.csv
