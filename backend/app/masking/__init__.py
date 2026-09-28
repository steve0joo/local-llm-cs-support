"""개인정보 마스킹 (계약 4). 게이트웨이와 모든 학습 스크립트가 같은 `mask`를 쓴다."""
from app.masking.mask import MaskResult, mask

__all__ = ["MaskResult", "mask"]
