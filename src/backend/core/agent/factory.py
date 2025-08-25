import asyncio
from typing import Type
from attr import dataclass
from celery import Celery, bootsteps
from celery.utils.log import get_logger
import threading

from django.conf import settings
from core.agent.agent import AbstractAgent, AgentInfo
from livekit.agents import Worker
from dataclasses import asdict


class AgentFactory(bootsteps.StartStopStep):
    require = {"celery.worker.components:Logging", "celery.worker.components:Pool"}

    _AGENTS: list[tuple[AgentInfo, Type[AbstractAgent]]] = []
    _registered = False

    def __init__(self, worker, **kwargs):
        super().__init__(worker, **kwargs)
        self.logger = get_logger(__name__)
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._aloop: asyncio.AbstractEventLoop | None = None

        self._agents = [
            (info, agent()) for (info, agent) in self._AGENTS if info.enabled
        ]
        self._workers: list[tuple[AgentInfo, Worker, asyncio.Task]] = []
        self._main_task: asyncio.Task | None = None
        self._shutdown_event: asyncio.Event | None = None
        self._shutting_down = False
        self.logger.info(f"AgentFactory initialized with {len(self._agents)} agents")

    def start(self, parent):
        self._thread.start()

    def stop(self, parent):
        self.logger.info("Stopping AgentFactory")
        if self._aloop is not None and not self._shutting_down:
            try:
                fut = asyncio.run_coroutine_threadsafe(self._graceful_shutdown(), self._aloop)
                fut.result(timeout=30)
            except Exception as e:
                self.logger.error(f"Error during graceful shutdown: {e}")
        self.logger.info("Waiting for AgentFactory thread to finish")
        self._thread.join(timeout=10)
        if self._thread.is_alive():
            self.logger.warning("AgentFactory thread did not exit cleanly")

    @classmethod
    def register_agent(cls, agent: Type[AbstractAgent]):
        info = agent.info()
        cls._AGENTS.append((info, agent))
        print(f"Registered agent: {info.name}")

    @classmethod
    def register_factory(cls, app: Celery):
        if cls._registered:
            return
        if app is None or app.steps is None:
            raise ValueError(
                "Celery app must be initialized before registering agents."
            )
        app.steps["worker"].add(AgentFactory)

    async def _run(self):
        if self._aloop is None:
            raise RuntimeError("Event loop is not initialized")
        self._shutdown_event = asyncio.Event()

        workers: list[tuple[AgentInfo, Worker]] = []
        self.logger.info("Configuring agents")
        for info, agent in self._agents:
            self.logger.debug(f"Agent {info.name} options: {asdict(agent.options)}")
            worker = Worker(
                opts=agent.options,
                devmode=settings.DEBUG,
            )
            workers.append((info, worker))
        self.logger.info(f"Total agents configured: {len(workers)}")
        if not workers:
            self.logger.info("No agents configured")
            await self._shutdown_event.wait()
            return

        self.logger.info("Starting agents")
        for (info, worker) in workers:
            self.logger.debug(f"Starting agent: {info.name}")
            task = asyncio.create_task(worker.run(), name=f"agent:{info.name}")
            self._workers.append((info, worker, task))

        self.logger.info("Agents started")
        await self._shutdown_event.wait()

    async def _graceful_shutdown(self):
        if self._shutting_down:
            return
        self._shutting_down = True
        self.logger.info("Graceful shutdown initiated")
        for (info, worker, task) in self._workers:
            if task.done():
                continue
            self.logger.debug(f"Draining agent: {info.name}")
            try:
                await worker.drain(timeout=10)
            except Exception as e:
                self.logger.error(f"Drain failed for {info.name}: {e}")
        pending = [(i, w, t) for (i, w, t) in self._workers if not t.done()]
        if pending:
            self.logger.debug(f"Waiting for {len(pending)} agent tasks to finish")
            done, not_done = await asyncio.wait([t for (_, _, t) in pending], timeout=15)
            self.logger.debug(f"{len(done)} agent tasks completed, {len(not_done)} still running")
            for (i, w, t) in pending:
                if t in done:
                    continue
                self.logger.warning(f"Agent task still running: {i.name}")
                await w.aclose()
            done, not_done = await asyncio.wait(not_done, timeout=5)
            for t in not_done:
                self.logger.warning(f"Cancelling stuck agent task: {t.get_name()}")
                t.cancel()
            if not_done:
                await asyncio.gather(*not_done, return_exceptions=True)
        close_tasks = [worker.aclose() for (_, worker, _) in self._workers]
        if close_tasks:
            try:
                await asyncio.gather(*close_tasks, return_exceptions=True)
            except Exception as e:
                self.logger.error(f"Error during worker close: {e}")
        self.logger.info("All agents stopped")
        if self._shutdown_event and not self._shutdown_event.is_set():
            self._shutdown_event.set()

    def _loop(self):
        self._aloop = asyncio.new_event_loop()
        try:
            self._main_task = self._aloop.create_task(self._run(), name="AgentFactoryMain")
            def _done(_):
                if self._aloop:
                    self._aloop.call_soon_threadsafe(self._aloop.stop)
            self._main_task.add_done_callback(_done)

            self._aloop.run_forever()

            if self._main_task and self._main_task.done():
                try:
                    self._main_task.result()
                except Exception as e:
                    self.logger.error(f"AgentFactory main task error: {e}")
            self.logger.debug("AgentFactory loop finished")
        finally:
            try:
                if self._aloop:
                    pending = [t for t in asyncio.all_tasks(self._aloop) if t is not self._main_task]
                    for t in pending:
                        t.cancel()
                    if pending:
                        self._aloop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            finally:
                if self._aloop:
                    self._aloop.close()
                self._aloop = None
                self._main_task = None
                self._shutdown_event = None
                self._workers.clear()
