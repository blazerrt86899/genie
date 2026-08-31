"""Task service (CLAUDE.md §12)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from app.core.exceptions import NotFoundError
from app.services import task_service
from app.services.task_service import TaskValidationError


def _task(**kw):
    now = SimpleNamespace(isoformat=lambda: "2026-08-31T00:00:00+00:00")
    base = dict(
        id=uuid.uuid4(),
        title="buy milk",
        description=None,
        status="todo",
        conversation_id=None,
        source_agent="task_creator",
        created_at=now,
        updated_at=now,
        archived_at=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


class FakeRepo:
    """Class-level state so monkeypatched instances share it."""

    store: dict[uuid.UUID, SimpleNamespace] = {}
    archived: int = 0

    def __init__(self, _db) -> None: ...

    async def create(self, user_id, title, **kw):
        t = _task(title=title, user_id=user_id, **kw)
        FakeRepo.store[t.id] = t
        return t

    async def get_for_user(self, task_id, user_id):
        return FakeRepo.store.get(task_id)

    async def list_for_user(self, user_id, *, include_archived=False):
        return [
            t
            for t in FakeRepo.store.values()
            if include_archived or t.status != "archived"
        ]

    async def find_by_title(self, user_id, query):
        return next(
            (t for t in FakeRepo.store.values() if query.lower() in t.title.lower()), None
        )

    async def set_status(self, task_id, user_id, status):
        t = FakeRepo.store.get(task_id)
        if t:
            t.status = status
        return t

    async def update(self, task_id, user_id, **fields):
        t = FakeRepo.store.get(task_id)
        if t:
            if fields.get("title") is not None:
                t.title = fields["title"]
            if "description" in fields:
                t.description = fields["description"]
        return t

    async def archive_done(self, user_id):
        n = 0
        for t in FakeRepo.store.values():
            if t.status == "done":
                t.status = "archived"
                n += 1
        return n

    async def delete_for_user(self, task_id, user_id):
        return FakeRepo.store.pop(task_id, None) is not None


class FakeMsgRepo:
    messages: list = []

    def __init__(self, _db) -> None: ...

    async def list_for_conversation(self, conversation_id, limit=200):
        return FakeMsgRepo.messages


@pytest.fixture(autouse=True)
def _patch(monkeypatch):
    FakeRepo.store = {}
    FakeMsgRepo.messages = []
    monkeypatch.setattr(task_service, "TaskRepository", FakeRepo)
    monkeypatch.setattr(task_service, "MessageRepository", FakeMsgRepo)


_UID = uuid.uuid4()


async def test_create_and_list():
    t = await task_service.create_task(None, _UID, "  buy milk  ", source_agent="task_creator")
    assert t.title == "buy milk" and t.status == "todo"
    tasks = await task_service.list_tasks(None, _UID)
    assert [x.title for x in tasks] == ["buy milk"]


async def test_create_rejects_empty_title():
    with pytest.raises(TaskValidationError):
        await task_service.create_task(None, _UID, "   ")


async def test_move_validates_status():
    t = await task_service.create_task(None, _UID, "x")
    with pytest.raises(TaskValidationError):
        await task_service.move_task(None, _UID, t.id, "bogus")
    moved = await task_service.move_task(None, _UID, t.id, "in_progress")
    assert moved.status == "in_progress"


async def test_move_missing_task_404():
    with pytest.raises(NotFoundError):
        await task_service.move_task(None, _UID, uuid.uuid4(), "done")


async def test_archive_done_and_board_filter():
    a = await task_service.create_task(None, _UID, "a")
    b = await task_service.create_task(None, _UID, "b")
    await task_service.move_task(None, _UID, a.id, "done")
    n = await task_service.archive_done(None, _UID)
    assert n == 1
    board = await task_service.list_tasks(None, _UID)
    assert {x.title for x in board} == {"b"}
    everything = await task_service.list_tasks(None, _UID, include_archived=True)
    assert {x.title for x in everything} == {"a", "b"}
    assert b  # keep ref


async def test_find_task():
    await task_service.create_task(None, _UID, "quarterly report draft")
    m = await task_service.find_task(None, _UID, "report")
    assert m and "report" in m.title


async def test_to_dict_shape():
    t = await task_service.create_task(None, _UID, "x")
    d = task_service.to_dict(t)
    assert set(d) == {
        "id", "title", "description", "status", "conversation_id",
        "source_agent", "created_at", "updated_at", "archived_at",
    }


async def test_summarize_writes_description(monkeypatch):
    conv = uuid.uuid4()
    t = await task_service.create_task(None, _UID, "ship the release", conversation_id=conv)
    FakeMsgRepo.messages = [
        SimpleNamespace(role="user", content="we need to ship v2 friday"),
        SimpleNamespace(role="assistant", content="ok, blockers are the migration and QA"),
    ]

    async def fake_summarise(title, transcript):
        assert "ship the release" in title
        assert "v2 friday" in transcript
        return "Ship v2 on Friday. Blockers: the DB migration and QA. Agreed to prioritise both."

    monkeypatch.setattr(task_service, "_summarise", fake_summarise)

    out = await task_service.summarize_task(None, _UID, t.id)
    assert out.description.startswith("Ship v2 on Friday")


async def test_summarize_needs_a_linked_chat():
    t = await task_service.create_task(None, _UID, "no chat")  # no conversation_id
    with pytest.raises(TaskValidationError):
        await task_service.summarize_task(None, _UID, t.id)
