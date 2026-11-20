---
name: ocr-model-orchestrator
description: RunPod 오픈소스 LLM 실험(서빙, 부하 테스트, 양자화, LoRA/QLoRA 파인튜닝, 평가, 에이전트 개발)의 전체 진행을 맡는 입구 스킬. "모델 띄워줘", "vLLM 서빙", "파인튜닝 해보자", "평가 돌려줘", "에이전트 만들어줘" 같은 요청과 "다시 실행", "재실행", "eval만 다시", "설정만 바꿔서", "이전 결과 기반 보완", "업데이트", "로드맵 진도/다음 실험" 같은 후속 요청에 사용한다. 개념 질문만 하는 경우와 하네스와 무관한 일반 코딩에는 사용하지 않는다.
---

# ocr-model Orchestrator

실험 1건을 **계획 → 견적·승인 → 실행 → 평가 → 리뷰 → 정리 → 학습 노트 → 리포트**로 진행하고, 모든 단계를 `artifacts/experiments/{id}/`에 파일로 남긴다.

## Phase 0. 모드 확인

1. `artifacts/cost-ledger.md`를 읽고 이번 달 누적 비용을 계산한다. 100% 이상이면 즉시 멈추고 사용자에게 알린다.
2. `artifacts/learning/roadmap.md`를 읽고 현재 마일스톤을 파악한다.
3. 요청을 분류한다.

| 모드 | 판단 기준 | 처리 |
|---|---|---|
| 개념 질문 | 실행 없이 이해만 원함 | `learning-note`만 실행하고 끝 |
| 새 실험 | 새로운 목표 | `{YYYYMMDD}-m{n}-{slug}` 폴더를 만들고 Phase 1부터 (예: `20261120-m1-qwen3-8b-vllm`) |
| 부분 재실행 | "eval만", "X만 바꿔서" | 기존 폴더를 읽고, 바뀐 단계부터 다시. 기존 파일은 `*.v1.md`로 보존 |
| 이어하기 | 이전 실험이 승인 대기나 중단 상태 | `final-report.md`가 없는 최신 폴더를 찾아 마지막 완료 단계 다음부터 |
| 진도/추천 | "다음 뭐 해?" | roadmap과 최근 리포트를 읽고 다음 실험 1~2개 제안 |

4. 사용자 요청 원문, 제약, 모드를 `00-input.md`에 저장한다.

## Phase 1. 팀 구성

- **실행 모드 선택**
  - Agent Team 도구(`TeamCreate` 등)를 쓸 수 있으면 Agent Team으로 진행한다.
  - 쓸 수 없으면 Subagent(Agent 도구에 `subagent_type`으로 아래 agent 이름 지정)로 대체한다. 이때 중간 결과는 반드시 파일로 넘긴다.
  - 서빙만 하는 작은 실험은 infra-engineer, ml-engineer, reviewer 3명이면 충분하다. 에이전트 실험일 때만 agent-developer를 추가한다.
- **Task 등록** (`TaskCreate`)

| Task | 담당 | 입력 | 출력 | 의존 |
|---|---|---|---|---|
| T01-plan | ml-engineer | 00-input, roadmap | 01-plan.md | - |
| T02-infra-quote | infra-engineer | 01-plan, cost-ledger | 02-infra-plan.md | T01 |
| T03-review-cost | reviewer | 02 | 05-review.md (비용 섹션) | T02 |
| 🔴 GATE-A | 사람 | 02 | 승인/거절 | T03 |
| T04-provision | infra-engineer | 승인 | 03-run-log#Infra | GATE-A |
| T05-run | ml-engineer / agent-developer | 엔드포인트 | 03-run-log#Model/#Agent | T04 |
| T06-eval | ml-engineer (+agent-developer) | 03 | 04-eval.md | T05 |
| T07-review | reviewer | 01~04 | 05-review.md | T06 |
| 🔴 GATE-B | 사람 | 정리 계획 | 정리/유지 승인 | T07 |
| T08-teardown | infra-engineer | 승인 | run-log 갱신, cost-ledger | GATE-B |
| T09-learn | orchestrator (`learning-note`) | 01~05 | 06-learning-note.md, concepts/ | T07 |
| T10-report | orchestrator | 전체 | final-report.md, roadmap 갱신 | T08, T09 |

## Phase 2. 계획과 견적
- T01, T02, T03을 진행한다. 팀원 간 VRAM 요구량과 GPU 후보는 `SendMessage`로 조율한다.
- `TaskGet`으로 T03 완료를 확인한다.

## Phase 3. 🔴 GATE-A: 비용 승인
사용자에게 아래만 간결하게 보여주고 **멈춘다**.
```
GPU: {type} x{n} @ {dc}  |  ${x}/h ≈ ₩{y}/h
예상 시간: {h}h  →  예상 ₩{total}  (월 누적 {a}% → {b}%)
정리 계획: {언제 무엇을 지우는지}
진행할까요?
```
승인받지 못하면 상태를 `02-infra-plan.md`에 "승인 대기"로 남기고 종료한다. 다음 세션에서 "이어하기"로 재개할 수 있다.

## Phase 4. 실행
- T04 → T05. 실패하면 담당자가 원인을 run-log에 기록하고 1회 재시도한다. 재시도도 실패하면 `runpod:runpod-pod-doctor` 또는 `runpod:runpod-endpoint-ops`로 진단한다. 그래도 안 되면 사용자에게 보고한다.
- 과금 중인 리소스가 유휴 상태로 오래 남지 않게 한다. 실행이 막히면 먼저 Stop 여부를 사용자에게 묻는다.

## Phase 5. 평가와 리뷰
- T06 → T07. 리뷰 결과가 FIX_REQUIRED이면 해당 Task로 되돌린다. 최대 2회까지 반복하고, 그래도 안 되면 사람에게 확인한다.

## Phase 6. 🔴 GATE-B: 정리
리소스별로 `삭제 / Stop(디스크 비용 유지) / 유지(사유)` 중 하나를 사용자에게 고르게 한다. 그다음 T08을 실행하고 cost-ledger를 갱신한다.

## Phase 7. 학습과 리포트
- T09: `learning-note` 스킬로 이번 실험의 노트를 쓰고, 새 개념은 `concepts/`에 누적한다.
- T10: `final-report.md`를 작성하고 `roadmap.md` 체크박스와 진도를 갱신한다. 이번 실행에서 하네스 문제가 드러났으면 `improvement-log.md`에 기록한다.
- `TeamDelete`로 팀을 정리한다.

## final-report.md 형식
```
# {실험 제목}
- 한 줄 결론:
- 핵심 수치: (표)
- 비용: 실제 ₩ / 견적 ₩
- 배운 개념: [[concept]] 링크
- 실패와 교훈:
- 다음 실험 제안 1~2개:
```

## 메시지 규칙
`수신 / 유형(발견|질문|충돌|차단|완료) / 관련 Task / 관련 파일 / 내용 / 필요한 조치`. 다음 단계가 반드시 알아야 하는 내용은 메시지가 아니라 파일에 남긴다.
