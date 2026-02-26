import json
from typing import Any

from bot import CACHE, FORWARD_MODE_KEY, LOGS, SOURCE_INDEX, db


def _index_add(work_name: str, sources: list[int]) -> None:
    """Add a task to SOURCE_INDEX for each of its source chat IDs."""
    for src in sources:
        SOURCE_INDEX.setdefault(src, set()).add(work_name)


def _index_remove(work_name: str, sources: list[int]) -> None:
    """Remove a task from SOURCE_INDEX for each of its source chat IDs."""
    for src in sources:
        bucket = SOURCE_INDEX.get(src)
        if bucket:
            bucket.discard(work_name)
            if not bucket:
                del SOURCE_INDEX[src]


async def get_work(work_name: str) -> dict:
    """Get a task by name from the local cache."""
    return CACHE.get(work_name) or {}


async def is_work_present(work_name: str) -> bool:
    """Check if a task name already exists."""
    return bool(CACHE.get(work_name))


async def get_all_work_names() -> list[str]:
    """Return all task names (excluding system keys)."""
    return [k for k in CACHE.keys() if k != FORWARD_MODE_KEY]


async def get_tasks_for_source(source_id: int) -> list[dict]:
    """Return all tasks that have the given source_id — O(1) via SOURCE_INDEX."""
    task_names = SOURCE_INDEX.get(source_id)
    if not task_names:
        return []
    return [CACHE[name] for name in task_names if name in CACHE]


async def setup_work(work_name: str, source: list[int], target: list[int]) -> None:
    """Create a new forwarding task with default settings."""
    data = {
        "work_name": work_name,
        "source": source,
        "target": target,
        "show_forward_header": False,
        "delay": 0,
        "blacklist_words": [],
        "crossids": {},
        "has_to_edit": False,
        "has_to_blacklist": False,
        "has_to_forward": True,
    }
    CACHE[work_name] = data
    _index_add(work_name, source)
    await _persist(work_name, data)


async def edit_work(work_name: str, **kwargs: Any) -> bool:
    """Update specific fields of an existing task."""
    task_data = await get_work(work_name)
    if not task_data:
        return False

    # If source list is changing, update the index
    if "source" in kwargs:
        old_sources = task_data.get("source") or []
        new_sources = kwargs["source"]
        _index_remove(work_name, old_sources)
        _index_add(work_name, new_sources)

    task_data.update(kwargs)
    CACHE[work_name] = task_data
    await _persist(work_name, task_data)
    return True


async def delete_work(work_name: str) -> None:
    """Delete a task from both cache and Redis."""
    task_data = CACHE.pop(work_name, None)
    if task_data:
        _index_remove(work_name, task_data.get("source") or [])
    await db.delete(work_name)


async def rename_work(old_name: str, new_name: str) -> None:
    """Rename a task, updating both cache and Redis."""
    data = CACHE.pop(old_name, None)
    if data:
        # Update index: remove old name, add new name
        sources = data.get("source") or []
        _index_remove(old_name, sources)
        data["work_name"] = new_name
        CACHE[new_name] = data
        _index_add(new_name, sources)
    await db.rename(old_name, new_name)
    await _persist(new_name, CACHE.get(new_name, {}))


async def _persist(work_name: str, data: dict) -> None:
    """Persist task data to Redis as JSON."""
    try:
        await db.set(work_name, json.dumps(data))
    except Exception as e:
        LOGS.error("Failed to persist task '%s' to Redis: %s", work_name, e)
