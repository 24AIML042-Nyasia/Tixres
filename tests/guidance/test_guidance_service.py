"""
tests/test_guidance_service.py
────────────────────────────────
Integration tests for GuidanceService (guidance/guidance_service.py).
All operations run against a real in-memory SQLite DB via the `service` fixture.
"""

import pytest

from guidance.models import Priority
from guidance.schemas import GuidanceUpdate
from guidance.GuidanceService import GuidanceService, GuidanceNotFoundError
from tests.guidance.conftest import make_upsert


# =========================================================================== #
#  upsert()                                                                    #
# =========================================================================== #

class TestServiceUpsert:

    def test_creates_new_record(self, service: GuidanceService):
        response, created = service.upsert(make_upsert())

        assert created is True
        assert response.id is not None
        assert response.metric_name == "cpu_usage"
        assert response.severity == "high"
        assert response.priority == Priority.P2

    def test_returns_guidance_response_schema(self, service: GuidanceService):
        from guidance.schemas import GuidanceResponse
        response, _ = service.upsert(make_upsert())
        assert isinstance(response, GuidanceResponse)

    def test_second_upsert_returns_created_false(self, service: GuidanceService):
        service.upsert(make_upsert())
        _, created = service.upsert(make_upsert())
        assert created is False

    def test_second_upsert_updates_payload(self, service: GuidanceService):
        service.upsert(make_upsert(resolver_notes="Old"))
        response, _ = service.upsert(make_upsert(resolver_notes="New"))
        assert response.resolver_notes == "New"

    def test_upsert_preserves_natural_key(self, service: GuidanceService):
        r1, _ = service.upsert(make_upsert())
        r2, _ = service.upsert(make_upsert(resolver_notes="Updated"))
        assert r1.id == r2.id

    def test_different_severities_are_independent_records(self, service: GuidanceService):
        _, c1 = service.upsert(make_upsert(severity="high"))
        _, c2 = service.upsert(make_upsert(severity="critical"))
        assert c1 is True
        assert c2 is True

    def test_last_updated_populated_on_create(self, service: GuidanceService):
        response, _ = service.upsert(make_upsert())
        assert response.last_updated is not None


# =========================================================================== #
#  get_by_id()                                                                 #
# =========================================================================== #

class TestServiceGetById:

    def test_returns_correct_record(self, service: GuidanceService):
        created, _ = service.upsert(make_upsert())
        fetched = service.get_by_id(created.id)
        assert fetched.id == created.id
        assert fetched.metric_name == created.metric_name

    def test_raises_not_found_for_missing_id(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError):
            service.get_by_id(99999)

    def test_not_found_message_contains_id(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError, match="99999"):
            service.get_by_id(99999)


# =========================================================================== #
#  get_by_natural_key()                                                        #
# =========================================================================== #

class TestServiceGetByNaturalKey:

    def test_returns_correct_record(self, service: GuidanceService):
        service.upsert(make_upsert(metric_name="latency", severity="critical"))
        record = service.get_by_natural_key("latency", "critical")
        assert record.metric_name == "latency"
        assert record.severity == "critical"

    def test_raises_not_found_for_missing_key(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError):
            service.get_by_natural_key("ghost", "low")

    def test_wrong_severity_raises_not_found(self, service: GuidanceService):
        service.upsert(make_upsert(metric_name="cpu_usage", severity="high"))
        with pytest.raises(GuidanceNotFoundError):
            service.get_by_natural_key("cpu_usage", "low")


# =========================================================================== #
#  list()                                                                      #
# =========================================================================== #

class TestServiceList:

    def _seed(self, service: GuidanceService):
        service.upsert(make_upsert("cpu_usage", "high", Priority.P1))
        service.upsert(make_upsert("cpu_usage", "critical", Priority.P1))
        service.upsert(make_upsert("memory_usage", "high", Priority.P2))
        service.upsert(make_upsert("disk_io", "low", Priority.P4))

    def test_returns_all_records(self, service: GuidanceService):
        self._seed(service)
        result = service.list()
        assert result.total == 4
        assert len(result.items) == 4

    def test_filter_by_priority(self, service: GuidanceService):
        self._seed(service)
        result = service.list(priority=Priority.P1)
        assert result.total == 2
        assert all(r.priority == Priority.P1 for r in result.items)

    def test_filter_by_metric_name(self, service: GuidanceService):
        self._seed(service)
        result = service.list(metric_name="cpu")
        assert result.total == 2

    def test_filter_by_severity(self, service: GuidanceService):
        self._seed(service)
        result = service.list(severity="high")
        assert result.total == 2

    def test_pagination(self, service: GuidanceService):
        self._seed(service)
        result = service.list(skip=0, limit=2)
        assert result.total == 4
        assert len(result.items) == 2

    def test_empty_result(self, service: GuidanceService):
        result = service.list()
        assert result.total == 0
        assert result.items == []

    def test_no_match_filter_returns_empty(self, service: GuidanceService):
        self._seed(service)
        result = service.list(metric_name="nonexistent")
        assert result.total == 0


# =========================================================================== #
#  update_by_id()                                                              #
# =========================================================================== #

class TestServiceUpdateById:

    def test_updates_resolver_notes(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert())
        updated = service.update_by_id(r.id, GuidanceUpdate(resolver_notes="New note"))
        assert updated.resolver_notes == "New note"

    def test_updates_resolution_steps(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert())
        steps = [{"step": 1, "action": "Reboot"}]
        updated = service.update_by_id(r.id, GuidanceUpdate(resolution_steps=steps))
        assert updated.resolution_steps == steps

    def test_updates_resolution_meta(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert())
        updated = service.update_by_id(r.id, GuidanceUpdate(resolution_meta={"sla_minutes": 5}))
        assert updated.resolution_meta == {"sla_minutes": 5}

    def test_patch_leaves_unset_fields_unchanged(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert(resolver_notes="Keep", resolution_meta={"keep": 1}))
        service.update_by_id(r.id, GuidanceUpdate(resolution_steps=[{"step": 99}]))
        fetched = service.get_by_id(r.id)
        assert fetched.resolver_notes == "Keep"
        assert fetched.resolution_meta == {"keep": 1}

    def test_raises_not_found_for_missing_id(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError):
            service.update_by_id(99999, GuidanceUpdate(resolver_notes="x"))

    def test_natural_key_unchanged_after_patch(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert())
        updated = service.update_by_id(r.id, GuidanceUpdate(resolver_notes="x"))
        assert updated.metric_name == r.metric_name
        assert updated.severity == r.severity


# =========================================================================== #
#  update_by_natural_key()                                                     #
# =========================================================================== #

class TestServiceUpdateByNaturalKey:

    def test_updates_via_natural_key(self, service: GuidanceService):
        service.upsert(make_upsert(metric_name="latency", severity="high"))
        updated = service.update_by_natural_key(
            "latency", "high", GuidanceUpdate(resolver_notes="Via key")
        )
        assert updated.resolver_notes == "Via key"

    def test_raises_not_found_for_missing_key(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError):
            service.update_by_natural_key("ghost", "low", GuidanceUpdate(resolver_notes="x"))


# =========================================================================== #
#  delete_by_id()                                                              #
# =========================================================================== #

class TestServiceDeleteById:

    def test_deletes_existing_record(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert())
        result = service.delete_by_id(r.id)
        assert result == {"deleted": True, "id": r.id}

    def test_record_gone_after_delete(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert())
        service.delete_by_id(r.id)
        with pytest.raises(GuidanceNotFoundError):
            service.get_by_id(r.id)

    def test_raises_not_found_for_missing_id(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError):
            service.delete_by_id(99999)

    def test_only_target_record_deleted(self, service: GuidanceService):
        r1, _ = service.upsert(make_upsert(metric_name="cpu_usage"))
        service.upsert(make_upsert(metric_name="memory_usage"))
        service.delete_by_id(r1.id)
        result = service.list()
        assert result.total == 1


# =========================================================================== #
#  delete_by_natural_key()                                                     #
# =========================================================================== #

class TestServiceDeleteByNaturalKey:

    def test_deletes_by_natural_key(self, service: GuidanceService):
        service.upsert(make_upsert(metric_name="disk_io", severity="critical"))
        result = service.delete_by_natural_key("disk_io", "critical")
        assert result == {"deleted": True, "metric_name": "disk_io", "severity": "critical"}

    def test_record_gone_after_delete(self, service: GuidanceService):
        service.upsert(make_upsert(metric_name="disk_io", severity="critical"))
        service.delete_by_natural_key("disk_io", "critical")
        with pytest.raises(GuidanceNotFoundError):
            service.get_by_natural_key("disk_io", "critical")

    def test_raises_not_found_for_missing_key(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError):
            service.delete_by_natural_key("ghost_metric", "low")


# =========================================================================== #
#  get_resolution_steps()                                                      #
# =========================================================================== #

class TestServiceGetResolutionSteps:

    def test_returns_steps_list(self, service: GuidanceService):
        steps = [{"step": 1, "action": "Restart"}, {"step": 2, "action": "Monitor"}]
        service.upsert(make_upsert(resolution_steps=steps))
        result = service.get_resolution_steps("cpu_usage", "high")
        assert result == steps

    def test_returns_empty_list_when_steps_none(self, service: GuidanceService):
        service.upsert(make_upsert(resolution_steps=[]))
        result = service.get_resolution_steps("cpu_usage", "high")
        assert result == []

    def test_raises_not_found_for_missing_key(self, service: GuidanceService):
        with pytest.raises(GuidanceNotFoundError):
            service.get_resolution_steps("nonexistent", "high")


# =========================================================================== #
#  summarize_by_priority()                                                     #
# =========================================================================== #

class TestServiceSummarizeByPriority:

    def test_all_priorities_present_in_output(self, service: GuidanceService):
        result = service.summarize_by_priority()
        assert set(result.keys()) == {"P1", "P2", "P3", "P4"}

    def test_zero_counts_on_empty_db(self, service: GuidanceService):
        result = service.summarize_by_priority()
        assert all(v == 0 for v in result.values())

    def test_counts_correct_after_inserts(self, service: GuidanceService):
        service.upsert(make_upsert("cpu_usage", "high", Priority.P1))
        service.upsert(make_upsert("cpu_usage", "critical", Priority.P1))
        service.upsert(make_upsert("memory_usage", "high", Priority.P2))
        service.upsert(make_upsert("disk_io", "low", Priority.P4))

        result = service.summarize_by_priority()
        assert result["P1"] == 2
        assert result["P2"] == 1
        assert result["P3"] == 0
        assert result["P4"] == 1

    def test_count_reflects_delete(self, service: GuidanceService):
        r, _ = service.upsert(make_upsert(priority=Priority.P1))
        service.upsert(make_upsert("memory_usage", "high", Priority.P1))

        service.delete_by_id(r.id)
        result = service.summarize_by_priority()
        assert result["P1"] == 1
