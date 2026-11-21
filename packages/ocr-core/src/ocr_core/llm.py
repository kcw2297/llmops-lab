"""OpenAI 호환 클라이언트 팩토리 (vLLM 서빙 엔드포인트용)."""

from __future__ import annotations

from openai import OpenAI

from ocr_core.settings import LLMSettings


def make_client(settings: LLMSettings, *, timeout_s: float = 120.0, max_retries: int = 0) -> OpenAI:
    """재시도는 기본 0회. 측정 지연에 SDK 재시도 시간이 섞이지 않게 한다."""
    return OpenAI(
        base_url=settings.base_url,
        api_key=settings.api_key,
        timeout=timeout_s,
        max_retries=max_retries,
    )
