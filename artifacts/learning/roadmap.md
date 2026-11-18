# 학습 로드맵

현재 마일스톤: **M1**

| M | 마일스톤 | 핵심 개념 | 상태 | 실험 |
|---|---|---|---|---|
| M1 | 7~8B 모델을 vLLM으로 Pod에 서빙 | VRAM 산정, KV cache, 토크나이저, OpenAI 호환 API | ⬜ | |
| M2 | Serverless 전환과 부하 테스트 | cold start, continuous batching, PagedAttention, TTFT/TPOT | ⬜ | |
| M3 | 양자화 비교 (AWQ/GPTQ/FP8) | 정밀도, 품질·속도·메모리 트레이드오프 | ⬜ | |
| M4 | LoRA/QLoRA 파인튜닝과 어댑터 서빙 | 학습 루프, loss, 과적합, 어댑터 | ⬜ | |
| M5 | 평가 체계 | 벤치마크, LLM-as-judge, 회귀 테스트 | ⬜ | |
| M6 | `app/` 1개로 서빙 모델 검증 (tool calling 품질, 긴 컨텍스트 부하, 파인튜닝 전후 비교) | function calling 파서, 컨텍스트 길이와 지연, 구조화 출력 | ⬜ | |
| M7 | 운영 | 메트릭·관측성, 오토스케일링, 비용 최적화 | ⬜ | |

## 개념 체크리스트
(learning-note가 개념 노트를 만들 때마다 추가)
