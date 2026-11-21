"""`.env` 로더와 LLM 접속 설정.

백엔드 비유: 12-factor 앱의 환경변수 설정 객체. 값은 `.env` 또는 프로세스 환경변수에서만 읽고,
코드·config·로그에는 쓰지 않는다. `repr`도 키와 URL을 가린다.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def find_repo_root(start: Path | None = None) -> Path:
    """`.git` 또는 workspace `pyproject.toml`([tool.uv.workspace])이 있는 가장 가까운 상위 폴더."""
    here = (start or Path.cwd()).resolve()
    for p in [here, *here.parents]:
        if (p / ".git").exists():
            return p
        pp = p / "pyproject.toml"
        if pp.exists() and "[tool.uv.workspace]" in pp.read_text(encoding="utf-8"):
            return p
    return here


def load_dotenv(path: Path | None = None, *, override: bool = False) -> None:
    """의존성 없는 최소 `.env` 파서. `KEY=VALUE`, 주석(#), 따옴표만 처리한다.

    이미 설정된 환경변수는 덮어쓰지 않는다(override=False). 셸에서 준 값이 우선이다.
    """
    path = path or find_repo_root() / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip().removeprefix("export ").strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if override or key not in os.environ:
            os.environ[key] = value


@dataclass(frozen=True)
class LLMSettings:
    base_url: str = field(repr=False)
    api_key: str = field(repr=False)
    model: str | None = None

    def __repr__(self) -> str:  # 키·URL 노출 방지
        return f"LLMSettings(base_url=<env:LLM_BASE_URL>, api_key=<env:LLM_API_KEY>, model={self.model!r})"

    def redact(self, text: str) -> str:
        """에러 메시지 등에 섞여 들어온 URL·키를 가린다. 결과 파일에 쓰기 전에 항상 통과시킨다."""
        out = text
        if self.api_key:
            out = out.replace(self.api_key, "<LLM_API_KEY>")
        if self.base_url:
            base = self.base_url.rstrip("/")
            host = base.split("://", 1)[-1].split("/", 1)[0]
            out = out.replace(base, "<LLM_BASE_URL>")
            if host:
                out = out.replace(host, "<LLM_HOST>")
        return out


def llm_settings(*, require: bool = True) -> LLMSettings:
    """`.env`를 읽어 `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`을 돌려준다."""
    load_dotenv()
    base_url = os.environ.get("LLM_BASE_URL", "").strip()
    api_key = os.environ.get("LLM_API_KEY", "").strip()
    model = os.environ.get("LLM_MODEL", "").strip() or None
    if require:
        missing = [k for k, v in (("LLM_BASE_URL", base_url), ("LLM_API_KEY", api_key)) if not v]
        if "<endpoint>" in base_url:
            missing.append("LLM_BASE_URL(예시값 그대로)")
        if missing:
            raise RuntimeError(f".env에 값이 없습니다: {', '.join(missing)} (값은 출력하지 않음)")
    return LLMSettings(base_url=base_url, api_key=api_key, model=model)
