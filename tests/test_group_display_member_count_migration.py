import importlib.util
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MIGRATION_PATH = (
    PROJECT_ROOT
    / "migrations"
    / "versions"
    / "c7e8f9a0b1c2_add_group_display_member_count.py"
)


def _load_migration():
    spec = importlib.util.spec_from_file_location("group_display_count_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_group_display_count_migration_has_linear_revision_metadata():
    migration = _load_migration()

    assert migration.revision == "c7e8f9a0b1c2"
    assert migration.down_revision == "a1b2c3d4e5f6"


def test_group_display_count_migration_adds_and_removes_only_the_new_column(
    monkeypatch,
):
    migration = _load_migration()
    calls = []
    monkeypatch.setattr(
        migration.op,
        "add_column",
        lambda table_name, column: calls.append(
            ("add", table_name, column.name, column.type.length, column.nullable)
        ),
    )
    monkeypatch.setattr(
        migration.op,
        "drop_column",
        lambda table_name, column_name: calls.append(
            ("drop", table_name, column_name)
        ),
    )

    migration.upgrade()
    migration.downgrade()

    assert calls == [
        ("add", "groups", "display_member_count", 32, True),
        ("drop", "groups", "display_member_count"),
    ]
