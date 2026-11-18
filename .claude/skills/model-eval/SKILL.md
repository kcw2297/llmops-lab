---
name: model-eval
description: 서빙 성능(지연, 처리량)과 모델 품질을 측정하는 매뉴얼. 부하 테스트, 양자화나 파인튜닝 전후 비교, LLM-as-judge 평가, 04-eval.md 작성 시 사용한다.
---

# model-eval

## 성능 지표 (백엔드 지표와 대응)
| LLM 지표 | 의미 | 백엔드 대응 |
|---|---|---|
| TTFT | 첫 토큰까지 걸린 시간 | TTFB |
| TPOT / ITL | 토큰 사이 간격 | 스트리밍 chunk 간격 |
| output tokens/s (전체) | 시스템 처리량 | RPS × 응답 크기 |
| p50 / p95 / p99 | 분위수 | 동일 |

## 성능 측정 절차
1. 도구: `vllm bench serve`(컨테이너 안) 또는 `eval/src/llmops_eval/` 의 asyncio 스크립트(`uv run python -m llmops_eval.bench --config eval/configs/{suite}.yaml`)
2. 고정 조건: 입력/출력 토큰 길이, 프롬프트 세트, 워밍업 요청 수
3. 동시성을 1, 4, 16, 64로 올리면서 측정한다. 처리량이 포화되는 지점과 p95가 급격히 늘어나는 지점을 찾는다.
4. 원본 결과(JSON/CSV)는 `artifacts/experiments/{id}/results/`에 저장한다. 코드 폴더에는 결과를 쓰지 않는다. 04-eval.md의 숫자는 반드시 이 파일에서 가져온다.

## 품질 측정 절차
- 처음에는 실험 목적에 맞는 고정 프롬프트 20~50개 세트(`eval/datasets/{name}-v{n}/`)를 쓴다. 세트를 수정하면 버전을 올린다(v1 → v2). 기존 버전을 덮어쓰면 과거 실험과 비교할 수 없다.
- 비교는 A/B로 한다(베이스 vs 파인튜닝, bf16 vs awq). 채점은 규칙 기반(정답 매칭, JSON 파싱 성공률)을 먼저 쓰고, 그다음 LLM-as-judge를 쓴다.
- 표준 벤치마크(lm-eval-harness 등)는 M5에서 도입한다.

## 출력 형식 (`04-eval.md`)
```
## 조건
## 성능 표 (동시성별 TTFT p50/p95, tokens/s)
## 품질 표
## 해석 (가설 대비 결과, 왜 그런지)
## 원본 파일 경로
```

## 품질 체크
- 모든 수치에 원본 파일 근거가 있는가?
- 워밍업 요청을 측정에서 제외했는가?
- 비교 실험은 바꾼 변수 외의 조건이 같은가?
