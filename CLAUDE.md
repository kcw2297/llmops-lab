# ocr-model — 문서 OCR용 오픈소스 VLM 서빙·운영·튜닝 (RunPod)

## 프로젝트 목적
- RunPod에서 오픈소스 VLM을 직접 **서빙 → 추출 평가 → 파인튜닝 → 앱 연결 검증 → 운영**까지 해본다.
- 모델의 용도는 **AI OCR(문서 이미지 → 필드 JSON 추출)**이다. 베이스 모델은 `Qwen/Qwen3-VL-8B-Instruct`다(근거와 비교 대상은 roadmap). 채팅형 에이전트, tool calling, RAG는 범위 밖이다.
- 사용자는 백엔드/DevOps 출신이다. **AI 개념 학습이 1차 목표**다. 설명할 때는 백엔드/인프라 비유를 먼저 들고, 그다음 AI 고유 개념으로 넘어간다.

## 하네스 라우팅 (자연어 → Orchestrator)
아래 같은 요청은 스킬명을 입력하지 않아도 **`ocr-model-orchestrator` 스킬을 먼저 사용**한다.
- "VLM 후보 비교해줘", "이 모델 vLLM으로 띄워줘", "서빙 실험 해보자", "부하 테스트 해줘"
- "납부서 추출 LoRA 해보고 싶어", "양자화 비교해줘", "추출 정확도 평가 돌려줘", "합성 데이터셋 만들어줘"
- "서빙한 모델을 ocr-agent에 붙여서 검증해줘"
- 후속 요청: "지난 실험 다시", "eval만 다시", "max-model-len만 바꿔서 재실행", "이전 결과 기반으로 보완"
- "다음에 뭐 하면 돼?", "로드맵 진도 보여줘"

개념 질문만 하는 경우("KV cache가 뭐야?")에는 `learning-note` 스킬만 사용한다.
하네스와 무관한 일반 코딩 질문에는 하네스를 사용하지 않는다.

## 🔴 비용·안전 규칙 (모든 Agent·Skill 공통)
- **월 예산 상한: ₩200,000** (환산 기준 1 USD ≈ ₩1,450. 환율이 바뀌면 여기만 수정한다)
- 과금 리소스(Pod, Endpoint, Volume, Cluster)를 만들기 전에 **시간당 가격과 예상 총액(₩)을 보여주고 사용자 승인**을 받는다.
- 실험 1건 예상 비용이 **₩30,000을 넘으면** 강조해서 경고한다.
- 이번 달 누적 비용([artifacts/cost-ledger.md](artifacts/cost-ledger.md))이 **80%(₩160,000) 이상**이면 모든 계획에 경고를 붙인다. **100% 이상**이면 사용자가 명시적으로 예외를 허락하기 전까지 신규 생성을 금지한다.
- 삭제, 종료, HF Hub push, 엔드포인트 공개, 시크릿 등록도 사람 승인을 받는다. 삭제·변경은 이 대화에서 만들었거나 사용자가 ID로 지정한 리소스에만 한다.
- 실험이 끝나면 반드시 정리(teardown) 여부를 확인한다. Stop한 Pod도 디스크 비용이 계속 나간다.
- API 키나 HF 토큰은 `.env`에만 두고 커밋하지 않는다. 산출물에 키를 적지 않는다.

## 레포 구조 원칙 (새 파일·폴더는 반드시 이 규칙을 따른다)
- **P1 자산 4종 분리**: 코드 · 설정(`configs/`) · 데이터(`datasets/`, `.data/`) · 기록(`artifacts/`)을 섞지 않는다.
- **P2 두 실행 세계**: Local(uv workspace: `packages/ocr-core`, `eval`)과 Remote(RunPod 컨테이너: `serving`, `finetune`). 두 세계는 OpenAI 호환 HTTP API, HF 형식 LoRA 어댑터, YAML config로만 연결한다.
- **P3 단방향 의존**: `eval`은 `ocr_core`만 import한다. 앱 레포(`ocr-agent`)는 이 레포의 코드를 import하지 않고 OpenAI 호환 API(`LLM_BASE_URL`)로만 서빙 모델을 쓴다.
- **P4 실험 = 설정**: 새 실험은 `{module}/configs/*.yaml`을 추가해서 만든다. 레시피 코드는 복사하지 않는다.
- **P5 실험 ID**: `{YYYYMMDD}-m{n}-{slug}` 형식(예: `20261120-m1-vlm-bakeoff`). 측정 원본과 로그는 `artifacts/experiments/{id}/results/`에만 쓴다. 코드 폴더에는 결과를 쓰지 않는다.
- **P6 git에는 재현에 필요한 것만**: 가중치, 체크포인트, 원본 데이터는 `.data/`, RunPod 볼륨, HF Hub에 둔다.
- **앱은 별도 Private 레포 1개(`~/Desktop/ocr-agent`)만 둔다.** 이 레포(Public)에는 앱 코드를 두지 않는다. 앱은 서빙한 모델을 실제 업무 워크로드(2단계 부가세 서류 필드 추출)로 검증하는 소비자다.
- **실데이터 금지 (Public 레포)**: 이 레포는 Public이다. 실제 회사명·계좌번호·사업자번호·비밀번호·기획서 원본·거래내역을 커밋하지 않는다. 평가 데이터셋에 업무 데이터가 필요하면 합성하거나 가명 처리한다.

## 주요 위치
| 목적 | 위치 |
|---|---|
| Orchestrator (전체 진행표) | `.claude/skills/ocr-model-orchestrator/SKILL.md` |
| 팀원 카드 | `.claude/agents/` (infra-engineer, ml-engineer, ocr-engineer, reviewer) |
| 작업 매뉴얼 | `.claude/skills/` |
| 산출물 지도 | `artifacts/README.md` |
| 학습 로드맵 | `artifacts/learning/roadmap.md` |
| 공유 커널 | `packages/ocr-core/src/ocr_core/` |
| 측정·추출 평가 | `eval/src/ocr_eval/`, `eval/configs/`, `eval/datasets/{name}-v{n}/` |
| 앱 (별도 Private 레포) | `~/Desktop/ocr-agent/` (기획: `docs/`) |
| 서빙 | `serving/recipes/{engine}/`, `serving/configs/{model}-{quant}-{gpu}.yaml` |
| 파인튜닝 | `finetune/recipes/{method}/`, `finetune/configs/{model}-{method}-{dataset}.yaml`, `finetune/datasets/{name}-v{n}/`(데이터 카드와 샘플) |

## 개발 환경
- 로컬: Python 3.13, uv workspace (`uv sync`, `uv run`, 의존성은 해당 멤버에서 `uv add --package ocr-eval <pkg>`처럼 추가)
- 원격(RunPod 컨테이너) Python 버전은 이미지가 정한다. vLLM, 학습 라이브러리는 로컬에 설치하지 않고 컨테이너 안에서 실행한다.
- git: remote `origin` = `kcw2297/ocr-model` (Public). push는 사용자가 요청할 때만 한다.

## 변경 이력
- 2026-11-18: 하네스 최초 구성 (Agent 4, Skill 8, artifacts 구조, 월 예산 ₩200,000)
- 2026-11-18: 루트 `agents/` → `apps/` 이름 변경 (`.claude/agents/`와 혼동 방지)
- 2026-11-18: 레포 구조 원칙 P1~P6 도입. uv workspace(core/eval/app), 앱은 `app/` 1개로 고정, 실험 ID 형식 변경, 측정 원본은 artifacts로 이동
- 2026-11-19: 레포 분리. `app/`을 제거하고 앱은 Private `biz-automation`으로 이동. Public 레포 실데이터 금지 규칙 추가
- 2026-11-20: 앱 레포 이름 `biz-automation` → `ocr-docflow`. 로드맵 주제를 VLM 문서 추출로 변경
- 2026-11-20: 레포 이름 `llmops-lab` → `ocr-model` (GitHub, 오케스트레이터 `ocr-model-orchestrator`). 앱 레포 `ocr-docflow` → `ocr-agent`. 로컬 폴더 `~/Desktop/AiAgent`와 패키지명 `llmops_core`·`llmops_eval`은 유지
- 2026-11-20: 로컬 폴더 `~/Desktop/AiAgent` → `~/Desktop/ocr-model` (zshrc 훅, Claude 프로젝트 메모리 경로 이동)
- 2026-11-20: 채팅형 에이전트 범위 제거. `agent-developer` → `ocr-engineer`, 스킬 `agent-build` → `ocr-extraction`, 서빙·튜닝·평가 매뉴얼을 VLM 문서 추출 기준으로 변경. 베이스 모델은 M1 비교 후 결정
- 2026-11-20: 옛 이름 정리. 패키지 `llmops-core`·`llmops-eval` → `ocr-core`·`ocr-eval` (import `ocr_core`·`ocr_eval`)
- 2026-11-20: 베이스 모델 `Qwen/Qwen3-VL-8B-Instruct`로 결정. Qwen3.5-9B는 비교 대상, M7에서 재검토
