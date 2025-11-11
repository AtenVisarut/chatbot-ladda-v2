"""
Base agent class that defines the interface for all agents
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name
    
    @abstractmethod
    async def process(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Process the input data and return results
        """
        pass
    
    @abstractmethod
    async def can_handle(self, data: Dict[str, Any]) -> bool:
        """
        Check if this agent can handle the given input
        """
        pass