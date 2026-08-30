from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

PAPER_1 = "01890f3a-0000-7000-8000-000000000001"
PAPER_2 = "01890f3a-0000-7000-8000-000000000002"
VERSION_1 = "01890f3a-0000-7000-8000-000000000011"
VERSION_2 = "01890f3a-0000-7000-8000-000000000012"
NOW = "2026-08-29T08:00:00+00:00"


def _connection(database_path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def _seed_selected_origin(
    connection: sqlite3.Connection,
    suffix: int,
    source_id: str = "arxiv",
) -> tuple[str, str, int]:
    blob_id = f"01890f3a-0000-7000-8000-{suffix:012d}"
    snapshot_id = f"01890f3a-0000-7000-8000-{suffix + 1:012d}"
    capture_id = f"01890f3a-0000-7000-8000-{suffix + 2:012d}"
    run_id = f"01890f3a-0000-7000-8000-{suffix + 3:012d}"
    connection.execute(
        "INSERT INTO stored_blobs "
        "(id, sha256, size_bytes, media_type, relative_path, created_at) "
        "VALUES (?, ?, 1, 'application/atom+xml', ?, ?)",
        (blob_id, f"{suffix:064x}", f"blobs/{suffix:02x}/source", NOW),
    )
    connection.execute(
        "INSERT INTO source_snapshots "
        "(id, capture_id, source_id, stored_blob_id, request_fingerprint, retrieved_at) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (snapshot_id, capture_id, source_id, blob_id, "f" * 64, NOW),
    )
    connection.execute(
        "INSERT INTO snapshot_records "
        "(source_snapshot_id, ordinal, source_item_id, source_version_key, raw_record_sha256) "
        "VALUES (?, 0, '2608.00001', '2608.00001v1', ?)",
        (snapshot_id, "e" * 64),
    )
    connection.execute(
        "INSERT INTO ingestion_runs "
        "(id, source_id, prepared_digest, query_json, status, started_at, selected_records, "
        "new_papers, new_versions, metadata_updates, unchanged_records, failed_records) "
        "VALUES (?, ?, ?, ?, 'running', ?, 1, 0, 0, 0, 0, 0)",
        (run_id, source_id, "d" * 64, '{"schema_version":"discovery-query-v1"}', NOW),
    )
    connection.execute(
        "INSERT INTO ingestion_run_snapshots "
        "(run_id, page_ordinal, source_snapshot_id, source_id) "
        "VALUES (?, 0, ?, ?)",
        (run_id, snapshot_id, source_id),
    )
    connection.execute(
        "INSERT INTO ingestion_run_selected_records "
        "(run_id, selection_ordinal, source_snapshot_id, record_ordinal) "
        "VALUES (?, 0, ?, 0)",
        (run_id, snapshot_id),
    )
    return run_id, snapshot_id, 0


def test_foreign_keys_reject_orphans(database_path: Path) -> None:
    with _connection(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO paper_versions "
                "(id, paper_id, source_id, source_version_key, is_current, created_at) "
                "VALUES (?, ?, 'arxiv', '2608.00001v1', 1, ?)",
                (VERSION_1, PAPER_1, NOW),
            )


def test_partial_index_allows_one_current_version_per_paper_and_source(
    database_path: Path,
) -> None:
    with _connection(database_path) as connection:
        connection.execute("INSERT INTO papers (id, created_at) VALUES (?, ?)", (PAPER_1, NOW))
        connection.execute(
            "INSERT INTO paper_versions "
            "(id, paper_id, source_id, source_version_key, is_current, created_at) "
            "VALUES (?, ?, 'arxiv', '2608.00001v1', 1, ?)",
            (VERSION_1, PAPER_1, NOW),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO paper_versions "
                "(id, paper_id, source_id, source_version_key, is_current, created_at) "
                "VALUES (?, ?, 'arxiv', '2608.00001v2', 1, ?)",
                (VERSION_2, PAPER_1, NOW),
            )


def test_closed_values_and_canonical_query_json_are_checked(database_path: Path) -> None:
    with _connection(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ingestion_runs "
                "(id, source_id, prepared_digest, query_json, status, started_at, "
                "selected_records, new_papers, new_versions, metadata_updates, "
                "unchanged_records, failed_records) "
                "VALUES (?, 'arxiv', ?, ?, 'running', ?, 0, 0, 0, 0, 0, 0)",
                (
                    "01890f3a-0000-7000-8000-000000000020",
                    "a" * 64,
                    '{"schema_version":"unknown"}',
                    NOW,
                ),
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO artifacts "
                "(id, paper_version_id, stored_blob_id, kind, created_at) "
                "VALUES (?, ?, ?, 'source_response', ?)",
                (
                    "01890f3a-0000-7000-8000-000000000021",
                    VERSION_1,
                    "01890f3a-0000-7000-8000-000000000022",
                    NOW,
                ),
            )


def test_identifier_evidence_uses_real_composite_foreign_keys(database_path: Path) -> None:
    with _connection(database_path) as connection:
        connection.execute("INSERT INTO papers (id, created_at) VALUES (?, ?)", (PAPER_2, NOW))
        connection.execute(
            "INSERT INTO paper_identifiers "
            "(paper_id, scheme, canonical_value) VALUES (?, 'doi', '10.1000/example')",
            (PAPER_2,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO paper_identifier_evidence "
                "(scheme, canonical_value, source_id, source_snapshot_id, record_ordinal, "
                "observed_at) VALUES "
                "('doi', '10.1000/missing', 'arxiv', ?, 0, ?)",
                ("01890f3a-0000-7000-8000-000000000099", NOW),
            )


def test_catalog_meta_is_a_non_negative_singleton(database_path: Path) -> None:
    with _connection(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO catalog_meta "
                "(singleton_id, revision, schema_contract_version) VALUES (2, 0, 'catalog-v1')"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE catalog_meta SET revision = -1 WHERE singleton_id = 1")


def test_internal_ids_are_uuidv7(database_path: Path) -> None:
    with _connection(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO papers (id, created_at) VALUES "
                "('01890f3a-0000-4000-8000-000000000001', ?)",
                (NOW,),
            )


def test_metadata_artifact_observation_belongs_to_same_version(database_path: Path) -> None:
    observation_1 = "01890f3a-0000-7000-8000-000000000031"
    observation_2 = "01890f3a-0000-7000-8000-000000000032"
    blob = "01890f3a-0000-7000-8000-000000000033"
    with _connection(database_path) as connection:
        connection.execute("INSERT INTO papers (id, created_at) VALUES (?, ?)", (PAPER_1, NOW))
        connection.execute("INSERT INTO papers (id, created_at) VALUES (?, ?)", (PAPER_2, NOW))
        connection.execute(
            "INSERT INTO paper_versions "
            "(id, paper_id, source_id, source_version_key, is_current, created_at) "
            "VALUES (?, ?, 'arxiv', '2608.00001v1', 1, ?)",
            (VERSION_1, PAPER_1, NOW),
        )
        connection.execute(
            "INSERT INTO paper_versions "
            "(id, paper_id, source_id, source_version_key, is_current, created_at) "
            "VALUES (?, ?, 'arxiv', '2608.00002v1', 1, ?)",
            (VERSION_2, PAPER_2, NOW),
        )
        origin_1 = _seed_selected_origin(connection, 70)
        origin_2 = _seed_selected_origin(connection, 80)
        connection.execute(
            "INSERT INTO version_observations "
            "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
            "origin_run_id, "
            "origin_source_snapshot_id, origin_record_ordinal, title, title_normalized) "
            "VALUES (?, ?, ?, ?, 'arxiv', ?, ?, ?, 'One', 'one')",
            (observation_1, VERSION_1, "a" * 64, NOW, *origin_1),
        )
        connection.execute(
            "INSERT INTO version_observations "
            "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
            "origin_run_id, "
            "origin_source_snapshot_id, origin_record_ordinal, title, title_normalized) "
            "VALUES (?, ?, ?, ?, 'arxiv', ?, ?, ?, 'Two', 'two')",
            (observation_2, VERSION_2, "b" * 64, NOW, *origin_2),
        )
        connection.execute(
            "INSERT INTO stored_blobs "
            "(id, sha256, size_bytes, media_type, relative_path, created_at) "
            "VALUES (?, ?, 1, 'application/json', 'blobs/aa/value', ?)",
            (blob, "c" * 64, NOW),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO artifacts "
                "(id, paper_version_id, version_observation_id, stored_blob_id, kind, "
                "created_at) VALUES (?, ?, ?, ?, 'metadata', ?)",
                (
                    "01890f3a-0000-7000-8000-000000000034",
                    VERSION_1,
                    observation_2,
                    blob,
                    NOW,
                ),
            )


def test_metadata_artifact_blob_matches_observation_digest(database_path: Path) -> None:
    observation = "01890f3a-0000-7000-8000-000000000051"
    blob = "01890f3a-0000-7000-8000-000000000052"
    with _connection(database_path) as connection:
        connection.execute("INSERT INTO papers (id, created_at) VALUES (?, ?)", (PAPER_1, NOW))
        connection.execute(
            "INSERT INTO paper_versions "
            "(id, paper_id, source_id, source_version_key, is_current, created_at) "
            "VALUES (?, ?, 'arxiv', '2608.00001v1', 1, ?)",
            (VERSION_1, PAPER_1, NOW),
        )
        origin = _seed_selected_origin(connection, 90)
        connection.execute(
            "INSERT INTO version_observations "
            "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
            "origin_run_id, "
            "origin_source_snapshot_id, origin_record_ordinal, title, title_normalized) "
            "VALUES (?, ?, ?, ?, 'arxiv', ?, ?, ?, 'One', 'one')",
            (observation, VERSION_1, "a" * 64, NOW, *origin),
        )
        connection.execute(
            "INSERT INTO stored_blobs "
            "(id, sha256, size_bytes, media_type, relative_path, created_at) "
            "VALUES (?, ?, 1, 'application/json', 'blobs/bb/value', ?)",
            (blob, "b" * 64, NOW),
        )

        with pytest.raises(sqlite3.IntegrityError, match="digest mismatch"):
            connection.execute(
                "INSERT INTO artifacts "
                "(id, paper_version_id, version_observation_id, stored_blob_id, kind, "
                "created_at) VALUES (?, ?, ?, ?, 'metadata', ?)",
                (
                    "01890f3a-0000-7000-8000-000000000053",
                    VERSION_1,
                    observation,
                    blob,
                    NOW,
                ),
            )


def test_finalized_run_requires_exact_counters_and_finished_timestamp(
    database_path: Path,
) -> None:
    with _connection(database_path) as connection:
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ingestion_runs "
                "(id, source_id, prepared_digest, query_json, status, started_at, finished_at, "
                "selected_records, new_papers, new_versions, metadata_updates, "
                "unchanged_records, failed_records) "
                "VALUES (?, 'arxiv', ?, ?, 'succeeded', ?, NULL, 2, 0, 1, 0, 0, 0)",
                (
                    "01890f3a-0000-7000-8000-000000000040",
                    "a" * 64,
                    '{"schema_version":"discovery-query-v1"}',
                    NOW,
                ),
            )


def test_ingestion_foreign_keys_close_manifest_selection_item_and_error(
    database_path: Path,
) -> None:
    with _connection(database_path) as connection:
        run_id, snapshot_id, _ = _seed_selected_origin(connection, 110)
        connection.execute(
            "INSERT INTO snapshot_records "
            "(source_snapshot_id, ordinal, source_item_id, source_version_key, "
            "raw_record_sha256) VALUES (?, 1, '2608.00002', '2608.00002v1', ?)",
            (snapshot_id, "a" * 64),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ingestion_run_items "
                "(run_id, source_snapshot_id, record_ordinal, outcome, created_paper, "
                "recorded_at) VALUES (?, ?, 1, 'failed', 0, ?)",
                (run_id, snapshot_id, NOW),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO collection_errors "
                "(run_id, source_snapshot_id, record_ordinal, stage, code, message, "
                "occurred_at) VALUES (?, ?, 0, 'recovery', 'interrupted', "
                "'record interrupted before completion', ?)",
                (run_id, snapshot_id, NOW),
            )

        connection.execute(
            "INSERT INTO ingestion_run_items "
            "(run_id, source_snapshot_id, record_ordinal, outcome, created_paper, "
            "recorded_at) VALUES (?, ?, 0, 'failed', 0, ?)",
            (run_id, snapshot_id, NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO collection_errors "
                "(run_id, source_snapshot_id, record_ordinal, stage, code, message, "
                "occurred_at) VALUES (?, ?, 0, 'catalog_write', 'interrupted', "
                "'invalid stage-code pair', ?)",
                (run_id, snapshot_id, NOW),
            )

        foreign_run = "01890f3a-0000-7000-8000-000000000120"
        connection.execute(
            "INSERT INTO ingestion_runs "
            "(id, source_id, prepared_digest, query_json, status, started_at, "
            "selected_records, new_papers, new_versions, metadata_updates, "
            "unchanged_records, failed_records) VALUES (?, 'arxiv', ?, ?, 'running', ?, "
            "0, 0, 0, 0, 0, 0)",
            (foreign_run, "c" * 64, '{"schema_version":"discovery-query-v1"}', NOW),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ingestion_run_selected_records "
                "(run_id, selection_ordinal, source_snapshot_id, record_ordinal) "
                "VALUES (?, 0, ?, 0)",
                (foreign_run, snapshot_id),
            )


def test_run_snapshot_composite_keys_enforce_one_source(database_path: Path) -> None:
    with _connection(database_path) as connection:
        _, snapshot_id, _ = _seed_selected_origin(connection, 130)
        connection.execute(
            "INSERT INTO sources (id, base_url, enabled) "
            "VALUES ('crossref', 'https://api.crossref.org', 1)"
        )
        crossref_run = "01890f3a-0000-7000-8000-000000000140"
        connection.execute(
            "INSERT INTO ingestion_runs "
            "(id, source_id, prepared_digest, query_json, status, started_at, "
            "selected_records, new_papers, new_versions, metadata_updates, "
            "unchanged_records, failed_records) VALUES (?, 'crossref', ?, ?, 'running', ?, "
            "0, 0, 0, 0, 0, 0)",
            (crossref_run, "b" * 64, '{"schema_version":"discovery-query-v1"}', NOW),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO ingestion_run_snapshots "
                "(run_id, page_ordinal, source_snapshot_id, source_id) "
                "VALUES (?, 0, ?, 'crossref')",
                (crossref_run, snapshot_id),
            )


def test_provenance_composite_keys_enforce_source_equality(database_path: Path) -> None:
    with _connection(database_path) as connection:
        connection.execute(
            "INSERT INTO sources (id, base_url, enabled) "
            "VALUES ('crossref', 'https://api.crossref.org', 1)"
        )
        arxiv_run, arxiv_snapshot, _ = _seed_selected_origin(connection, 150)
        crossref_run, crossref_snapshot, _ = _seed_selected_origin(connection, 160, "crossref")
        paper_id = "01890f3a-0000-7000-8000-000000000170"
        version_id = "01890f3a-0000-7000-8000-000000000171"
        connection.execute("INSERT INTO papers (id, created_at) VALUES (?, ?)", (paper_id, NOW))
        connection.execute(
            "INSERT INTO paper_versions "
            "(id, paper_id, source_id, source_version_key, is_current, created_at) "
            "VALUES (?, ?, 'arxiv', '2608.00001v1', 1, ?)",
            (version_id, paper_id, NOW),
        )
        connection.execute(
            "INSERT INTO paper_identifiers (paper_id, scheme, canonical_value) "
            "VALUES (?, 'doi', '10.1000/source-equality')",
            (paper_id,),
        )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO paper_identifier_evidence "
                "(scheme, canonical_value, source_id, source_snapshot_id, record_ordinal, "
                "observed_at) VALUES ('doi', '10.1000/source-equality', 'crossref', ?, 0, ?)",
                (arxiv_snapshot, NOW),
            )

        connection.execute(
            "INSERT INTO version_identifiers "
            "(paper_version_id, scheme, canonical_value) "
            "VALUES (?, 'doi-version', '10.1000/source-equality.v1')",
            (version_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO version_identifier_evidence "
                "(scheme, canonical_value, source_id, source_snapshot_id, record_ordinal, "
                "observed_at) VALUES "
                "('doi-version', '10.1000/source-equality.v1', 'crossref', ?, 0, ?)",
                (arxiv_snapshot, NOW),
            )

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO version_observations "
                "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
                "origin_run_id, "
                "origin_source_snapshot_id, origin_record_ordinal, title, title_normalized) "
                "VALUES ('01890f3a-0000-7000-8000-000000000172', ?, ?, ?, 'crossref', ?, ?, 0, "
                "'Wrong source', 'wrong source')",
                (version_id, "a" * 64, NOW, crossref_run, crossref_snapshot),
            )

        observation_id = "01890f3a-0000-7000-8000-000000000173"
        connection.execute(
            "INSERT INTO version_observations "
            "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
            "origin_run_id, origin_source_snapshot_id, origin_record_ordinal, title, "
            "title_normalized) VALUES (?, ?, ?, ?, 'arxiv', ?, ?, 0, 'Valid', 'valid')",
            (observation_id, version_id, "b" * 64, NOW, arxiv_run, arxiv_snapshot),
        )
        author_id = "01890f3a-0000-7000-8000-000000000174"
        connection.execute("INSERT INTO authors (id, created_at) VALUES (?, ?)", (author_id, NOW))
        connection.execute(
            "INSERT INTO author_identifiers "
            "(author_id, scheme, canonical_value, verification_status) "
            "VALUES (?, 'orcid', '0000-0001-2345-6789', 'source_asserted')",
            (author_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO author_identifier_evidence "
                "(scheme, canonical_value, version_observation_id, source_id, observed_at) "
                "VALUES ('orcid', '0000-0001-2345-6789', ?, 'crossref', ?)",
                (observation_id, NOW),
            )

        assert arxiv_run != crossref_run


def test_resolved_records_and_items_cannot_cross_source_boundaries(
    database_path: Path,
) -> None:
    with _connection(database_path) as connection:
        connection.execute(
            "INSERT INTO sources (id, base_url, enabled) "
            "VALUES ('crossref', 'https://api.crossref.org', 1)"
        )
        arxiv_run, arxiv_snapshot, _ = _seed_selected_origin(connection, 180)
        crossref_run, crossref_snapshot, _ = _seed_selected_origin(connection, 190, "crossref")
        paper_id = "01890f3a-0000-7000-8000-000000000200"
        version_id = "01890f3a-0000-7000-8000-000000000201"
        observation_id = "01890f3a-0000-7000-8000-000000000202"
        connection.execute("INSERT INTO papers (id, created_at) VALUES (?, ?)", (paper_id, NOW))
        connection.execute(
            "INSERT INTO paper_versions "
            "(id, paper_id, source_id, source_version_key, is_current, created_at) "
            "VALUES (?, ?, 'crossref', '10.1000/source-boundary', 1, ?)",
            (version_id, paper_id, NOW),
        )
        connection.execute(
            "INSERT INTO version_observations "
            "(id, paper_version_id, normalized_sha256, observed_at, origin_source_id, "
            "origin_run_id, origin_source_snapshot_id, origin_record_ordinal, title, "
            "title_normalized) VALUES (?, ?, ?, ?, 'crossref', ?, ?, 0, 'Crossref', "
            "'crossref')",
            (
                observation_id,
                version_id,
                "a" * 64,
                NOW,
                crossref_run,
                crossref_snapshot,
            ),
        )

        with pytest.raises(sqlite3.IntegrityError, match="snapshot observation source mismatch"):
            connection.execute(
                "UPDATE snapshot_records SET version_observation_id = ? "
                "WHERE source_snapshot_id = ? AND ordinal = 0",
                (observation_id, arxiv_snapshot),
            )
        with pytest.raises(sqlite3.IntegrityError, match="ingestion item source mismatch"):
            connection.execute(
                "INSERT INTO ingestion_run_items "
                "(run_id, source_snapshot_id, record_ordinal, paper_id, paper_version_id, "
                "version_observation_id, outcome, created_paper, recorded_at) "
                "VALUES (?, ?, 0, ?, ?, ?, 'metadata_update', 0, ?)",
                (arxiv_run, arxiv_snapshot, paper_id, version_id, observation_id, NOW),
            )

        connection.execute(
            "UPDATE snapshot_records SET version_observation_id = ? "
            "WHERE source_snapshot_id = ? AND ordinal = 0",
            (observation_id, crossref_snapshot),
        )
        connection.execute(
            "INSERT INTO ingestion_run_items "
            "(run_id, source_snapshot_id, record_ordinal, paper_id, paper_version_id, "
            "version_observation_id, outcome, created_paper, recorded_at) "
            "VALUES (?, ?, 0, ?, ?, ?, 'metadata_update', 0, ?)",
            (crossref_run, crossref_snapshot, paper_id, version_id, observation_id, NOW),
        )

        assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
