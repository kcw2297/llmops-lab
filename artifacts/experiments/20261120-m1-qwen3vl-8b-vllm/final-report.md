# M1 Qwen3-VL-8B vLLM 서빙 — 중단

- 한 줄 결론: Pod를 만들기 전에 중단. 2026-11-21 사용자가 자체 서빙·학습 대신 외부 API(OpenRouter + Gemini 3.8 Flash)로 방향을 바꿨다.
- 비용: 실제 ₩0 / 견적 ₩2,144 (RunPod 잔액 $0으로 생성 전 막힘, 이후 방향 전환)
- 남은 리소스: 없음 (list-pods 비어 있음, 2026-11-21 04:52Z 확인)
- 재사용할 산출물: 합성 데이터셋 `eval/datasets/vat-slip-v1/`, 평가 실행기 `eval/src/ocr_eval/m1_smoke.py`(OpenAI 호환이면 어디든 호출 가능), 서빙 config(보관용)
- 실패와 교훈: 선불 계정은 생성 전에 잔액을 먼저 확인한다. vLLM v0.32.0은 API 키를 걸어도 /invocations를 연다.
