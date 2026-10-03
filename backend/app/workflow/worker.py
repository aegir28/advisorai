"""The in-process worker loop (blueprint p. 41: "Worker loop (in-process for prototype)").

Picks a queued run, keeps its lease alive while the engine works, and gives the run back on shutdown. If the
lease is lost (another worker took over after a stall) the engine is cancelled and nothing more is written.
"""

import asyncio
import contextlib
import logging
import uuid
from typing import Any

from app.workflow.engine import Engine, LeaseLostError
from app.workflow.repository import WorkflowRepository

logger = logging.getLogger("advisorai.worker")


class Worker:
    def __init__(
        self,
        repository: WorkflowRepository,
        engine: Engine,
        *,
        worker_id: str | None = None,
        lease_seconds: int = 60,
        poll_interval: float = 2.0,
    ) -> None:
        self._repo = repository
        self._engine = engine
        self.worker_id = worker_id or f"worker-{uuid.uuid4().hex[:8]}"
        self._lease = lease_seconds
        self._poll = poll_interval

    async def run_once(self) -> bool:
        """Claim and execute one run. False when the queue was empty."""
        await self._repo.fail_exhausted()
        run = await self._repo.claim_next(self.worker_id, self._lease)
        if run is None:
            return False

        async def renew() -> bool:
            return await self._repo.extend_lease(run.id, self.worker_id, self._lease)

        lost = asyncio.Event()
        task = asyncio.ensure_future(self._engine.execute(run, self.worker_id, renew))
        heartbeat = asyncio.ensure_future(self._heartbeat(run.id, task, lost))
        try:
            await task
        except LeaseLostError:
            logger.warning("run %s was taken over by another worker", run.id)
        except asyncio.CancelledError:
            if lost.is_set():
                logger.warning("run %s: lease lost mid-step; stopped", run.id)
                return True
            task.cancel()
            await self._repo.release(run.id, self.worker_id)  # clean shutdown: hand the run back
            raise
        except Exception:
            # The engine records node failures itself; this is a bug or an outage. The lease expires and the
            # run is retried (and failed after MAX_RUN_ATTEMPTS). Type only: never message content.
            logger.error("run %s: engine crashed", run.id, exc_info=False)
        finally:
            heartbeat.cancel()
        return True

    async def _heartbeat(self, run_id: uuid.UUID, task: "asyncio.Future[Any]", lost: asyncio.Event) -> None:
        try:
            while not task.done():
                await asyncio.sleep(self._lease / 3)
                if not await self._repo.extend_lease(run_id, self.worker_id, self._lease):
                    lost.set()
                    task.cancel()
                    return
        except asyncio.CancelledError:
            return

    async def run_forever(self, stop: asyncio.Event) -> None:
        logger.info("worker %s started", self.worker_id)
        while not stop.is_set():
            try:
                worked = await self.run_once()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.error("worker iteration failed", exc_info=False)
                worked = False
            if not worked:
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=self._poll)
        logger.info("worker %s stopped", self.worker_id)
