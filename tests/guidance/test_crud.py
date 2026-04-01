"""
tests/test_crud.py
───────────────────
Unit tests for the CRUD layer (guidance/crud.py).
Each test operates against a real in-memory SQLite DB via the `db` fixture.
"""

import pytest
from sqlalchemy.orm import Session

from guidance.models import Priority
from guidance.schemas import GuidanceUpdate, GuidanceUpsert
import guidance.crud as crud
from tests.guidance.conftest import make_upsert


# =========================================================================== #
#  UPSERT                                                                      #
# =========================================================================== #

class TestUpsertGuidance:

    def test_insert_new_record(self, db: Session):
        payload = make_upsert()
        record, created = crud.upsert_guidance(db, payload)

        assert created is True
        assert record.id is not None
        assert record.metric_name == "cpu_usage"
        assert record.priority == Priority.P2

    def test_insert_returns_persisted_data(self, db: Session):
        payload = make_upsert(resolution_steps=[{"step": 1, "action": "Kill process"}])
        record, _ = crud.upsert_guidance(db, payload)

        assert record.resolution_steps == [{"step": 1, "action": "Kill process"}]
        assert record.resolver_notes == "Check top/htop"
        assert record.resolution_meta == {"sla_minutes": 30, "tags": ["infra"]}

    def test_upsert_same_key_returns_created_false(self, db: Session):
        payload = make_upsert()
        crud.upsert_guidance(db, payload)
        _, created = crud.upsert_guidance(db, payload)

        assert created is False

    def test_upsert_updates_mutable_fields(self, db: Session):
        crud.upsert_guidance(db, make_upsert(resolver_notes="Old note"))

        updated_payload = make_upsert(
            resolver_notes="New note",
            resolution_steps=[{"step": 1, "action": "New action"}],
            resolution_meta={"sla_minutes": 60},
        )
        record, created = crud.upsert_guidance(db, updated_payload)

        assert created is False
        assert record.resolver_notes == "New note"
        assert record.resolution_steps == [{"step": 1, "action": "New action"}]
        assert record.resolution_meta == {"sla_minutes": 60}

    def test_upsert_updates_priority(self, db: Session):
        crud.upsert_guidance(db, make_upsert(priority=Priority.P4))
        record, _ = crud.upsert_guidance(db, make_upsert(priority=Priority.P1))

        assert record.priority == Priority.P1

    def test_different_priority_same_metric_creates_separate_records(self, db: Session):
        _, c1 = crud.upsert_guidance(db, make_upsert(priority=Priority.P1))
        _, c2 = crud.upsert_guidance(db, make_upsert(priority=Priority.P2))

        assert c1 is True
        assert c2 is True

        total, records = crud.get_all_guidance(db)
        assert total == 2

    def test_different_metric_same_priority_creates_separate_records(self, db: Session):
        crud.upsert_guidance(db, make_upsert(metric_name="cpu_usage", priority=Priority.P2))
        crud.upsert_guidance(db, make_upsert(metric_name="memory_usage", priority=Priority.P2))

        total, _ = crud.get_all_guidance(db)
        assert total == 2

    def test_last_updated_is_set_on_insert(self, db: Session):
        record, _ = crud.upsert_guidance(db, make_upsert())
        assert record.last_updated is not None


# =========================================================================== #
#  READ — by ID                                                                #
# =========================================================================== #

class TestGetGuidanceById:

    def test_returns_correct_record(self, db: Session):
        record, _ = crud.upsert_guidance(db, make_upsert())
        fetched = crud.get_guidance_by_id(db, record.id)

        assert fetched is not None
        assert fetched.id == record.id

    def test_returns_none_for_missing_id(self, db: Session):
        result = crud.get_guidance_by_id(db, 99999)
        assert result is None


# =========================================================================== #
#  READ — by natural key                                                       #
# =========================================================================== #

class TestGetGuidanceByNaturalKey:

    def test_returns_correct_record(self, db: Session):
        crud.upsert_guidance(db, make_upsert(metric_name="disk_io", priority=Priority.P1))
        record = crud.get_guidance_by_natural_key(db, "disk_io", Priority.P1)

        assert record is not None
        assert record.metric_name == "disk_io"
        assert record.priority == Priority.P1

    def test_returns_none_when_not_found(self, db: Session):
        result = crud.get_guidance_by_natural_key(db, "nonexistent", Priority.P1)
        assert result is None

    def test_lookup_is_exact_match(self, db: Session):
        crud.upsert_guidance(db, make_upsert(metric_name="cpu_usage", priority=Priority.P1))
        result = crud.get_guidance_by_natural_key(db, "cpu_usage", Priority.P2)
        assert result is None


# =========================================================================== #
#  READ — list / filters / pagination                                          #
# =========================================================================== #

class TestGetAllGuidance:

    def _seed(self, db: Session):
        crud.upsert_guidance(db, make_upsert("cpu_usage", priority=Priority.P1))
        crud.upsert_guidance(db, make_upsert("cpu_usage_heavy", priority=Priority.P1))
        crud.upsert_guidance(db, make_upsert("memory_usage", priority=Priority.P2))
        crud.upsert_guidance(db, make_upsert("disk_io", priority=Priority.P4, purpose="ops"))

    def test_returns_all_records(self, db: Session):
        self._seed(db)
        total, records = crud.get_all_guidance(db)
        assert total == 4
        assert len(records) == 4

    def test_filter_by_priority(self, db: Session):
        self._seed(db)
        total, records = crud.get_all_guidance(db, priority=Priority.P1)
        assert total == 2
        assert all(r.priority == Priority.P1 for r in records)

    def test_filter_by_metric_name_partial(self, db: Session):
        self._seed(db)
        total, records = crud.get_all_guidance(db, metric_name="cpu")
        assert total == 2
        assert all("cpu" in r.metric_name for r in records)

    def test_filter_by_purpose(self, db: Session):
        self._seed(db)
        total, records = crud.get_all_guidance(db, purpose="ops")
        assert total == 1
        assert all(r.purpose == "ops" for r in records)

    def test_combined_filters(self, db: Session):
        self._seed(db)
        total, records = crud.get_all_guidance(db, priority=Priority.P1, metric_name="cpu")
        assert total == 2

    def test_pagination_skip(self, db: Session):
        self._seed(db)
        total, records = crud.get_all_guidance(db, skip=2, limit=10)
        assert total == 4       # total reflects unsliced count
        assert len(records) == 2

    def test_pagination_limit(self, db: Session):
        self._seed(db)
        _, records = crud.get_all_guidance(db, skip=0, limit=2)
        assert len(records) == 2

    def test_empty_db_returns_zero(self, db: Session):
        total, records = crud.get_all_guidance(db)
        assert total == 0
        assert records == []

    def test_no_filter_match_returns_zero(self, db: Session):
        self._seed(db)
        total, records = crud.get_all_guidance(db, metric_name="nonexistent_metric")
        assert total == 0
        assert records == []


# =========================================================================== #
#  UPDATE by ID                                                                #
# =========================================================================== #

class TestUpdateGuidanceById:

    def test_updates_resolver_notes(self, db: Session):
        record, _ = crud.upsert_guidance(db, make_upsert())
        updated = crud.update_guidance_by_id(
            db, record.id, GuidanceUpdate(resolver_notes="Updated note")
        )
        assert updated.resolver_notes == "Updated note"

    def test_updates_resolution_steps(self, db: Session):
        record, _ = crud.upsert_guidance(db, make_upsert())
        new_steps = [{"step": 1, "action": "New step"}]
        updated = crud.update_guidance_by_id(
            db, record.id, GuidanceUpdate(resolution_steps=new_steps)
        )
        assert updated.resolution_steps == new_steps

    def test_updates_resolution_meta(self, db: Session):
        record, _ = crud.upsert_guidance(db, make_upsert())
        updated = crud.update_guidance_by_id(
            db, record.id, GuidanceUpdate(resolution_meta={"sla_minutes": 999})
        )
        assert updated.resolution_meta == {"sla_minutes": 999}

    def test_patch_only_sets_provided_fields(self, db: Session):
        """Unset fields must remain unchanged (PATCH semantics)."""
        record, _ = crud.upsert_guidance(
            db, make_upsert(resolver_notes="Keep me", resolution_meta={"keep": True})
        )
        crud.update_guidance_by_id(
            db, record.id, GuidanceUpdate(resolution_steps=[{"step": 99}])
        )
        # Re-fetch to confirm untouched fields
        fetched = crud.get_guidance_by_id(db, record.id)
        assert fetched.resolver_notes == "Keep me"
        assert fetched.resolution_meta == {"keep": True}

    def test_returns_none_for_missing_id(self, db: Session):
        result = crud.update_guidance_by_id(db, 99999, GuidanceUpdate(resolver_notes="x"))
        assert result is None

    def test_natural_key_unchanged_after_update(self, db: Session):
        record, _ = crud.upsert_guidance(db, make_upsert())
        updated = crud.update_guidance_by_id(
            db, record.id, GuidanceUpdate(resolver_notes="Changed")
        )
        assert updated.metric_name == record.metric_name


# =========================================================================== #
#  DELETE by ID                                                                #
# =========================================================================== #

class TestDeleteGuidanceById:

    def test_deletes_existing_record(self, db: Session):
        record, _ = crud.upsert_guidance(db, make_upsert())
        result = crud.delete_guidance_by_id(db, record.id)

        assert result is True
        assert crud.get_guidance_by_id(db, record.id) is None

    def test_returns_false_for_missing_id(self, db: Session):
        assert crud.delete_guidance_by_id(db, 99999) is False

    def test_only_deletes_target_record(self, db: Session):
        r1, _ = crud.upsert_guidance(db, make_upsert(metric_name="cpu_usage"))
        crud.upsert_guidance(db, make_upsert(metric_name="memory_usage"))

        crud.delete_guidance_by_id(db, r1.id)
        total, _ = crud.get_all_guidance(db)
        assert total == 1


# =========================================================================== #
#  DELETE by natural key                                                       #
# =========================================================================== #

class TestDeleteGuidanceByNaturalKey:

    def test_deletes_by_natural_key(self, db: Session):
        crud.upsert_guidance(db, make_upsert(metric_name="disk_io", priority=Priority.P2))
        result = crud.delete_guidance_by_natural_key(db, "disk_io", Priority.P2)

        assert result is True
        assert crud.get_guidance_by_natural_key(db, "disk_io", Priority.P2) is None

    def test_returns_false_for_missing_key(self, db: Session):
        assert crud.delete_guidance_by_natural_key(db, "ghost_metric", Priority.P3) is False
