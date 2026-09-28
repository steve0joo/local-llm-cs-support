"""모델 호출 (계약 5). 모든 모델 호출은 `generate` 하나를 거친다. 호출하는 쪽은 `from app import llm` 뒤 `llm.generate(...)`."""
from app.llm.client import generate

__all__ = ["generate"]
