# 03-run-log — 20261120-m1-qwen3vl-8b-vllm

섹션별 작성자: `## Infra`(infra-engineer), `## Model`(ml-engineer), `## Extraction`(ocr-engineer).
URL·API 키·Pod 프록시 주소는 적지 않는다(`env:LLM_BASE_URL`로만 표기).

## Infra

### 2026-11-21 — T04-provision 생성 전 점검: **차단 (잔액 부족, Pod 생성 안 함)**
- 작성: infra-engineer. 점검 시각 2026-11-21T04:52Z (2026-11-21 13:52 KST)
- 결과: **create-pod 호출하지 않음.** 과금 리소스 0개. 비용 ₩0
- 이 계정의 Pod 목록(`list-pods`): 비어 있음 (기존 리소스 없음)

| 점검 | 조회 | 결과 | 판정 |
|---|---|---|---|
| 계정 잔액 | `get-balance` | `balanceAmount: 0`, `billingMode: PREPAID` | **실패**. 승인 조건 최소 약 $0.60(1시간치, `pod-billing.deploy-needs-an-hour`), 권장 $6 이상에 미달 |
| A40 재고 (CUDA별) | `get-capacity` (`NVIDIA A40`, Secure, cudaVersions 13.0·13.2) | 13.0 `Out`, 13.2 **`High`** $0.59/h | 통과 (호스트 13.2 ≥ `minCudaVersion 13.0`) |
| A40 재고 (DC별) | `list-gpu-types` (`AVAILABILITY`, POD, SECURE, `minCudaVersion 13.0`) | **EU-SE-1 `HIGH`**, CA-MTL-1 `LOW`. Secure $0.59/h (≈₩856/h) | 통과 (02-infra-plan 때 LOW → HIGH) |

- 다음 조치(사용자): RunPod 콘솔 Billing에서 크레딧 충전(권장 $6 이상 — 상한 4.5h × $0.601 ≈ $2.70에 여유). 충전 후 T04를 같은 사양으로 다시 실행한다. 재고는 그때 다시 조회한다.
- 로컬 준비 상태: `.env`에 `VLLM_API_KEY`(값 있음, `LLM_API_KEY`와 동일) 확인. `LLM_BASE_URL`은 아직 자리표시자(Pod 생성 후 채움). 파일 권한 600, git ignore 확인

## Extraction

### 2026-11-21 — 0단계 로컬 준비 (GPU 없음, 비용 ₩0)
- 작성: ocr-engineer. RunPod 리소스 생성·호출 없음. 서버 호출 0건(dry-run만).
- 레포 HEAD: `2302be9` (작업 트리 미커밋 상태에서 생성)

**데이터셋 `vat-slip-v1`** (`eval/datasets/vat-slip-v1/`)
- 생성: `uv run python -m ocr_eval.synth.vat_slip --out eval/datasets/vat-slip-v1` (seed 20261120, Pillow 13.0.0, AppleSDGothicNeo.ttc)
- 8장, A4 150dpi 1240×1754 PNG(109~120KB), 필드 10개, 합계 금액 6·7·8·9·10·6·8·10자리, 날짜 표기 6종, 가상계좌 null 2건(행 없음 1, 빈칸 1)
- 재실행 결정성 확인: 2회 생성 시 PNG sha 8/8 일치. `manifest.json`에 sha256 기록
- 한글 렌더링 육안 확인: 001, 007 (tofu 없음)
- 모든 값 가짜(사업자번호 `000` 시작 + 체크섬 불일치, 전자납부번호 `0000` 시작, 가상 상호·은행·세무서)

**평가 실행기**
- 코드: `eval/src/ocr_eval/m1_smoke.py`, `eval/src/ocr_eval/scoring.py`, 공용 `packages/ocr-core/src/ocr_core/{settings,llm}.py`
- 설정: `eval/configs/m1-smoke-vat-slip.yaml` (temperature 0, max_tokens 1024, timeout 180s, 워밍업 1, 동시성 1, `response_format=json_schema` strict)
- 단위 테스트: `uv run pytest eval/tests -q` → 40 passed
- dry-run (요청 본문만 생성):
  ```
  uv run python -m ocr_eval.m1_smoke --config eval/configs/m1-smoke-vat-slip.yaml --model qwen3vl-8b --dry-run
  uv run python -m ocr_eval.m1_smoke --config eval/configs/m1-smoke-vat-slip.yaml --model qwen3.5-9b --dry-run
  ```
  - 8/8 본문 생성, 요청 1건 평균 155.7KB / 최대 163.0KB (base64 이미지 포함)
  - 예상 이미지 토큰 2,145/장 (39×55, 계산). 실측 `prompt_tokens`와 비교 예정(H2)
  - qwen3.5-9b 본문에만 `chat_template_kwargs: {enable_thinking: false}` 포함 확인
  - 미리보기: `results/{qwen3vl-8b,qwen3.5-9b}/dry-run/requests-preview.jsonl` (이미지 base64는 잘라서 저장)

**Pod 기동 후 실행 순서** (엔드포인트는 `.env`의 `LLM_BASE_URL`, `LLM_API_KEY`)
1. `--model qwen3vl-8b --limit 1` → `results/qwen3vl-8b/limit-1/` (워밍업 없음, 1장)
2. `--model qwen3vl-8b` → `results/qwen3vl-8b/` (워밍업 1 + 8장)
3. 모델 교체 후 `--model qwen3.5-9b --limit 1`, 이어서 본 측정 → `results/qwen3.5-9b/`
- 기존 결과가 있으면 멈춘다. 재측정은 `--overwrite`
- 산출물: `models.json`(/v1/models), `predictions.jsonl`(요청별 지연·usage·원 응답·JSON/스키마 유효·예측), `fields.csv`(필드별 정답·오류 유형), `warmup.jsonl`, `summary.json`

## Model

### 2026-11-21 — 0단계 서빙 설정 (GPU 없음, 비용 ₩0)
- 작성: ml-engineer. RunPod 리소스 생성·변경 없음. 레포 HEAD `2302be9` (아래 파일은 미커밋 상태. 커밋 후 sha를 여기에 추가한다)
- 만든 파일
  - `serving/configs/qwen3vl-8b-instruct-bf16-a40.yaml`
  - `serving/configs/qwen3.5-9b-bf16-a40.yaml`
  - `serving/recipes/vllm/README.md` (config → RunPod 필드 매핑, 모델 교체, 기동 판정, 기록할 로그 값)
  - 01-plan의 `serving/recipes/vllm/start.sh`는 만들지 않았다. Pod에 파일을 둘 수 없고, 공식 이미지 ENTRYPOINT(`vllm serve`)에 인자만 넘기면 되기 때문이다.
- 로컬 검증: 두 yaml 모두 `' '.join(cmd) == rendered_args`, 인자에 따옴표·중괄호·공백·`$` 없음, `str.split()` = `shlex.split()`, vLLM v0.32.0 dot 표기 병합 로직을 옮긴 시뮬레이션 결과가 `expected_parsed`와 일치

#### infra-engineer가 그대로 쓸 값
| create-pod 필드 | 값 |
|---|---|
| `image` | `vllm/vllm-openai:v0.32.0` |
| `args` (Qwen3-VL, 생성 시) | 아래 문자열 1 |
| `args` (Qwen3.5, `update-pod` 교체 시 이 필드만) | 아래 문자열 2 |
| `env` | `HF_HOME=/workspace/hf`, `VLLM_CACHE_ROOT=/workspace/vllm-cache`, `VLLM_NO_USAGE_STATS=1`, `VLLM_API_KEY=<.env 값>` |
| `ports` | `["8000/http"]` |
| `disk` / `mounts.persistent` | `30` / `{"size": 50, "path": "/workspace"}` |
| `gpu` | `{"id": "NVIDIA A40", "count": 1, "minCudaVersion": "13.0"}` |
| `entrypoint` | 넣지 않음 (이미지 기본 `vllm serve`) |

문자열 1 — Qwen3-VL-8B-Instruct
```
Qwen/Qwen3-VL-8B-Instruct --revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b --served-model-name qwen3vl-8b --host 0.0.0.0 --port 8000 --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt.image 1 --limit-mm-per-prompt.video 0 --mm-processor-kwargs.max_pixels 2621440
```
문자열 2 — Qwen3.5-9B
```
Qwen/Qwen3.5-9B --revision c202236235762e1c871ad0ccb60c8ee5ba337b9a --served-model-name qwen3.5-9b --host 0.0.0.0 --port 8000 --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt.image 1 --limit-mm-per-prompt.video 0 --mm-processor-kwargs.max_pixels 2621440 --reasoning-parser qwen3 --default-chat-template-kwargs.enable_thinking false
```
- 왜 `'{...}'` JSON 대신 dot 표기인가: RunPod `args`는 "split into arguments"라고만 되어 있고 따옴표 처리 규칙이 문서에 없다. 공백 기준으로 나누면 `'{"image": 1, "video": 0}'`이 5조각으로 깨진다. vLLM은 `--arg.key value`를 JSON 인자와 똑같이 받으므로(값은 `json.loads`) 따옴표 자체를 없앴다.
- 01-plan 계획값과 다른 점: 없음(값은 같고 표기만 dot). 추가한 것은 `--host 0.0.0.0 --port 8000`(명시), env `VLLM_CACHE_ROOT`·`VLLM_NO_USAGE_STATS`.

#### 01-plan "확인 필요" 해소 결과
| # | 항목 | 결과 | 출처 |
|---|---|---|---|
| a | 픽셀 상한 지정 방법 | **`--mm-processor-kwargs`의 `max_pixels` 키** (동의어 `size.longest_edge`. 하나만 주면 vLLM이 나머지를 채운다). 두 모델 같은 키. 값 2,621,440 → 이미지 최대 2,560토큰 | HF `preprocessor_config.json`@두 리비전(`size.longest_edge 16777216`, `Qwen2VLImageProcessorFast`), transformers v5.13 `Qwen2VLImageProcessorKwargs`(`min_pixels`, `max_pixels` 유효 kwarg), vLLM v0.32.0 `models/qwen2_vl.py` `_get_vision_size`·`get_image_size_with_most_features`, `models/qwen3_vl.py`, `models/qwen3_5.py`(`Qwen3_5ProcessingInfo(Qwen3VLProcessingInfo)`), `multimodal/processing/context.py`(flat 키 → `images_kwargs` 라우팅) |
| b | 상한 > max-model-len일 때 | **기동은 실패하지 않는다.** 기동 때 최대 크기 더미 이미지로 비전 인코더를 프로파일링한다(상한이 크면 메모리를 더 씀). 요청 시 이미지는 상한 안으로 축소되고, 이미지+텍스트가 max-model-len을 넘으면 **그 요청만 400**("The decoder prompt (length N) is longer than the maximum model length"). 자르지 않는다 | vLLM v0.32.0 `multimodal/encoder_budget.py`(`max_items_per_prompt = max(1, …)`), `v1/core/encoder_cache_manager.py`(`compute_mm_encoder_budget`), `v1/engine/input_processor.py`(`_validate_prompt_len`) |
| c-1 | Qwen3.5 linear attention 상태 dtype | **ssm(재귀) 상태 float32, conv 상태 bf16.** vLLM이 config의 `mamba_ssm_dtype: float32`를 읽어 적용한다. 01-plan의 시퀀스당 0.050GB가 맞다 | HF `config.json`@c202236(`text_config.mamba_ssm_dtype = float32`), vLLM `models/config.py` `Qwen3_5ForConditionalGenerationConfig`, `layers/mamba/mamba_utils.py` `gated_delta_net_state_dtype` |
| c-2 | Qwen3.5 MTP 로드 여부 | **로드하지 않는다.** 가중치 매퍼가 `mtp.` 접두사를 버린다. `--speculative-config`를 줄 때만 쓴다. 다운로드는 한다. → 가중치 VRAM 18.82GB = 17.53GiB (계산), 성공 기준 7의 비교값 | HF `config.json`(`mtp_num_hidden_layers 1`), vLLM `models/qwen3_5.py` `hf_to_vllm_mapper {"mtp.": None}` |
| d | Qwen3-VL OCR 한국어 | **지원 언어에 포함.** 기술 보고서 Figure 2(자체 OCR 테스트셋, 39개 언어)에 Korean 막대가 있고 값은 약 87%(그래프 판독, 표 없음). 단 평가 모델 크기가 명시되지 않아(플래그십 기준으로 보임) 8B 수치로 보면 안 된다. 우리 양식의 한국어 정답률은 이번 실측으로 확인 | Qwen3-VL Technical Report arXiv 2511.21631v2 p.17 Figure 2, 5.4절 "39 languages … over 70% on 32"; 모델 카드 README@0c351dd "Supports 32 languages" (목록 없음) |
| - | Qwen3.5 thinking 끄기 | 서버 `--default-chat-template-kwargs.enable_thinking false` + 요청 `extra_body.chat_template_kwargs.enable_thinking=false`(모델 카드 예시와 같음). chat template이 빈 `<think>\n\n</think>`를 넣고, 구조화 출력은 프롬프트 안의 `</think>`를 보고 첫 토큰부터 schema를 적용한다 | `tokenizer_config.json`@c202236 chat_template, Qwen3.5 README "Instruct (or Non-Thinking) Mode", vLLM recipes Qwen3.5, vLLM `v1/structured_output/__init__.py`, `reasoning/basic_parsers.py` `is_reasoning_end` |
| - | `--default-chat-template-kwargs` 존재 | v0.32.0에 있음, 요청 값이 우선 | vLLM `entrypoints/launchers/cli_args.py` |

미해소 (`확인 필요:`)
- 확인 필요: `vllm/vllm-openai:v0.32.0`의 실제 ENTRYPOINT가 `vllm serve`인지 이미지 config로 직접 보지 않았다(runpod-vllm 플러그인 `reference/pod.md` 기준). 기동 로그 첫 줄로 확인
- 확인 필요: 하이브리드 KV 할당기의 실제 `Maximum concurrency`(Qwen3.5 추정 66배)와 Qwen3-VL(추정 18.8배) — 기동 로그로 확인
- 확인 필요: 구조화 출력이 서버 인자 없이 두 모델에서 동작하는지 — 기동 후 1건으로 확인
- 확인 필요: Qwen3.5 thinking 끈 상태에서 응답 `message.reasoning`이 비고 `content`가 JSON으로 시작하는지 — 기동 후 1건으로 확인
- 확인 필요: 실제 VRAM 사용량 측정 방법(SSH 없음. `get-pod` 지표 또는 로그 합산)

#### 보안 발견 (infra-engineer, reviewer 확인 요청)
- vLLM v0.32.0은 `/invocations`(SageMaker 호환, 추론 가능)와 `/ping`을 조건 없이 등록하고, `VLLM_API_KEY`는 `/v1`, `/v2`, `/inference`만 보호한다. proxy URL을 아는 사람은 키 없이 `/invocations`로 추론할 수 있다. 끄는 인자는 찾지 못했다. 출처: `vllm/entrypoints/launchers/cli_args.py`(`api_key` 경고문), `launchers/api_server/routers.py`(무조건 `register_sagemaker_api_router`)
- 대응(제안): proxy URL을 산출물·대화에 적지 않기, 측정 끝나면 바로 Terminate. 위험 수용 여부는 사용자 판단

#### 기동 후 여기에 기록할 것 (모델별)
- 기동 로그 원문 경로 `results/{served-model-name}/boot.log` (키 grep 0건 확인 후 저장)
- `non-default args` 줄, `Model loading took X GiB`, `Available KV cache memory`, `# GPU blocks`/`GPU KV cache size`, `Maximum concurrency for 8,192 tokens per request`, 기동 소요 시간
- `GET /v1/models` 결과, 첫 이미지 요청의 `usage.prompt_tokens`
