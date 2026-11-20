# ocr-model

문서 OCR용 오픈소스 VLM을 RunPod에서 직접 서빙·운영·파인튜닝·평가하며 AI를 학습하는 프로젝트. 앱(ocr-agent, Private)은 이 모델을 OpenAI 호환 API로 쓴다.

- 하네스 규칙: [CLAUDE.md](CLAUDE.md)
- 학습 진도: [artifacts/learning/roadmap.md](artifacts/learning/roadmap.md)
- 비용 장부: [artifacts/cost-ledger.md](artifacts/cost-ledger.md)

## 시작
```bash
cp .env.example .env   # 키 입력
uv sync
```
Claude Code에서 자연어로 요청: "M1 시작하자. 8B 모델 vLLM으로 띄워보고 싶어"
