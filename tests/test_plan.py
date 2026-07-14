"""TaskPlan 校验与进度快照逻辑单测。"""

from __future__ import annotations

from tangyuan.agent.plan import TaskPlan


def test_replace_valid_items() -> None:
    plan = TaskPlan()
    res = plan.replace([{"id": "a", "content": "步骤A", "status": "pending"}])
    assert res["ok"] is True
    assert len(plan.items) == 1
    assert plan.items[0].id == "a"


def test_reject_empty_items() -> None:
    plan = TaskPlan()
    res = plan.replace([])
    assert res["ok"] is False


def test_reject_duplicate_id() -> None:
    plan = TaskPlan()
    res = plan.replace(
        [
            {"id": "a", "content": "x"},
            {"id": "a", "content": "y"},
        ]
    )
    assert res["ok"] is False
    assert "重复" in res["error"]


def test_reject_multiple_in_progress() -> None:
    plan = TaskPlan()
    res = plan.replace(
        [
            {"id": "a", "content": "x", "status": "in_progress"},
            {"id": "b", "content": "y", "status": "in_progress"},
        ]
    )
    assert res["ok"] is False


def test_reject_invalid_status() -> None:
    plan = TaskPlan()
    res = plan.replace([{"id": "a", "content": "x", "status": "done"}])
    assert res["ok"] is False


def test_merge_updates_and_appends() -> None:
    plan = TaskPlan()
    plan.replace([{"id": "a", "content": "A", "status": "pending"}])
    res = plan.merge(
        [
            {"id": "a", "content": "A", "status": "completed"},
            {"id": "b", "content": "B", "status": "in_progress"},
        ]
    )
    assert res["ok"] is True
    by_id = {i.id: i for i in plan.items}
    assert by_id["a"].status == "completed"
    assert by_id["b"].status == "in_progress"


def test_open_items_and_progress_key() -> None:
    plan = TaskPlan()
    plan.replace(
        [
            {"id": "a", "content": "A", "status": "completed"},
            {"id": "b", "content": "B", "status": "in_progress"},
            {"id": "c", "content": "C", "status": "pending"},
        ]
    )
    open_ids = {i.id for i in plan.open_items()}
    assert open_ids == {"b", "c"}

    completed, cancelled, in_prog, pending = plan.progress_key()
    assert completed == ("a",)
    assert in_prog == ("b",)
    assert pending == ("c",)
