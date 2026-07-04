"""Unit tests for the catalog registration logic (catalog/catalog_store.py)."""
import os
import tempfile

from catalog_store import CatalogStore


def test_register_and_get_dataset():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_catalog.duckdb")
        store = CatalogStore(db_path)
        store.register_dataset(
            domain="sales", dataset_name="orders",
            schema={"order_id": "string", "order_total": "float64"},
            partition_keys=["dt"], row_count=100,
        )
        ds = store.get_dataset("sales", "orders")
        assert ds is not None
        assert ds["domain"] == "sales"
        assert ds["dataset_name"] == "orders"
        assert ds["row_count"] == 100
        assert ds["schema"]["order_id"] == "string"
        store.close()


def test_register_dataset_upsert_updates_row_count():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_catalog.duckdb")
        store = CatalogStore(db_path)
        store.register_dataset("hr", "employees", {"employee_id": "string"}, [], 50)
        store.register_dataset("hr", "employees", {"employee_id": "string"}, [], 75)
        ds = store.get_dataset("hr", "employees")
        assert ds["row_count"] == 75
        store.close()


def test_list_datasets_returns_all_registered():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_catalog.duckdb")
        store = CatalogStore(db_path)
        store.register_dataset("sales", "orders", {"a": "string"}, [], 10)
        store.register_dataset("hr", "employees", {"b": "string"}, [], 20)
        datasets = store.list_datasets()
        assert len(datasets) == 2
        names = {(d["domain"], d["dataset_name"]) for d in datasets}
        assert ("sales", "orders") in names
        assert ("hr", "employees") in names
        store.close()


def test_get_dataset_missing_returns_none():
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "test_catalog.duckdb")
        store = CatalogStore(db_path)
        assert store.get_dataset("nonexistent", "dataset") is None
        store.close()
