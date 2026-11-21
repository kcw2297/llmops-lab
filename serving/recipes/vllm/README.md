# vLLM 서빙 레시피 (RunPod Pod, 공식 `vllm/vllm-openai` 이미지)

이 레시피는 코드가 아니라 **매핑 규칙**이다. Pod 이미지에 sshd가 없어 Pod 안에 스크립트를 둘 수 없다. 그래서 설정은 Pod의 **컨테이너 시작 인자(`vllm serve` 뒤에 붙는 인자)와 환경변수**로만 전달한다. 실험마다 바뀌는 값은 `serving/configs/{model}-{quant}-{gpu}.yaml`에 있고, 이 문서는 그 yaml을 RunPod 필드로 옮기는 방법을 정한다.

백엔드 비유: config yaml = Helm values 파일, 이 README = 차트 템플릿, RunPod `create-pod` 요청 = 렌더링된 Deployment manifest.

## 1. config yaml → RunPod `create-pod` 필드 매핑

| config yaml 키 | RunPod 필드 (MCP `create-pod` body) | 예 (`qwen3vl-8b-instruct-bf16-a40.yaml`) | 비고 |
|---|---|---|---|
| `engine.image` | `image` | `vllm/vllm-openai:v0.32.0` | 태그 고정. `latest` 금지 |
| `engine.entrypoint` | (넣지 않음) | `vllm serve` | 이미지 기본 ENTRYPOINT를 쓴다. `entrypoint` 필드를 주면 덮어써진다 |
| `rendered_args` | `args` (문자열) | `Qwen/Qwen3-VL-8B-Instruct --revision ...` | 콘솔의 "Container start command"와 같은 필드. 아래 2절 참고 |
| `cmd` | `cmd` (문자열 배열) | `["Qwen/Qwen3-VL-8B-Instruct", "--revision", ...]` | `args` 대신 쓸 수 있다. **둘 중 하나만** 넣는다 |
| `env` | `env` | `{"HF_HOME": "/workspace/hf", ...}` | `VLLM_API_KEY` 값은 로컬 `.env`에서 읽어 넣는다. 산출물에는 이름만 |
| `pod.ports` | `ports` | `["8000/http"]` | `22/tcp`는 넣지 않는다(sshd 없음) |
| `pod.volume_mount_path`, `pod.volume_gb` | `mounts.persistent.path`, `mounts.persistent.size` | `/workspace`, `50` | Pod 볼륨 디스크. Network Volume 아님 |
| `pod.container_disk_gb` | `disk` | `30` | 컨테이너 디스크. update-pod·재시작 때 지워진다 |
| `gpu.type`, `gpu.count` | `gpu.id`, `gpu.count` | `NVIDIA A40`, `1` | `--tensor-parallel-size`를 쓰면 `gpu.count`와 같아야 한다 |
| `engine.min_cuda_version` | `gpu.minCudaVersion` | `"13.0"` | 빠지면 오래된 드라이버 호스트에 배치되어 `OCI runtime create failed`로 안 뜰 수 있다 |
| (02-infra-plan) | `cloud`, `dataCenterIds`, `name` | `SECURE`, `["EU-SE-1"]`, `m1-qwen3vl-8b-vllm` | infra-engineer가 정한다 |

완성 예 (M1, Qwen3-VL-8B. 키 값은 자리표시자):
```json
{
  "name": "m1-qwen3vl-8b-vllm",
  "image": "vllm/vllm-openai:v0.32.0",
  "args": "Qwen/Qwen3-VL-8B-Instruct --revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b --served-model-name qwen3vl-8b --host 0.0.0.0 --port 8000 --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt.image 1 --limit-mm-per-prompt.video 0 --mm-processor-kwargs.max_pixels 2621440",
  "env": {
    "HF_HOME": "/workspace/hf",
    "VLLM_CACHE_ROOT": "/workspace/vllm-cache",
    "VLLM_NO_USAGE_STATS": "1",
    "VLLM_API_KEY": "<.env의 값>"
  },
  "disk": 30,
  "mounts": { "persistent": { "size": 50, "path": "/workspace" } },
  "ports": ["8000/http"],
  "gpu": { "id": "NVIDIA A40", "count": 1, "minCudaVersion": "13.0" },
  "cloud": "SECURE",
  "dataCenterIds": ["EU-SE-1"]
}
```

## 2. 최종 인자 문자열 (셸 인용 검토 완료)

### 왜 JSON 인자를 dot 표기로 바꿨나
- RunPod `args`는 문서상 "a bare shell string is treated as CMD and **split into arguments**"라고만 되어 있고, 따옴표를 어떻게 처리하는지는 적혀 있지 않다(RunPod REST v2 `POST /v2/templates`·`create-pod` 스키마).
- `--limit-mm-per-prompt '{"image": 1, "video": 0}'`처럼 쓰면, 셸 규칙으로 나누면 1개 토큰이 되지만 공백 기준으로 나누면 `'{"image":`, `1,`, `"video":`, `0}'` 5조각으로 깨진다. 어느 쪽인지 모르는 채로 쓰면 기동 실패를 Pod 시간으로 디버깅하게 된다.
- vLLM v0.32.0은 JSON 인자를 **dot 표기**로도 받는다: `--json-arg.key value` (vLLM CLI 문서, `vllm/utils/argparse_utils.py`). 값은 `json.loads`로 읽어서 `1`은 정수, `false`는 불리언이 된다. 같은 인자의 여러 키는 하나의 JSON으로 합쳐진다. 키 이름의 밑줄은 바뀌지 않는다(밑줄→하이픈 변환은 첫 `.` 앞 인자 이름에만 적용).
- 그래서 최종 문자열에는 **따옴표, 중괄호, 공백이 든 값, `$`가 하나도 없다.** 공백으로 나누든 셸 규칙으로 나누든 토큰이 같다(로컬에서 `str.split()`과 `shlex.split()` 결과 일치 확인).
- 공식 recipe도 같은 표기를 쓴다: Qwen3-VL recipe의 `--limit-mm-per-prompt.video 0`.

### Qwen3-VL-8B-Instruct (`serving/configs/qwen3vl-8b-instruct-bf16-a40.yaml`)
```
Qwen/Qwen3-VL-8B-Instruct --revision 0c351dd01ed87e9c1b53cbc748cba10e6187ff3b --served-model-name qwen3vl-8b --host 0.0.0.0 --port 8000 --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt.image 1 --limit-mm-per-prompt.video 0 --mm-processor-kwargs.max_pixels 2621440
```
vLLM이 받는 값: `limit_mm_per_prompt={"image": 1, "video": 0}`, `mm_processor_kwargs={"max_pixels": 2621440}`

### Qwen3.5-9B (`serving/configs/qwen3.5-9b-bf16-a40.yaml`)
```
Qwen/Qwen3.5-9B --revision c202236235762e1c871ad0ccb60c8ee5ba337b9a --served-model-name qwen3.5-9b --host 0.0.0.0 --port 8000 --dtype bfloat16 --max-model-len 8192 --gpu-memory-utilization 0.90 --limit-mm-per-prompt.image 1 --limit-mm-per-prompt.video 0 --mm-processor-kwargs.max_pixels 2621440 --reasoning-parser qwen3 --default-chat-template-kwargs.enable_thinking false
```
vLLM이 받는 값: 위 2개 + `reasoning_parser=qwen3`, `default_chat_template_kwargs={"enable_thinking": false}`

로컬 터미널에서 같은 명령을 셸로 칠 때(참고용)는 위 문자열을 그대로 `vllm serve` 뒤에 붙이면 된다. 따옴표가 없어서 셸 이스케이프가 필요 없다.

### config와 문자열이 일치하는지 확인 (로컬, GPU 없음)
```bash
uv run python -c "
import yaml, sys
for f in sys.argv[1:]:
    c = yaml.safe_load(open(f)); assert ' '.join(c['cmd']) == c['rendered_args'], f; print('OK', f)
" serving/configs/qwen3vl-8b-instruct-bf16-a40.yaml serving/configs/qwen3.5-9b-bf16-a40.yaml
```

## 3. 이미지 해상도 상한 (`--mm-processor-kwargs.max_pixels`)
- Qwen3-VL과 Qwen3.5는 같은 processor(`Qwen3VLProcessor` + `Qwen2VLImageProcessorFast`)를 쓴다. 기본 상한은 `preprocessor_config.json`의 `size.longest_edge = 16,777,216` 픽셀이다.
- **32×32 픽셀 = 비전 토큰 1개** (patch 16 × spatial merge 2). 기본 상한은 이미지 1장에 최대 16,384 토큰이라 `--max-model-len 8192`보다 크다.
- `max_pixels`와 `size.longest_edge`는 같은 값의 두 이름이다. vLLM은 둘 중 하나만 주면 나머지를 채운다(`Qwen2VLProcessingInfo._complete_mm_processor_size_aliases`). flat 키 `max_pixels`는 HF image processor의 유효 kwarg라서 `images_kwargs`로 전달된다. 우리는 이름이 짧고 모델 카드·vLLM 예시에서 흔히 쓰는 `max_pixels`를 쓴다.
- `2,621,440 = 2,560 토큰 × 1,024`. A4 150dpi(1240×1754)는 32 배수로 맞춘 1248×1760 = **2,145 토큰**으로 줄어들지 않고 들어간다.
- 상한보다 큰 이미지: 비율을 유지한 채 상한 안으로 **줄여서** 처리한다(smart_resize). 거절하지 않는다.
- 이미지 + 텍스트 토큰이 `max-model-len`을 넘는 요청: **그 요청만 HTTP 400**으로 거절된다("The decoder prompt (length N) is longer than the maximum model length of 8192"). 자르지 않는다. 기동은 실패하지 않는다. 상한을 안 걸면 기동 때 비전 인코더를 16,384토큰짜리 더미 이미지로 프로파일링해서 메모리를 더 쓴다.
- 요청마다 `mm_processor_kwargs`를 보내면 서버가 거절한다(`--trust-request-mm-kwargs` 기본 꺼짐). 해상도 실험은 서버 config를 새로 만들어서 한다.

## 4. 모델 교체 (같은 Pod, `update-pod`로 args만 바꾸기)
기본 이미지는 컨테이너 1개 = `vllm serve` 1개다. 다른 모델을 띄우려면 Pod 설정을 바꾼다.
1. 현재 모델의 측정과 로그 회수가 끝났는지 확인한다(로그는 컨테이너가 리셋되면 사라진다. `stream-pod-logs`로 받은 기동 로그를 먼저 `results/{model}/`에 저장).
2. `update-pod`에 **`args`만** 새 config의 `rendered_args`로 넣는다. `image`, `env`, `ports`, `mounts`는 넣지 않는다(빠진 필드는 그대로 유지).
   - 두 config의 `env`는 같으므로 바꿀 필요가 없다. 다르면 `env`도 함께 넣는다.
3. Pod가 리셋된다. 컨테이너 디스크(30GB)는 지워지고 `/workspace`(HF 캐시, vLLM 컴파일 캐시)는 남는다. 새 모델 가중치는 `/workspace/hf`에 추가로 받는다(19.33GB. 볼륨 50GB에 두 모델 36.9GB가 함께 들어간다).
4. 아래 5절 기준으로 기동을 다시 판정한다. `GET /v1/models`의 `id`가 새 served-model-name인지 꼭 본다(옛 모델이 응답하면 교체 실패).
- 승인: GATE-A에서 이번 실험 Pod 1대의 Qwen3.5 교체용 `update-pod`는 사전 승인됨(02-infra-plan). 다른 변경은 다시 묻는다.

## 5. 기동 성공 판정
`stream-pod-logs`를 짧게(`tail` 40, 몇 초 대기) 여러 번 읽는다. 순서대로 나와야 하는 줄:

| 순서 | 로그에서 볼 문구 | 확인할 것 |
|---|---|---|
| 1 | `non-default args: {...}` | config의 `expected_parsed` 값과 같은지. 특히 `limit_mm_per_prompt`, `mm_processor_kwargs`, `default_chat_template_kwargs`. **여기에 API 키가 보이면 안 된다** |
| 2 | `Resolved architecture: Qwen3VLForConditionalGeneration` / `Qwen3_5ForConditionalGeneration` | 이미지의 vLLM이 모델을 안다 |
| 3 | `Using max model len 8192` | 컨텍스트 길이 적용 |
| 4 | 가중치 다운로드 진행 → `Loading weights took ... seconds` / `Model loading took ... GiB` | 가중치 메모리 (기록) |
| 5 | `Available KV cache memory: ... GiB`, `GPU KV cache size: ... tokens`, `Maximum concurrency for 8,192 tokens per request: ...x` | KV 풀 (기록) |
| 6 | `torch.compile` / `Capturing CUDA graphs` | 첫 기동에서 가장 오래 걸린다 |
| 7 | `Application startup complete.` | API 준비 완료 |

로그 문구는 vLLM 버전마다 조금 다르다. 위 문구가 정확히 없으면 비슷한 줄을 원문 그대로 기록한다.

성공 = 아래 둘 다 만족:
1. 로그에 `Application startup complete.`
2. `GET {LLM_BASE_URL}/models` (헤더 `Authorization: Bearer $VLLM_API_KEY`)가 **HTTP 200**이고 `data[0].id`가 config의 `served_model_name`
   - 키 없이 호출하면 401이어야 한다(키가 걸렸는지 확인)

실패 대응표는 runpod 플러그인 `runpod-vllm/reference/boot-log-triage.md`를 따른다. 크래시 루프는 매분 과금되므로 먼저 멈추고 원인을 본다.

## 6. 로그에서 기록할 값 (`03-run-log.md` `## Model`, 원문은 `results/{model}/boot.log`)
| 값 | 로그 위치 | 비교 대상 |
|---|---|---|
| vLLM 버전, 받은 인자 | `vLLM API server version ...`, `non-default args` | config |
| 가중치 메모리 | `Model loading took X GiB` | config `model.weights_vram_gib` (±10%) |
| KV 캐시 메모리 | `Available KV cache memory: X GiB` | config `vram_estimate.kv_pool_gb` ÷ 1.074 |
| KV 블록 수 | `# GPU blocks: N` 또는 `GPU KV cache size: N tokens` | 버전에 따라 둘 중 하나가 나온다 |
| 최대 동시성 | `Maximum concurrency for 8,192 tokens per request: X` | config `vram_estimate.expected_max_concurrency_x` |
| 기동 소요 | 첫 로그 ~ `Application startup complete.` 시각 | 01-plan 시간표 |
| 실제 VRAM 사용 | Pod 안 `nvidia-smi`는 못 쓴다(SSH 없음). `get-pod`의 GPU 사용 지표가 있으면 그 값, 없으면 `GET /metrics`의 `vllm:kv_cache_usage_perc`와 로그의 `Model loading took` + `Available KV cache memory` 합으로 대신한다 | 48GB × 0.90 = 43.2GB |
| 이미지 1장 `usage.prompt_tokens` | 첫 요청 응답 | 2,145 + 텍스트 (H2) |

저장 전에 로그에서 API 키 문자열을 검색해(`grep -c "$VLLM_API_KEY" boot.log` 결과 0) 노출이 없는지 확인한다. `get-pod` 원문은 `env`를 가린 뒤 저장한다.

## 7. 보안 메모 (공개 proxy URL)
- `VLLM_API_KEY`는 `/v1`, `/v2`, `/inference` 경로만 보호한다. vLLM v0.32.0은 SageMaker 호환 경로 **`/invocations`(추론 가능)와 `/ping`을 조건 없이 등록하고, 이 경로는 키 검사를 하지 않는다**(`vllm/entrypoints/launchers/cli_args.py`의 `api_key` 설명, `launchers/api_server/routers.py`). `/metrics`, `/health`, `/version`도 키 없이 열린다.
- 이 버전에는 `/invocations`를 끄는 인자를 찾지 못했다. 그래서 RunPod proxy URL(`https://<pod-id>-8000.proxy.runpod.net`)을 아는 사람은 키 없이 추론을 호출할 수 있다. 대응: URL을 산출물·채팅에 적지 않는다, Pod 수명을 측정 시간으로 제한한다, 측정이 끝나면 바로 Terminate한다.

## 8. 파일 위치
- 실험 설정: `serving/configs/{model}-{quant}-{gpu}.yaml`. 인자를 바꾸면 새 파일을 만든다(P4).
- 기동 로그·검증 응답: `artifacts/experiments/{id}/results/{served-model-name}/`. 코드 폴더에 결과를 쓰지 않는다(P5).
- `start.sh`는 만들지 않았다. 공식 이미지의 ENTRYPOINT(`vllm serve`)에 인자만 넘기면 되고, Pod 안에 파일을 둘 방법이 없기 때문이다. 커스텀 이미지가 필요해지면 그때 `Dockerfile`과 함께 추가한다.
