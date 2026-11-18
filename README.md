# llmops-lab

RunPod에서 오픈소스 LLM을 직접 서빙·운영·파인튜닝하고, 그 위에 에이전트를 개발하며 AI를 학습하는 프로젝트.

- 하네스 규칙: [CLAUDE.md](CLAUDE.md)
- 학습 진도: [artifacts/learning/roadmap.md](artifacts/learning/roadmap.md)
- 비용 장부: [artifacts/cost-ledger.md](artifacts/cost-ledger.md)

## 시작
```bash
cp .env.example .env   # 키 입력
uv sync
```
Claude Code에서 자연어로 요청: "M1 시작하자. 8B 모델 vLLM으로 띄워보고 싶어"
