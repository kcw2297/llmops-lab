# 하네스 개선 기록

| 날짜 | 대상 | 문제/피드백 | 변경 내용 | 반영 여부 |
|---|---|---|---|---|
| 2026-11-18 | 전체 | - | 최초 구성 | ✅ |
| 2026-11-18 | 폴더 구조 | 루트 `agents/`가 `.claude/agents/`와 헷갈림 | `apps/`로 변경, agent-developer·agent-build·CLAUDE.md 경로 수정 | ✅ |
| 2026-11-18 | 레포 구조 | 모듈 경계와 실험 관리 기준이 불명확함 | 구조 원칙 P1~P6, uv workspace(core/eval/app), 앱 1개 고정, 실험 ID `{YYYYMMDD}-m{n}-{slug}`, 측정 원본은 artifacts/…/results로 이동. 스킬 5개·agent 3개·CLAUDE.md 수정 | ✅ |
| 2026-11-19 | 레포 분리 | 실제 업무(형님 회사) 데이터를 Public 레포에 둘 수 없음 | `app/` 제거, 앱은 Private `biz-automation`으로 분리, CLAUDE.md 실데이터 금지 규칙, reviewer 8번 항목 추가, agent-developer·agent-build 경로 수정 | ✅ |
