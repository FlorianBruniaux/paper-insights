from __future__ import annotations

import sqlalchemy as sa

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}

metadata = sa.MetaData(naming_convention=NAMING_CONVENTION)


def _sha_check(column: str) -> str:
    return f"length({column}) = 64 AND {column} NOT GLOB '*[^0-9a-f]*'"


def _uuid7_check(column: str) -> str:
    return (
        f"length({column}) = 36 AND substr({column}, 9, 1) = '-' "
        f"AND substr({column}, 14, 1) = '-' AND substr({column}, 15, 1) = '7' "
        f"AND substr({column}, 19, 1) = '-' "
        f"AND lower(substr({column}, 20, 1)) IN ('8', '9', 'a', 'b') "
        f"AND substr({column}, 24, 1) = '-' "
        f"AND replace({column}, '-', '') NOT GLOB '*[^0-9a-f]*'"
    )


catalog_meta = sa.Table(
    "catalog_meta",
    metadata,
    sa.Column("singleton_id", sa.Integer, primary_key=True),
    sa.Column("revision", sa.Integer, nullable=False),
    sa.Column("schema_contract_version", sa.String(32), nullable=False),
    sa.CheckConstraint("singleton_id = 1", name="singleton"),
    sa.CheckConstraint("revision >= 0", name="revision_non_negative"),
    sa.CheckConstraint("schema_contract_version = 'catalog-v1'", name="schema_contract_version"),
)

sources = sa.Table(
    "sources",
    metadata,
    sa.Column("id", sa.String(64), primary_key=True),
    sa.Column("base_url", sa.Text, nullable=False),
    sa.Column("terms_url", sa.Text),
    sa.Column("enabled", sa.Boolean, nullable=False),
    sa.CheckConstraint("id <> ''", name="id_nonempty"),
    sa.CheckConstraint("enabled IN (0, 1)", name="enabled_boolean"),
)

stored_blobs = sa.Table(
    "stored_blobs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("sha256", sa.String(64), nullable=False, unique=True),
    sa.Column("size_bytes", sa.Integer, nullable=False),
    sa.Column("media_type", sa.Text, nullable=False),
    sa.Column("relative_path", sa.Text, nullable=False),
    sa.Column("created_at", sa.String(35), nullable=False),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
    sa.CheckConstraint(_sha_check("sha256"), name="sha256"),
    sa.CheckConstraint("size_bytes >= 0", name="size_non_negative"),
    sa.CheckConstraint("media_type <> ''", name="media_type_nonempty"),
    sa.CheckConstraint(
        "relative_path <> '' AND substr(relative_path, 1, 1) <> '/' "
        "AND relative_path NOT LIKE '%..%'",
        name="relative_path_confined",
    ),
)

papers = sa.Table(
    "papers",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("created_at", sa.String(35), nullable=False),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
)

paper_versions = sa.Table(
    "paper_versions",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id"), nullable=False),
    sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id"), nullable=False),
    sa.Column("source_version_key", sa.Text, nullable=False),
    sa.Column("is_current", sa.Boolean, nullable=False),
    sa.Column("created_at", sa.String(35), nullable=False),
    sa.UniqueConstraint("source_id", "source_version_key", name="uq_source_version"),
    sa.UniqueConstraint("id", "paper_id", name="uq_version_paper"),
    sa.UniqueConstraint("id", "source_id", name="uq_version_source"),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
    sa.CheckConstraint("source_version_key <> ''", name="source_version_key_nonempty"),
    sa.CheckConstraint("is_current IN (0, 1)", name="is_current_boolean"),
)
sa.Index(
    "uq_paper_versions_current",
    paper_versions.c.paper_id,
    paper_versions.c.source_id,
    unique=True,
    sqlite_where=paper_versions.c.is_current.is_(True),
)

version_observations = sa.Table(
    "version_observations",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "paper_version_id",
        sa.String(36),
        sa.ForeignKey("paper_versions.id"),
        nullable=False,
    ),
    sa.Column("normalized_sha256", sa.String(64), nullable=False),
    sa.Column("observed_at", sa.String(35), nullable=False),
    sa.Column("origin_source_id", sa.String(64), nullable=False),
    sa.Column("origin_run_id", sa.String(36), nullable=False),
    sa.Column("origin_source_snapshot_id", sa.String(36), nullable=False),
    sa.Column("origin_record_ordinal", sa.Integer, nullable=False),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("title_normalized", sa.Text, nullable=False),
    sa.Column("abstract", sa.Text),
    sa.Column("comment", sa.Text),
    sa.Column("journal_reference", sa.Text),
    sa.Column("language", sa.Text),
    sa.Column("source_url", sa.Text),
    sa.Column("submitted_at", sa.String(35)),
    sa.Column("announced_at", sa.String(35)),
    sa.UniqueConstraint(
        "paper_version_id", "normalized_sha256", name="uq_version_observation_hash"
    ),
    sa.UniqueConstraint("id", "paper_version_id", name="uq_observation_version"),
    sa.UniqueConstraint("id", "origin_source_id", name="uq_observation_source"),
    sa.ForeignKeyConstraint(
        ["origin_run_id", "origin_source_snapshot_id", "origin_record_ordinal"],
        [
            "ingestion_run_selected_records.run_id",
            "ingestion_run_selected_records.source_snapshot_id",
            "ingestion_run_selected_records.record_ordinal",
        ],
    ),
    sa.ForeignKeyConstraint(
        ["paper_version_id", "origin_source_id"],
        ["paper_versions.id", "paper_versions.source_id"],
    ),
    sa.ForeignKeyConstraint(
        ["origin_source_snapshot_id", "origin_source_id"],
        ["source_snapshots.id", "source_snapshots.source_id"],
    ),
    sa.ForeignKeyConstraint(
        ["origin_run_id", "origin_source_id"],
        ["ingestion_runs.id", "ingestion_runs.source_id"],
    ),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
    sa.CheckConstraint(_sha_check("normalized_sha256"), name="normalized_sha256"),
    sa.CheckConstraint("title <> ''", name="title_nonempty"),
    sa.CheckConstraint("title_normalized <> ''", name="title_normalized_nonempty"),
    sa.CheckConstraint("origin_record_ordinal >= 0", name="origin_record_ordinal_non_negative"),
)

authors = sa.Table(
    "authors",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("created_at", sa.String(35), nullable=False),
    sa.Column("retired_at", sa.String(35)),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
)

source_snapshots = sa.Table(
    "source_snapshots",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("capture_id", sa.String(36), nullable=False, unique=True),
    sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id"), nullable=False),
    sa.Column("stored_blob_id", sa.String(36), sa.ForeignKey("stored_blobs.id"), nullable=False),
    sa.Column("request_fingerprint", sa.String(64), nullable=False),
    sa.Column("retrieved_at", sa.String(35), nullable=False),
    sa.Column("next_cursor", sa.Text),
    sa.UniqueConstraint("id", "source_id", name="uq_snapshot_source"),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
    sa.CheckConstraint(_uuid7_check("capture_id"), name="capture_id_uuid7"),
    sa.CheckConstraint(_sha_check("request_fingerprint"), name="request_fingerprint"),
)

snapshot_records = sa.Table(
    "snapshot_records",
    metadata,
    sa.Column(
        "source_snapshot_id",
        sa.String(36),
        sa.ForeignKey("source_snapshots.id"),
        primary_key=True,
    ),
    sa.Column("ordinal", sa.Integer, primary_key=True),
    sa.Column("source_item_id", sa.Text),
    sa.Column("source_version_key", sa.Text),
    sa.Column("raw_record_sha256", sa.String(64), nullable=False),
    sa.Column("version_observation_id", sa.String(36)),
    sa.ForeignKeyConstraint(
        ["version_observation_id"],
        ["version_observations.id"],
        use_alter=True,
    ),
    sa.CheckConstraint("ordinal >= 0", name="ordinal_non_negative"),
    sa.CheckConstraint(_sha_check("raw_record_sha256"), name="raw_record_sha256"),
)

ingestion_runs = sa.Table(
    "ingestion_runs",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id"), nullable=False),
    sa.Column("prepared_digest", sa.String(64), nullable=False),
    sa.Column("query_json", sa.Text, nullable=False),
    sa.Column("status", sa.String(16), nullable=False),
    sa.Column("started_at", sa.String(35), nullable=False),
    sa.Column("finished_at", sa.String(35)),
    sa.Column("selected_records", sa.Integer, nullable=False),
    sa.Column("new_papers", sa.Integer, nullable=False, server_default="0"),
    sa.Column("new_versions", sa.Integer, nullable=False, server_default="0"),
    sa.Column("metadata_updates", sa.Integer, nullable=False, server_default="0"),
    sa.Column("unchanged_records", sa.Integer, nullable=False, server_default="0"),
    sa.Column("failed_records", sa.Integer, nullable=False, server_default="0"),
    sa.UniqueConstraint("id", "source_id", name="uq_run_source"),
    sa.CheckConstraint(_sha_check("prepared_digest"), name="prepared_digest"),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
    sa.CheckConstraint("json_valid(query_json)", name="query_json_valid"),
    sa.CheckConstraint(
        "json_extract(query_json, '$.schema_version') = 'discovery-query-v1'",
        name="query_json_schema",
    ),
    sa.CheckConstraint("status IN ('running', 'succeeded', 'partial', 'failed')", name="status"),
    sa.CheckConstraint(
        "selected_records >= 0 AND new_papers >= 0 AND new_versions >= 0 "
        "AND metadata_updates >= 0 AND unchanged_records >= 0 AND failed_records >= 0",
        name="counters_non_negative",
    ),
    sa.CheckConstraint("new_papers <= new_versions", name="new_papers_bounded"),
    sa.CheckConstraint(
        "(status = 'running' AND finished_at IS NULL) OR "
        "(status <> 'running' AND finished_at IS NOT NULL "
        "AND selected_records = new_versions + metadata_updates "
        "+ unchanged_records + failed_records)",
        name="final_state",
    ),
)

ingestion_run_snapshots = sa.Table(
    "ingestion_run_snapshots",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("page_ordinal", sa.Integer, primary_key=True),
    sa.Column("source_snapshot_id", sa.String(36), nullable=False),
    sa.Column("source_id", sa.String(64), nullable=False),
    sa.UniqueConstraint("run_id", "source_snapshot_id", name="uq_run_snapshot"),
    sa.ForeignKeyConstraint(
        ["run_id", "source_id"],
        ["ingestion_runs.id", "ingestion_runs.source_id"],
    ),
    sa.ForeignKeyConstraint(
        ["source_snapshot_id", "source_id"],
        ["source_snapshots.id", "source_snapshots.source_id"],
    ),
    sa.CheckConstraint("page_ordinal >= 0", name="page_ordinal_non_negative"),
)

ingestion_run_selected_records = sa.Table(
    "ingestion_run_selected_records",
    metadata,
    sa.Column("run_id", sa.String(36), primary_key=True),
    sa.Column("selection_ordinal", sa.Integer, primary_key=True),
    sa.Column("source_snapshot_id", sa.String(36), nullable=False),
    sa.Column("record_ordinal", sa.Integer, nullable=False),
    sa.UniqueConstraint(
        "run_id",
        "source_snapshot_id",
        "record_ordinal",
        name="uq_run_selected_record",
    ),
    sa.ForeignKeyConstraint(
        ["run_id", "source_snapshot_id"],
        ["ingestion_run_snapshots.run_id", "ingestion_run_snapshots.source_snapshot_id"],
    ),
    sa.ForeignKeyConstraint(
        ["source_snapshot_id", "record_ordinal"],
        ["snapshot_records.source_snapshot_id", "snapshot_records.ordinal"],
    ),
    sa.CheckConstraint("selection_ordinal >= 0", name="selection_ordinal_non_negative"),
    sa.CheckConstraint("record_ordinal >= 0", name="record_ordinal_non_negative"),
)

ingestion_run_items = sa.Table(
    "ingestion_run_items",
    metadata,
    sa.Column("run_id", sa.String(36), sa.ForeignKey("ingestion_runs.id"), primary_key=True),
    sa.Column("source_snapshot_id", sa.String(36), primary_key=True),
    sa.Column("record_ordinal", sa.Integer, primary_key=True),
    sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id")),
    sa.Column("paper_version_id", sa.String(36), sa.ForeignKey("paper_versions.id")),
    sa.Column(
        "version_observation_id",
        sa.String(36),
        sa.ForeignKey("version_observations.id"),
    ),
    sa.Column("outcome", sa.String(24), nullable=False),
    sa.Column("created_paper", sa.Boolean, nullable=False),
    sa.Column("recorded_at", sa.String(35), nullable=False),
    sa.ForeignKeyConstraint(
        ["run_id", "source_snapshot_id", "record_ordinal"],
        [
            "ingestion_run_selected_records.run_id",
            "ingestion_run_selected_records.source_snapshot_id",
            "ingestion_run_selected_records.record_ordinal",
        ],
    ),
    sa.ForeignKeyConstraint(
        ["paper_version_id", "paper_id"],
        ["paper_versions.id", "paper_versions.paper_id"],
    ),
    sa.ForeignKeyConstraint(
        ["version_observation_id", "paper_version_id"],
        ["version_observations.id", "version_observations.paper_version_id"],
    ),
    sa.CheckConstraint("record_ordinal >= 0", name="record_ordinal_non_negative"),
    sa.CheckConstraint(
        "outcome IN ('new_version', 'metadata_update', 'unchanged', 'failed')",
        name="outcome",
    ),
    sa.CheckConstraint("created_paper IN (0, 1)", name="created_paper_boolean"),
    sa.CheckConstraint(
        "created_paper = 0 OR outcome = 'new_version'", name="created_paper_outcome"
    ),
    sa.CheckConstraint(
        "(outcome = 'failed' AND paper_id IS NULL AND paper_version_id IS NULL "
        "AND version_observation_id IS NULL AND created_paper = 0) OR "
        "(outcome <> 'failed' AND paper_id IS NOT NULL AND paper_version_id IS NOT NULL "
        "AND version_observation_id IS NOT NULL)",
        name="outcome_references",
    ),
)

collection_errors = sa.Table(
    "collection_errors",
    metadata,
    sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
    sa.Column("run_id", sa.String(36), sa.ForeignKey("ingestion_runs.id"), nullable=False),
    sa.Column("source_snapshot_id", sa.String(36), nullable=False),
    sa.Column("record_ordinal", sa.Integer, nullable=False),
    sa.Column("stage", sa.String(24), nullable=False),
    sa.Column("code", sa.String(64), nullable=False),
    sa.Column("message", sa.Text, nullable=False),
    sa.Column("occurred_at", sa.String(35), nullable=False),
    sa.UniqueConstraint(
        "run_id", "source_snapshot_id", "record_ordinal", name="uq_collection_error_item"
    ),
    sa.ForeignKeyConstraint(
        ["run_id", "source_snapshot_id", "record_ordinal"],
        [
            "ingestion_run_items.run_id",
            "ingestion_run_items.source_snapshot_id",
            "ingestion_run_items.record_ordinal",
        ],
    ),
    sa.CheckConstraint(
        "(stage = 'catalog_write' AND code IN "
        "('record_invalid', 'artifact_invalid', 'catalog_conflict')) OR "
        "(stage = 'recovery' AND code = 'interrupted')",
        name="stage_code",
    ),
    sa.CheckConstraint("code <> '' AND message <> ''", name="public_error_nonempty"),
)

paper_identifiers = sa.Table(
    "paper_identifiers",
    metadata,
    sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id"), nullable=False),
    sa.Column("scheme", sa.String(32), primary_key=True),
    sa.Column("canonical_value", sa.Text, primary_key=True),
    sa.Column("verified_at", sa.String(35)),
    sa.CheckConstraint("scheme <> '' AND canonical_value <> ''", name="identity_nonempty"),
)

version_identifiers = sa.Table(
    "version_identifiers",
    metadata,
    sa.Column(
        "paper_version_id", sa.String(36), sa.ForeignKey("paper_versions.id"), nullable=False
    ),
    sa.Column("scheme", sa.String(32), primary_key=True),
    sa.Column("canonical_value", sa.Text, primary_key=True),
    sa.Column("verified_at", sa.String(35)),
    sa.CheckConstraint("scheme <> '' AND canonical_value <> ''", name="identity_nonempty"),
)

author_identifiers = sa.Table(
    "author_identifiers",
    metadata,
    sa.Column("author_id", sa.String(36), sa.ForeignKey("authors.id"), nullable=False),
    sa.Column("scheme", sa.String(32), primary_key=True),
    sa.Column("canonical_value", sa.Text, primary_key=True),
    sa.Column("verification_status", sa.String(32), nullable=False),
    sa.Column("verified_at", sa.String(35)),
    sa.CheckConstraint(
        "scheme <> '' AND canonical_value <> '' AND verification_status <> ''",
        name="identity_nonempty",
    ),
)

paper_identifier_evidence = sa.Table(
    "paper_identifier_evidence",
    metadata,
    sa.Column("scheme", sa.String(32), primary_key=True),
    sa.Column("canonical_value", sa.Text, primary_key=True),
    sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id"), nullable=False),
    sa.Column("source_snapshot_id", sa.String(36), primary_key=True),
    sa.Column("record_ordinal", sa.Integer, primary_key=True),
    sa.Column("observed_at", sa.String(35), nullable=False),
    sa.ForeignKeyConstraint(
        ["scheme", "canonical_value"],
        ["paper_identifiers.scheme", "paper_identifiers.canonical_value"],
    ),
    sa.ForeignKeyConstraint(
        ["source_snapshot_id", "record_ordinal"],
        ["snapshot_records.source_snapshot_id", "snapshot_records.ordinal"],
    ),
    sa.ForeignKeyConstraint(
        ["source_snapshot_id", "source_id"],
        ["source_snapshots.id", "source_snapshots.source_id"],
    ),
)

version_identifier_evidence = sa.Table(
    "version_identifier_evidence",
    metadata,
    sa.Column("scheme", sa.String(32), primary_key=True),
    sa.Column("canonical_value", sa.Text, primary_key=True),
    sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id"), nullable=False),
    sa.Column("source_snapshot_id", sa.String(36), primary_key=True),
    sa.Column("record_ordinal", sa.Integer, primary_key=True),
    sa.Column("observed_at", sa.String(35), nullable=False),
    sa.ForeignKeyConstraint(
        ["scheme", "canonical_value"],
        ["version_identifiers.scheme", "version_identifiers.canonical_value"],
    ),
    sa.ForeignKeyConstraint(
        ["source_snapshot_id", "record_ordinal"],
        ["snapshot_records.source_snapshot_id", "snapshot_records.ordinal"],
    ),
    sa.ForeignKeyConstraint(
        ["source_snapshot_id", "source_id"],
        ["source_snapshots.id", "source_snapshots.source_id"],
    ),
)

author_identifier_evidence = sa.Table(
    "author_identifier_evidence",
    metadata,
    sa.Column("scheme", sa.String(32), primary_key=True),
    sa.Column("canonical_value", sa.Text, primary_key=True),
    sa.Column("version_observation_id", sa.String(36), primary_key=True),
    sa.Column("source_id", sa.String(64), sa.ForeignKey("sources.id")),
    sa.Column("observed_at", sa.String(35), nullable=False),
    sa.ForeignKeyConstraint(
        ["scheme", "canonical_value"],
        ["author_identifiers.scheme", "author_identifiers.canonical_value"],
    ),
    sa.ForeignKeyConstraint(["version_observation_id"], ["version_observations.id"]),
    sa.ForeignKeyConstraint(
        ["version_observation_id", "source_id"],
        ["version_observations.id", "version_observations.origin_source_id"],
    ),
)

paper_authors = sa.Table(
    "paper_authors",
    metadata,
    sa.Column(
        "version_observation_id",
        sa.String(36),
        sa.ForeignKey("version_observations.id"),
        primary_key=True,
    ),
    sa.Column("position", sa.Integer, primary_key=True),
    sa.Column("author_id", sa.String(36), sa.ForeignKey("authors.id"), nullable=False),
    sa.Column("raw_name", sa.Text, nullable=False),
    sa.Column("affiliation_raw", sa.Text),
    sa.CheckConstraint("position >= 1", name="position_positive"),
    sa.CheckConstraint("raw_name <> ''", name="raw_name_nonempty"),
)

paper_version_categories = sa.Table(
    "paper_version_categories",
    metadata,
    sa.Column(
        "version_observation_id",
        sa.String(36),
        sa.ForeignKey("version_observations.id"),
        primary_key=True,
    ),
    sa.Column("position", sa.Integer, primary_key=True),
    sa.Column("category", sa.Text, nullable=False),
    sa.Column("is_primary", sa.Boolean, nullable=False),
    sa.UniqueConstraint("version_observation_id", "category", name="uq_observation_category"),
    sa.CheckConstraint("position >= 1", name="position_positive"),
    sa.CheckConstraint("category <> ''", name="category_nonempty"),
    sa.CheckConstraint("is_primary IN (0, 1)", name="is_primary_boolean"),
)

artifacts = sa.Table(
    "artifacts",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column(
        "paper_version_id", sa.String(36), sa.ForeignKey("paper_versions.id"), nullable=False
    ),
    sa.Column("version_observation_id", sa.String(36)),
    sa.Column("stored_blob_id", sa.String(36), sa.ForeignKey("stored_blobs.id"), nullable=False),
    sa.Column("kind", sa.String(16), nullable=False),
    sa.Column("source_url", sa.Text),
    sa.Column("parent_artifact_id", sa.String(36), sa.ForeignKey("artifacts.id")),
    sa.Column("producer_name", sa.Text),
    sa.Column("producer_version", sa.Text),
    sa.Column("created_at", sa.String(35), nullable=False),
    sa.UniqueConstraint("paper_version_id", "kind", "stored_blob_id", name="uq_version_artifact"),
    sa.ForeignKeyConstraint(
        ["version_observation_id", "paper_version_id"],
        ["version_observations.id", "version_observations.paper_version_id"],
    ),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
    sa.CheckConstraint("kind IN ('metadata', 'pdf', 'text', 'analysis')", name="kind"),
    sa.CheckConstraint(
        "kind <> 'metadata' OR version_observation_id IS NOT NULL",
        name="metadata_observation",
    ),
)

collections = sa.Table(
    "collections",
    metadata,
    sa.Column("id", sa.String(36), primary_key=True),
    sa.Column("slug", sa.String(128), nullable=False, unique=True),
    sa.Column("title", sa.Text, nullable=False),
    sa.Column("created_at", sa.String(35), nullable=False),
    sa.Column("updated_at", sa.String(35), nullable=False),
    sa.CheckConstraint(_uuid7_check("id"), name="id_uuid7"),
    sa.CheckConstraint("slug <> '' AND title <> ''", name="identity_nonempty"),
)

collection_papers = sa.Table(
    "collection_papers",
    metadata,
    sa.Column("collection_id", sa.String(36), sa.ForeignKey("collections.id"), primary_key=True),
    sa.Column("paper_id", sa.String(36), sa.ForeignKey("papers.id"), primary_key=True),
    sa.Column("added_at", sa.String(35), nullable=False),
    sa.Column("note", sa.Text),
)
