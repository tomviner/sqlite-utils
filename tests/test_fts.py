import pytest
from sqlite_utils import Database
from sqlite_utils.utils import sqlite3

search_records = [
    {
        "text": "tanuki are running tricksters",
        "country": "Japan",
        "not_searchable": "foo",
    },
    {
        "text": "racoons are biting trash pandas",
        "country": "USA",
        "not_searchable": "bar",
    },
]


def test_enable_fts(fresh_db):
    table = fresh_db["searchable"]
    table.insert_all(search_records)
    assert ["searchable"] == fresh_db.table_names()
    table.enable_fts(["text", "country"], fts_version="FTS4")
    assert [
        "searchable",
        "searchable_fts",
        "searchable_fts_segments",
        "searchable_fts_segdir",
        "searchable_fts_docsize",
        "searchable_fts_stat",
    ] == fresh_db.table_names()
    assert [("tanuki are running tricksters", "Japan", "foo")] == table.search("tanuki")
    assert [("racoons are biting trash pandas", "USA", "bar")] == table.search("usa")
    assert [] == table.search("bar")


def test_enable_fts_escape_table_names(fresh_db):
    # Table names with restricted chars are handled correctly.
    # colons and dots are restricted characters for table names.
    table = fresh_db["http://example.com"]
    table.insert_all(search_records)
    assert ["http://example.com"] == fresh_db.table_names()
    table.enable_fts(["text", "country"], fts_version="FTS4")
    assert [
        "http://example.com",
        "http://example.com_fts",
        "http://example.com_fts_segments",
        "http://example.com_fts_segdir",
        "http://example.com_fts_docsize",
        "http://example.com_fts_stat",
    ] == fresh_db.table_names()
    assert [("tanuki are running tricksters", "Japan", "foo")] == table.search("tanuki")
    assert [("racoons are biting trash pandas", "USA", "bar")] == table.search("usa")
    assert [] == table.search("bar")


def test_enable_fts_table_names_containing_spaces(fresh_db):
    table = fresh_db["test"]
    table.insert({"column with spaces": "in its name"})
    table.enable_fts(["column with spaces"])
    assert [
        "test",
        "test_fts",
        "test_fts_data",
        "test_fts_idx",
        "test_fts_docsize",
        "test_fts_config",
    ] == fresh_db.table_names()


def test_populate_fts(fresh_db):
    table = fresh_db["populatable"]
    table.insert(search_records[0])
    table.enable_fts(["text", "country"], fts_version="FTS4")
    assert [] == table.search("trash pandas")
    table.insert(search_records[1])
    assert [] == table.search("trash pandas")
    # Now run populate_fts to make this record available
    table.populate_fts(["text", "country"])
    assert [("racoons are biting trash pandas", "USA", "bar")] == table.search("usa")


def test_populate_fts_escape_table_names(fresh_db):
    # Restricted characters such as colon and dots should be escaped.
    table = fresh_db["http://example.com"]
    table.insert(search_records[0])
    table.enable_fts(["text", "country"], fts_version="FTS4")
    assert [] == table.search("trash pandas")
    table.insert(search_records[1])
    assert [] == table.search("trash pandas")
    # Now run populate_fts to make this record available
    table.populate_fts(["text", "country"])
    assert [("racoons are biting trash pandas", "USA", "bar")] == table.search("usa")


def test_fts_tokenize(fresh_db):
    for fts_version in ("4", "5"):
        table_name = "searchable_{}".format(fts_version)
        table = fresh_db[table_name]
        table.insert_all(search_records)
        # Test without porter stemming
        table.enable_fts(
            ["text", "country"],
            fts_version="FTS{}".format(fts_version),
        )
        assert [] == table.search("bite")
        # Test WITH stemming
        table.disable_fts()
        table.enable_fts(
            ["text", "country"],
            fts_version="FTS{}".format(fts_version),
            tokenize="porter",
        )
        assert [("racoons are biting trash pandas", "USA", "bar")] == table.search(
            "bite"
        )


def test_optimize_fts(fresh_db):
    for fts_version in ("4", "5"):
        table_name = "searchable_{}".format(fts_version)
        table = fresh_db[table_name]
        table.insert_all(search_records)
        table.enable_fts(["text", "country"], fts_version="FTS{}".format(fts_version))
    # You can call optimize successfully against the tables OR their _fts equivalents:
    for table_name in (
        "searchable_4",
        "searchable_5",
        "searchable_4_fts",
        "searchable_5_fts",
    ):
        fresh_db[table_name].optimize()


def test_enable_fts_w_triggers(fresh_db):
    table = fresh_db["searchable"]
    table.insert(search_records[0])
    table.enable_fts(["text", "country"], fts_version="FTS4", create_triggers=True)
    assert [("tanuki are running tricksters", "Japan", "foo")] == table.search("tanuki")
    table.insert(search_records[1])
    # Triggers will auto-populate FTS virtual table, not need to call populate_fts()
    assert [("racoons are biting trash pandas", "USA", "bar")] == table.search("usa")
    assert [] == table.search("bar")


@pytest.mark.parametrize("create_triggers", [True, False])
def test_disable_fts(fresh_db, create_triggers):
    table = fresh_db["searchable"]
    table.insert(search_records[0])
    table.enable_fts(["text", "country"], create_triggers=create_triggers)
    assert {
        "searchable",
        "searchable_fts",
        "searchable_fts_data",
        "searchable_fts_idx",
        "searchable_fts_docsize",
        "searchable_fts_config",
    } == set(fresh_db.table_names())
    if create_triggers:
        expected_triggers = {"searchable_ai", "searchable_ad", "searchable_au"}
    else:
        expected_triggers = set()
    assert expected_triggers == set(
        r[0]
        for r in fresh_db.execute(
            "select name from sqlite_master where type = 'trigger'"
        ).fetchall()
    )
    # Now run .disable_fts() and confirm it worked
    table.disable_fts()
    assert (
        0
        == fresh_db.execute(
            "select count(*) from sqlite_master where type = 'trigger'"
        ).fetchone()[0]
    )
    assert ["searchable"] == fresh_db.table_names()


@pytest.mark.parametrize("table_to_fix", ["searchable", "searchable_fts"])
def test_rebuild_fts(fresh_db, table_to_fix):
    table = fresh_db["searchable"]
    table.insert(search_records[0])
    table.enable_fts(["text", "country"])
    # Run a search
    assert [("tanuki are running tricksters", "Japan", "foo")] == table.search("tanuki")
    # Delete from searchable_fts_data
    fresh_db["searchable_fts_data"].delete_where()
    # This should have broken the index
    with pytest.raises(sqlite3.DatabaseError):
        table.search("tanuki")
    # Running rebuild_fts() should fix it
    fresh_db[table_to_fix].rebuild_fts()
    assert [("tanuki are running tricksters", "Japan", "foo")] == table.search("tanuki")


@pytest.mark.parametrize("invalid_table", ["does_not_exist", "not_searchable"])
def test_rebuild_fts_invalid(fresh_db, invalid_table):
    fresh_db["not_searchable"].insert({"foo": "bar"})
    # Raise OperationalError on invalid table
    with pytest.raises(sqlite3.OperationalError):
        fresh_db[invalid_table].rebuild_fts()


@pytest.mark.parametrize("fts_version", ["FTS4", "FTS5"])
def test_rebuild_removes_junk_docsize_rows(tmpdir, fts_version):
    # Recreating https://github.com/simonw/sqlite-utils/issues/149
    path = tmpdir / "test.db"
    db = Database(str(path), recursive_triggers=False)
    licenses = [{"key": "apache2", "name": "Apache 2"}, {"key": "bsd", "name": "BSD"}]
    db["licenses"].insert_all(licenses, pk="key", replace=True)
    db["licenses"].enable_fts(["name"], create_triggers=True, fts_version=fts_version)
    assert db["licenses_fts_docsize"].count == 2
    # Bug: insert with replace increases the number of rows in _docsize:
    db["licenses"].insert_all(licenses, pk="key", replace=True)
    assert db["licenses_fts_docsize"].count == 4
    # rebuild should fix this:
    db["licenses_fts"].rebuild_fts()
    assert db["licenses_fts_docsize"].count == 2
