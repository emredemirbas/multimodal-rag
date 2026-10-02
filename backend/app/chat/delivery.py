"""SSE transports only validated persisted answers; it never executes evidence."""
import json

from starlette.concurrency import run_in_threadpool

from .contracts import ChatTurn


def frame(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


async def deliver(repository, tenant, project, actor, conversation, turn: ChatTurn):
    try:
        if not await run_in_threadpool(repository.readable, tenant, project, actor, conversation, turn.id):
            yield frame("error", {"code": "evidence_unavailable"})
            return
        yield frame("start", {"id": str(turn.id), "sequence": turn.sequence})
        for offset in range(0, len(turn.response.answer), 256):
            if not await run_in_threadpool(repository.readable, tenant, project, actor, conversation, turn.id):
                yield frame("error", {"code": "evidence_unavailable"})
                return
            yield frame("delta", {"text": turn.response.answer[offset:offset+256]})
        if await run_in_threadpool(repository.readable, tenant, project, actor, conversation, turn.id):
            yield frame("complete", turn.model_dump(mode="json"))
        else:
            yield frame("error", {"code": "evidence_unavailable"})
    except Exception:
        yield frame("error", {"code": "stream_unavailable"})
