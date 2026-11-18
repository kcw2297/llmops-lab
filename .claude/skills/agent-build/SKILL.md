---
name: agent-build
description: 직접 서빙한 OpenAI 호환 LLM 위에 에이전트를 구현하는 매뉴얼. tool calling, 에이전트 루프, RAG, 메모리, 시나리오 테스트를 설계하고 구현할 때 사용한다. 모델 서빙 설정에는 사용하지 않는다.
---

# agent-build

## 개념 (백엔드 비유)
- **에이전트** = LLM이 매 턴 "다음에 어떤 API를 호출할지" 정하는 while 루프
- **tool** = JSON Schema로 정의한 함수. LLM은 호출 의도(JSON)만 내고, 실행은 우리 코드가 한다.
- **컨텍스트** = 요청마다 다시 보내는 상태. 서버는 stateless다. 길어지면 비용과 지연이 늘어난다.

## 절차
1. **먼저 확인**: 모델이 tool calling을 지원하는지, vLLM에 `--tool-call-parser`가 설정되어 있는지 확인한다(ml-engineer에게 문의).
2. **프레임워크 없이 시작**: `openai` SDK와 직접 작성한 루프로 원리를 먼저 이해한다. 그다음 필요하면 프레임워크를 비교한다.
3. **루프 구현**: messages → completion → tool_calls가 있으면 실행하고 결과를 append → 반복. **최대 스텝 수, 타임아웃, JSON 파싱 실패 시 재시도 1회**를 넣는다.
4. **도구 설계**: 이름과 설명은 짧고 명확하게 쓴다. 인자는 최소한으로 둔다. 파괴적 도구에는 확인 단계를 넣는다.
5. **관측**: 매 스텝의 입력 토큰 수, 호출한 도구, 지연 시간을 JSONL 로그로 남긴다.
6. **시나리오 테스트**: `app/tests/scenarios.yaml`에 정상, 모호, 실패 유도 케이스를 각각 3개 이상 둔다. 성공률과 평균 스텝을 측정한다.

## 코드 규칙
- Python 3.13, `uv add --package llmops-app openai python-dotenv` (클라이언트를 eval과 공유하면 `llmops-core`에 추가)
- 설정: `.env`의 `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`
- 위치: `app/src/llmops_app/` (`main.py`, `loop.py`, `state.py`, `prompts/`, `tools/`), 앱은 1개만 두고 확장한다
- 의존 규칙: `llmops_core`만 import한다. `llmops_eval` import는 금지한다

## 흔한 실패 패턴 (발견하면 learning-note에 기록)
- tool call JSON이 깨짐(작은 모델에서 흔함), 같은 도구를 무한 반복 호출, 도구 결과를 무시하고 지어낸 답변, 컨텍스트 초과
