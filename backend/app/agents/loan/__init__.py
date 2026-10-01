"""대출문의 에이전트. agent·mock_router export(계약 3)."""
from app.agents.loan.agent import agent
from app.agents.loan.mock_api import mock_router

__all__ = ["agent", "mock_router"]
