# 학습 로드맵

현재 마일스톤: **M1**

주제: **문서 AI(VLM으로 문서 필드 추출)**. 앱(ocr-agent 2단계)의 부가세 서류 추출을 실제 워크로드로 쓴다. **베이스 모델: `Qwen/Qwen3-VL-8B-Instruct`** (2026-11-20 결정, Apache 2.0). 이유: 표준 트랜스포머 구조라 기본 개념 학습에 맞고, 이미지 → JSON LoRA 사례가 많고, vLLM multi-LoRA 서빙이 안정적이다. 비교 대상: Qwen3.5-9B(최신 세대, vLLM LoRA 안정성 확인 필요 → M7에서 재검토), Gemma 4(E4B·12B), 전용 OCR 모델(PaddleOCR-VL, GLM-OCR 등, 기준선). 외부 VLM API는 정확도 기준선으로 쓴다. 업무 실문서는 이 레포에 올리지 않고 합성·가명 데이터만 쓴다.

| M | 마일스톤 | 핵심 개념 | 상태 | 실험 |
|---|---|---|---|---|
| M1 | Qwen3-VL-8B-Instruct를 vLLM으로 Pod에 서빙하고, 같은 합성 문서로 비교 대상(Qwen3.5-9B 등)과 대조 | VRAM 산정, KV cache, 이미지 토큰, OpenAI 호환 API(이미지 메시지), 구조화 출력 | ⬜ | |
| M2 | Serverless 전환과 부하 테스트 (문서 이미지 배치) | cold start, continuous batching, PagedAttention, TTFT/TPOT, 이미지 해상도와 지연 | ⬜ | |
| M3 | 양자화 비교 (AWQ/GPTQ/FP8) | 정밀도, 품질·속도·메모리 트레이드오프 | ⬜ | |
| M4 | 문서 양식별 LoRA 파인튜닝(이미지 → JSON)과 어댑터 서빙 | 학습 루프, loss, 과적합, 데이터 수와 정확도, 어댑터 | ⬜ | |
| M5 | 추출 평가 체계 | 필드 정답률, 문서 완전 일치, 회귀 테스트, 합성 데이터 | ⬜ | |
| M6 | 앱 레포(`ocr-agent` 2단계 부가세 서류 추출)로 서빙 모델 검증 (외부 API 대비 정확도, 파인튜닝 전후 비교) | 구조화 출력, 사람 확인(HITL), 정확도·비용 트레이드오프 | ⬜ | |
| M7 | 운영 (양식별 multi-LoRA 서빙, 베이스 세대 교체 재검토) | 메트릭·관측성, 오토스케일링, 비용 최적화 | ⬜ | |

## 개념 체크리스트
(learning-note가 개념 노트를 만들 때마다 추가)
- [ ] [모델 패밀리와 이름 읽는 법](concepts/model-family-naming.md) — M1에서 실측 수치 채우면 체크
