---
name: model-serving
description: 오픈소스 LLM 서빙 설정 매뉴얼. VRAM 계산, vLLM 핵심 인자 선택, 양자화 선택, OpenAI 호환 API 확인이 필요할 때 사용한다. RunPod 리소스 생성 절차는 runpod-ops를 사용한다.
---

# model-serving

## VRAM 계산 (백엔드 비유: 가중치 = 바이너리 크기, KV cache = 요청별 세션 메모리)
- **가중치** ≈ 파라미터 수 × 바이트 (bf16=2, fp8/int8=1, int4≈0.5). 예: 8B bf16 ≈ 16GB
- **KV cache (토큰 1개당)** = 2(K,V) × 레이어 수 × KV 헤드 수 × 헤드 차원 × 바이트
  → × 최대 컨텍스트 × 동시 시퀀스 수. 레이어·헤드 값은 모델의 `config.json`에서 읽는다.
- **여유분**: CUDA 컨텍스트, 활성화 메모리 등으로 1~2GB
- vLLM은 `gpu-memory-utilization` 비율만큼 메모리를 미리 잡고, 가중치를 뺀 나머지를 KV cache 블록으로 쓴다(PagedAttention). 기동 로그의 `# GPU blocks`와 `Maximum concurrency` 값을 run-log에 기록한다.

## vLLM 핵심 인자
| 인자 | 의미 | 처음 시작할 값 |
|---|---|---|
| `--max-model-len` | 최대 컨텍스트 길이. 크게 잡을수록 KV를 많이 쓴다 | 8192 |
| `--gpu-memory-utilization` | 미리 잡을 VRAM 비율 | 0.90 |
| `--max-num-seqs` | 동시에 처리할 시퀀스 수 | 기본값 |
| `--quantization` / `--dtype` | 정밀도 | 모델 기본값 |
| `--tensor-parallel-size` | GPU 여러 장에 나누기 | 1 |
| `--enable-auto-tool-choice --tool-call-parser {parser}` | tool calling | 에이전트 실험일 때만 |
| `--enable-lora --lora-modules` | LoRA 어댑터 서빙 | M4에서 |

## 검증
1. `GET /v1/models` 응답 확인
2. `POST /v1/chat/completions`로 짧은 요청 1건을 보내 응답 텍스트를 run-log에 기록
3. 이미지 태그, 모델 리비전, 전체 인자를 run-log에 기록

## 흔한 실패
- OOM이 나면 `max-model-len`이나 `gpu-memory-utilization`을 줄이거나 양자화 모델을 쓴다.
- gated 모델이면 `HF_TOKEN`이 필요하다(RunPod 시크릿으로 등록하며, 사람 승인 필요).
- CUDA 버전이 맞지 않으면 플러그인 `runpod:runpod-vllm`의 CUDA 고정 가이드를 따른다.

## 파일 위치
- 레시피(재사용): `serving/recipes/{engine}/` (`start.sh`, 필요하면 `Dockerfile`)
- 실험 설정: `serving/configs/{model}-{quant}-{gpu}.yaml` (모델 repo, revision, vLLM 인자, 이미지 태그). 인자를 바꾸면 기존 파일을 고치지 않고 새 config를 만든다.
- 기동 로그와 검증 응답: `artifacts/experiments/{id}/results/`
