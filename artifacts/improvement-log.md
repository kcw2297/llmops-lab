# 하네스 개선 기록

| 날짜 | 대상 | 문제/피드백 | 변경 내용 | 반영 여부 |
|---|---|---|---|---|
| 2026-11-18 | 전체 | - | 최초 구성 | ✅ |
| 2026-11-18 | 폴더 구조 | 루트 `agents/`가 `.claude/agents/`와 헷갈림 | `apps/`로 변경, agent-developer·agent-build·CLAUDE.md 경로 수정 | ✅ |
| 2026-11-18 | 레포 구조 | 모듈 경계와 실험 관리 기준이 불명확함 | 구조 원칙 P1~P6, uv workspace(core/eval/app), 앱 1개 고정, 실험 ID `{YYYYMMDD}-m{n}-{slug}`, 측정 원본은 artifacts/…/results로 이동. 스킬 5개·agent 3개·CLAUDE.md 수정 | ✅ |
| 2026-11-19 | 레포 분리 | 실제 업무(형님 회사) 데이터를 Public 레포에 둘 수 없음 | `app/` 제거, 앱은 Private `biz-automation`으로 분리, CLAUDE.md 실데이터 금지 규칙, reviewer 8번 항목 추가, agent-developer·agent-build 경로 수정 | ✅ |
| 2026-11-20 | 로드맵 | 앱의 모델 용도가 자연어 LLM이 아니라 문서 AI(OCR 추출·병합)로 확정됨 | 로드맵 주제를 VLM 문서 추출로 변경 (M1 멀티모달 서빙, M4 양식별 LoRA, M5 필드 정답률 평가, M6 biz-automation 2단계) | ✅ |
| 2026-11-20 | 앱 레포 이름 | 앱이 OCR 중심으로 확정됨 | `biz-automation` → `ocr-docflow` (CLAUDE.md, agent-developer, agent-build, roadmap, pyproject 주석) | ✅ |
| 2026-11-20 | 레포 이름 | OCR 중심으로 프로젝트 정체성 통일 | `llmops-lab` → `ocr-model`, 오케스트레이터 `ocr-model-orchestrator`, 앱 레포 `ocr-agent` 참조 수정 | ✅ |
