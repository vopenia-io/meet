import abc
from dataclasses import dataclass
from celery import Celery
from livekit.agents import WorkerOptions, WorkerPermissions, cli, worker

@dataclass
class AgentInfo:
    name: str
    enabled: bool

class AbstractAgent(abc.ABC):
    """Abstract base class for all agents."""

    @staticmethod
    @abc.abstractmethod
    def info() -> AgentInfo:
        """Return information about the agent."""
        pass
    
    @property
    @abc.abstractmethod
    def options(self) -> WorkerOptions:
        """Return the options for the agent."""
        pass

    @classmethod
    def auto_register(cls, app: Celery):
        from .factory import AgentFactory
        AgentFactory.register_agent(cls)
        AgentFactory.register_factory(app)

