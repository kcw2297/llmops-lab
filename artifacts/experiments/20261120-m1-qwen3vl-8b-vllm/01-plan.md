# 01-plan — Qwen3-VL-8B-Instruct vLLM 서빙과 Qwen3.5-9B 스모크 대조 (M1)

- 실험 ID: `20261120-m1-qwen3vl-8b-vllm`
- 작성: ml-engineer, 2026-11-20 (T01)
- 상태: 계획. 리소스 생성 전(GATE-A 대기)
- 이 문서의 수치 표기: **(확인)** = HF/vLLM 원문에서 직접 읽은 값, **(계산)** = 확인된 값으로 계산한 값, **(추정)** = 측정 전 가정. `확인 필요:` = 아직 근거가 없는 값.

## 요약
- 마일스톤: **M1** (roadmap: "Qwen3-VL-8B-Instruct를 vLLM으로 Pod에 서빙하고, 같은 합성 문서로 비교 대상과 대조")
- 질문: **"GPU 1장(48GB급)에서 Qwen3-VL-8B-Instruct를 bf16·max-model-len 8192로 vLLM 서빙할 때, 합성 부가세 납부서 1장의 이미지 토큰 수는 얼마이고, JSON schema 구조화 출력이 8/8건 유효한가? 같은 조건에서 Qwen3.5-9B는 VRAM(KV 여유)과 필드 정답률이 어떻게 다른가?"**
- 바꾸는 변수: **모델 1개**(Qwen3-VL-8B-Instruct ↔ Qwen3.5-9B). 나머지는 모두 고정.

## 가설 (틀려도 된다. 틀린 가설이 학습 포인트다)
| # | 가설 | 예상 수치 | 이유 |
|---|---|---|---|
| H1 | 두 모델 모두 48GB급 1장에서 bf16으로 기동된다 | 기동 2/2 | 가중치 17.5GB/19.3GB (계산) + KV + 여유가 43GB(=48×0.90) 안에 들어간다. 아래 VRAM 계산 참고 |
| H2 | 이미지 1장의 `prompt_tokens`는 약 2,400~2,600 | 이미지 토큰 ≈ 2,145 + 텍스트(지시문·스키마) 250~450 (추정) | 두 모델 모두 patch 16 × merge 2 → **32×32 픽셀당 토큰 1개** (확인). A4 150dpi(1240×1754)는 32 배수로 맞추면 1248×1760 → 39×55 = 2,145 토큰 (계산) |
| H3 | JSON 유효율은 두 모델 모두 100% | 8/8, 8/8 | 구조화 출력(guided decoding)이 스키마 밖 토큰을 막는다. 형식은 보장되지만 값은 보장되지 않는다 |
| H4 | 기동 로그의 `Maximum concurrency`(8192 토큰 기준)는 Qwen3.5-9B가 Qwen3-VL-8B보다 3배 이상 크다 | Qwen3-VL ≈ 18배, Qwen3.5 ≈ 60배 (추정, 48GB 기준) | Qwen3.5는 32층 중 8층만 full attention이고 나머지 24층은 고정 크기 상태(linear attention)만 쓴다. 토큰당 KV가 144KiB → 32KiB로 줄어든다 (계산) |
| H5 | 깨끗한 합성 인쇄 문서 필드 정답률은 두 모델 모두 90% 이상, 차이는 8장으로는 판단 불가 | 각 ≥ 90% (추정) | 같은 템플릿·깨끗한 렌더링이라 어렵지 않다. 표본 8장은 1건 차이가 12.5%p라서 결론용이 아니다(본격 비교는 M5) |

## 모델
| 항목 | 베이스 | 비교 대상 |
|---|---|---|
| repo | `Qwen/Qwen3-VL-8B-Instruct` (확인) | `Qwen/Qwen3.5-9B` (확인. `-Instruct` 접미사 없음: 하나의 모델이 thinking/non-thinking을 다 하고 **기본값이 thinking**) |
| revision (고정) | `0c351dd01ed87e9c1b53cbc748cba10e6187ff3b` (확인, lastModified 2025-10-15) | `c202236235762e1c871ad0ccb60c8ee5ba337b9a` (확인, lastModified 2026-03-02) |
| 라이선스 | Apache-2.0 (확인, 상업 사용 가능) | Apache-2.0 (확인) |
| gated | 아니오 (확인) → HF_TOKEN 없이 다운로드 가능 | 아니오 (확인) |
| 아키텍처 | `Qwen3VLForConditionalGeneration` (확인) | `Qwen3_5ForConditionalGeneration` (확인) |
| 전체 파라미터 | 8,767,123,696 (BF16) (확인) | 9,653,104,368 (BF16 9,653,100,528 + F32 3,840) (확인) |
| 언어 모델 (임베딩·lm_head 포함) | 8.190B (계산: safetensors 헤더 집계) | 8.954B (계산) |
| 비전 인코더 | 0.576B (계산) (depth 27, hidden 1152) | 0.456B (계산) (depth 27, hidden 1152) |
| 기타 | - | MTP(다음 토큰 다중 예측) 헤드 0.243B (계산) |
| 레이어 | 36 (전부 full attention) (확인) | 32 = 8 × (linear 3 + full 1) (확인). full attention 8층, linear attention(Gated DeltaNet) 24층 |
| Q 헤드 / KV 헤드 / 헤드 차원 | 32 / **8** / **128** (확인) | full attn: 16 / **4** / **256** (확인). linear attn: QK 헤드 16, V 헤드 32, key/value head dim 128, conv kernel 4 (확인) |
| 기본 컨텍스트 | 262,144 (확인) | 262,144 (확인) |
| 이미지 전처리 기본값 | `longest_edge` 16,777,216 px, `shortest_edge` 65,536 px, patch 16, merge 2 (확인) | 동일 (확인) |
| vLLM 최소 버전 | **0.11.0** (확인: vLLM recipes Qwen3-VL "Install vLLM >=0.11.0") | **0.17.0** (확인: v0.17.0 릴리스 노트 "Full support for the Qwen3.5 model family (#34110)", 2026-03-07) |
| 한국어 | 확인 필요: 모델 카드에 "OCR 32개 언어"만 있고 언어 목록에 한국어 명시를 찾지 못함 | 모델 카드 "201개 언어·방언" (확인). 한국어 문서 OCR 품질은 확인 필요 |
| 모델 카드 권장 vLLM 인자 | - | `--reasoning-parser qwen3` (확인). thinking 끄기: `--default-chat-template-kwargs '{"enable_thinking": false}'` (확인: vLLM Qwen3.5 recipe) |

출처: `huggingface.co/{repo}/resolve/main/config.json`, `preprocessor_config.json`, `README.md`, `huggingface.co/api/models/{repo}`, safetensors 헤더(Range 요청으로 텐서 shape만 읽어 집계), `docs.vllm.ai/projects/recipes/en/latest/Qwen/Qwen3-VL.html`, `.../Qwen3.5.html`, GitHub vLLM releases (2026-11-20 조회).

**vLLM 이미지 태그 제안: `vllm/vllm-openai:v0.32.0`** (amd64 압축 9.21GB, 2026-10-18 게시, Docker Hub 확인)
- 왜: 두 모델의 최소 버전(0.17.0)을 모두 넘고, 같은 태그 하나로 두 모델을 띄워야 "모델만 바꾼" 비교가 된다. 최신 v0.34.0(2026-11-16)은 나온 지 4일이라 초심자 첫 실험에는 한 달 지난 v0.32.0이 덜 위험하다.
- 확인 필요: v0.32.0 이미지가 요구하는 CUDA/드라이버 버전과 RunPod 호스트 호환성(infra-engineer). 문제가 있으면 v0.34.0으로 바꾸고 run-log에 기록한다.

## VRAM 계산
백엔드 비유: **가중치 = 서버에 올리는 바이너리**(고정), **KV cache = 요청별 세션 메모리**(동시 요청 수 × 대화 길이에 비례), **여유분 = 런타임·스레드 스택**.

공통 가정
- 정밀도 bf16 = 2바이트/파라미터. KV cache dtype = 모델 dtype(bf16, 2바이트). 단위 GB = 10^9 바이트(vLLM 로그는 GiB이므로 ÷1.074 해서 비교).
- `--max-model-len 8192`, 계산용 동시 시퀀스 수 **4**(M1 스모크는 동시성 1이지만, vLLM 기동에 필요한 최소 여유 + 약간의 병렬 호출을 고려). M2 대비용으로 16도 함께 계산.
- 여유분 3.0GB (추정): CUDA 컨텍스트 0.5~1, CUDA graph 0.5~1, 프리필 활성화 + 비전 인코더(이미지 1장) 피크 1~1.5. skill 기본값(1~2GB)보다 크게 잡은 이유는 VLM은 기동 시 비전 인코더 프로파일링 메모리가 추가로 들기 때문이다.
- `--gpu-memory-utilization 0.90` → 필요한 GPU 메모리 = 합계 ÷ 0.90.

### A. Qwen3-VL-8B-Instruct (표준 트랜스포머)
```
가중치   = 8,767,123,696 × 2 B                       = 17.53 GB
           (언어 모델 8.190B × 2 = 16.38 GB + 비전 인코더 0.576B × 2 = 1.15 GB)
KV/토큰  = 2(K,V) × 36층 × 8 KV헤드 × 128 차원 × 2 B  = 147,456 B (144 KiB)
KV/시퀀스 = 147,456 B × 8,192 토큰                    = 1.208 GB
KV(4 시퀀스)  = 1.208 × 4                             = 4.83 GB
여유분                                                = 3.00 GB (추정)
합계(4 시퀀스) = 17.53 + 4.83 + 3.00                  = 25.37 GB → ÷0.90 = 28.2 GB 필요
합계(1 시퀀스) = 17.53 + 1.21 + 3.00                  = 21.74 GB → ÷0.90 = 24.2 GB 필요
합계(16 시퀀스, M2 대비) = 17.53 + 19.33 + 3.00       = 39.86 GB → ÷0.90 = 44.3 GB 필요
```

### B. Qwen3.5-9B (하이브리드: full attention 8층 + linear attention 24층)
linear attention 층은 토큰마다 KV를 쌓지 않고, **시퀀스마다 고정 크기 상태(state)** 하나만 둔다. 백엔드 비유로는 "요청 로그를 계속 append하는 세션"(full attention) 대신 "고정 크기 카운터 몇 개만 갱신하는 세션"(linear attention)이다. 그래서 컨텍스트가 길어져도 이 부분은 늘지 않는다.
```
가중치   = 9,653,104,368 × 2 B                        = 19.31 GB
           (언어 모델 8.954B → 17.91 GB, 비전 0.456B → 0.91 GB, MTP 0.243B → 0.49 GB)
           ※ MTP는 speculative decoding을 안 켜면 로드 안 될 수 있음. 보수적으로 포함. 확인 필요: vLLM이 MTP 가중치를 기본 로드하는지

[full attention 8층: 토큰에 비례]
KV/토큰  = 2 × 8층 × 4 KV헤드 × 256 차원 × 2 B         = 32,768 B (32 KiB)
KV/시퀀스 = 32,768 B × 8,192                          = 0.268 GB

[linear attention 24층: 시퀀스당 고정]
재귀 상태 = 24층 × 32 V헤드 × 128 × 128 × 4 B(fp32)    = 50,331,648 B = 0.050 GB
           (config의 mamba_ssm_dtype = float32. 확인 필요: vLLM이 fp32로 두는지, bf16이면 0.025 GB)
conv 상태 = 24층 × (16×128×2 + 32×128 = 8,192 채널) × (커널 4−1) × 2 B = 0.001 GB
상태/시퀀스                                            ≈ 0.052 GB

시퀀스당 합계 = 0.268 + 0.052                         = 0.320 GB
KV+상태(4 시퀀스)  = 0.320 × 4                        = 1.28 GB
여유분                                                = 3.00 GB (추정)
합계(4 시퀀스) = 19.31 + 1.28 + 3.00                  = 23.59 GB → ÷0.90 = 26.2 GB 필요
합계(16 시퀀스, M2 대비) = 19.31 + 5.12 + 3.00        = 27.43 GB → ÷0.90 = 30.5 GB 필요
```
비교: 8192 토큰 시퀀스 1개당 메모리는 Qwen3-VL 1.208GB vs Qwen3.5 0.320GB, 약 **3.8배 차이** (계산). 가중치는 Qwen3.5가 1.8GB 더 크지만 KV는 훨씬 작다. 이것이 이번 실험의 핵심 학습 포인트다.

### 기동 로그 예측 (H4 검증용, 48GB급 기준, 추정)
```
KV 풀 = 48 × 0.90 − 가중치 − 여유분
Qwen3-VL: 43.2 − 17.53 − 3.0 = 22.67 GB → ÷147,456 B ≈ 153.7k 토큰 → ÷8,192 ≈ 18.8배
Qwen3.5 : 43.2 − 19.31 − 3.0 = 20.89 GB → ÷0.320 GB ≈ 65배
```
- 확인 필요: vLLM 하이브리드 KV 할당기는 full attention 블록과 linear 상태를 같은 페이지 크기로 맞추므로 실제 `Maximum concurrency`는 위 값과 다를 수 있다. 기동 로그의 `# GPU blocks`, `Maximum concurrency`, `Model loading took X GiB`를 run-log에 그대로 남겨 계산과 비교한다.

### GPU 등급 요구치 (가격·특정 상품 선택은 infra-engineer)
| 구분 | VRAM | 근거 |
|---|---|---|
| 불가 | 24GB급 | Qwen3-VL 1 시퀀스만 잡아도 24.2GB 필요 (계산). 실제 24GB 카드 가용량은 그보다 작다 |
| **최소** | **32GB급** | 두 모델 4 시퀀스 합계 최대 28.2GB (계산) 충족. 단 Qwen3-VL KV 풀이 약 8GB(≈ 6.9배 동시성, 추정)로 M2 부하 테스트에는 부족 |
| **권장** | **48GB급** | Qwen3-VL 16 시퀀스(44.3GB, 계산)까지 들어가서 M2에서도 같은 GPU로 이어갈 수 있다. OOM 디버깅 시간을 줄여 초심자 실험에 안전하다 |
| 공통 조건 | bf16 지원(Ampere 이상, compute capability ≥ 8.0), GPU 1장(`--tensor-parallel-size 1`) | 두 모델 모두 bf16 가중치 |

## 이미지 토큰 예산 (`max-model-len`과의 관계)
- 이미지 토큰 수 = (높이/32) × (너비/32) (확인: patch 16 × spatial merge 2).
- 기본 전처리 상한 `longest_edge` 16,777,216 px → 최대 **16,384 토큰** (계산)으로 `max-model-len 8192`를 넘는다. 고해상도 이미지가 들어오면 요청이 거절되거나 기동 프로파일링이 실패할 수 있으므로 **상한을 낮춘다.**
- 제안: 최대 픽셀 2,621,440 (= 2,560 토큰 × 1,024) (계산). A4 150dpi(1240×1754 → 2,145 토큰)는 줄이지 않고 들어가고, 프롬프트·출력에 약 5,600 토큰이 남는다.
- 확인 필요: vLLM v0.32.0에서 Qwen3-VL/Qwen3.5의 픽셀 상한을 넘기는 `--mm-processor-kwargs` 키 이름(`max_pixels` 또는 `size.longest_edge`)과, 상한이 `max-model-len`보다 클 때 vLLM이 오류를 내는지 자동으로 자르는지. 기동 전 vLLM 문서로 확인하고, 안 되면 합성 이미지 해상도를 고정(1240×1754)하는 것으로 대체한다.

## 사용 config (파일 생성은 GATE-A 이후)
- 서빙
  - `serving/configs/qwen3vl-8b-instruct-bf16-{gpu}.yaml`
  - `serving/configs/qwen3.5-9b-bf16-{gpu}.yaml`
  - `{gpu}`는 T02에서 infra-engineer가 정한 GPU 이름(소문자, 예: 48GB급 확정 후 기입)으로 채운다.
- 서빙 레시피: `serving/recipes/vllm/start.sh` (config를 읽어 `vllm serve` 인자를 만든다. 두 모델이 같은 레시피를 쓰고 config만 다르다: P4)
- 측정 설정: `eval/configs/m1-smoke-vat-slip.yaml` (엔드포인트, 데이터셋 경로, 스키마, temperature 0, 동시성 1)
- 레시피 git 커밋: 아직 레시피 없음. 현재 HEAD `2302be9`. 레시피 작성 후 커밋 sha를 `03-run-log.md`에 기록한다.

### config에 넣을 vLLM 인자 (계획값)
| 인자 | Qwen3-VL-8B | Qwen3.5-9B | 왜 |
|---|---|---|---|
| 이미지 | `vllm/vllm-openai:v0.32.0` | 동일 | 엔진 버전 고정. 모델만 바꾼다 |
| `--revision` | `0c351dd...` | `c202236...` | 가중치가 바뀌어도 재현 가능 |
| `--dtype` | bfloat16 | bfloat16 | 모델 기본 정밀도. 양자화는 M3 |
| `--max-model-len` | 8192 | 8192 | 이미지 ~2.1k + 프롬프트 + JSON 출력에 충분. 기본값 262K로 두면 KV를 과도하게 잡는다 |
| `--gpu-memory-utilization` | 0.90 | 0.90 | skill 기본값. 10%는 다른 프로세스·단편화 여유 |
| `--limit-mm-per-prompt` | `'{"image":1,"video":0}'` | 동일 | 문서 1장씩. 비디오 0으로 비디오 프로파일링 메모리를 아낀다(vLLM recipe 권장) |
| `--mm-processor-kwargs` | 픽셀 상한 2,621,440 (키 이름 확인 필요) | 동일 | 위 "이미지 토큰 예산" 참고 |
| `--max-num-seqs` | 기본값 | 기본값 | M1은 동시성 1. 튜닝은 M2 |
| `--reasoning-parser` | 없음 | `qwen3` | Qwen3.5 모델 카드 권장 |
| `--default-chat-template-kwargs` | 없음 | `'{"enable_thinking": false}'` | Qwen3.5 기본값이 thinking이다. 추출은 정확히 읽기가 중요하고 thinking 토큰은 지연만 늘린다. Instruct 모델과 공정하게 비교하려고 끈다 |
| `--served-model-name` | `qwen3vl-8b` | `qwen3.5-9b` | 클라이언트 `LLM_MODEL` 값 |
| 구조화 출력 | 요청의 `response_format: json_schema` | 동일 | 서버 인자 없이 동작하는지 기동 후 확인 |

알려진 함정 (Qwen3.5): CUDA graph 캡처 크기가 mamba(linear) 캐시 크기보다 크면 기동 실패. 그때는 `--max-cudagraph-capture-size`를 기본 512에서 낮춘다 (확인: vLLM Qwen3.5 recipe 트러블슈팅).

## 실험 변수 / 고정 조건
- **변수**: 모델 (Qwen3-VL-8B-Instruct ↔ Qwen3.5-9B) 1개
- **고정**: vLLM 이미지 태그, GPU 1장(같은 Pod), bf16, `max-model-len 8192`, `gpu-memory-utilization 0.90`, 이미지 해상도(1240×1754, 픽셀 상한 동일), 데이터셋 `vat-slip-v1` 8장, 같은 JSON schema와 지시문, `temperature=0`, `max_tokens=1024`, 동시성 1, 워밍업 1건(측정 제외)
- 의도적 차이: Qwen3.5만 thinking 끄기 인자 추가(모델 기본 동작을 Instruct와 맞추기 위한 것이라 변수로 보지 않는다)
- 모델 카드 권장 샘플링(Qwen3.5 non-thinking: temperature 0.7 등)과 다르게 `temperature=0`을 쓴다. 추출은 재현성이 우선이라서다. 결과 해석 시 이 점을 적는다.

## 합성 문서 데이터 계획 (GPU 없이 로컬에서 사전 생성. 생성은 ocr-engineer, GATE-A 전에 해도 비용 0)
- 이름·위치: `eval/datasets/vat-slip-v1/`
  - `README.md` (데이터 카드: 생성 방법, 건수 8, 양식 1종, 해상도, 라이선스 "자체 합성", 실데이터 아님 명시)
  - `schema.json` (JSON Schema 1개)
  - `images/vat-slip-001.png` ~ `008.png`
  - `labels/vat-slip-001.json` ~ `008.json` (정답 JSON)
  - 생성 스크립트는 `eval/src/ocr_eval/` 아래(코드와 데이터 분리: P1)
- 양식: **가상 부가가치세 납부서 1종** (HTML/이미지 템플릿 렌더링, 한국어 인쇄체)
- 건수: **8장**. 값만 바꾸고 레이아웃은 같다. 왜 8장: 5~10장 범위 안에서 두 모델 × 8장 호출이 수 분 안에 끝나고, 금액 자릿수(6~10자리)·날짜·번호 형식을 골고루 넣기에 충분하다.
- 필드 예시(약 8개): 납부자 상호(가상, 예: "가나다상사"), 사업자등록번호(형식만 맞춘 가짜 번호, 실존 번호 회피), 과세기간(`YYYY-MM-DD` 시작·끝), 납부기한, 세목("부가가치세"), 납부금액(정수, 원), 전자납부번호(가짜), 관할세무서명(가상 표기 가능)
- 정규화 규칙: 금액 정수(콤마 제거), 날짜 `YYYY-MM-DD`, 없는 값 `null`
- 렌더링: A4 150dpi PNG 1240×1754, 노이즈·회전 없음(M1은 깨끗한 조건. 열화 조건은 M5)
- 금지: 실제 회사명·사업자번호·계좌번호 사용 금지 (Public 레포 규칙)

## 실행 단계와 예상 GPU 시간
GPU 과금은 Pod 생성부터 종료까지 계속된다. **코드·데이터·config를 전부 로컬에서 끝낸 뒤** Pod를 만든다.

| # | 단계 | 현실값(h) (추정) | 상한값(h) (추정) | 메모 |
|---|---|---|---|---|
| 0 | 로컬 준비: 합성 데이터 8장, 스키마, 호출 스크립트, config 2개, start.sh | 0 | 0 | GPU 없음. GATE-A 전에 완료 |
| 1 | Pod 생성 + 이미지 pull (9.21GB 압축) | 0.15 | 0.30 | 호스트에 캐시가 없으면 길어진다 |
| 2 | Qwen3-VL 가중치 다운로드 (17.55GB) | 0.10 | 0.25 | 50~200MB/s 가정 (추정). HF 속도는 확인 필요 |
| 3 | vLLM 기동 (로드 + 프로파일링 + CUDA graph) | 0.15 | 0.30 | 인자 오류로 1~2회 재기동 포함 |
| 4 | Qwen3-VL 호출·측정: `/v1/models`, 이미지 1장, 구조화 출력, 8장 대조, 로그 기록 | 0.75 | 1.50 | 첫 실험 디버깅(이미지 base64 형식, 스키마 오류 등) 여유 포함 |
| 5 | 모델 교체: Qwen3-VL 종료 → Qwen3.5 가중치 다운로드 (19.33GB) | 0.10 | 0.25 | |
| 6 | Qwen3.5 기동 | 0.15 | 0.40 | 하이브리드 모델 CUDA graph 함정, thinking 끄기 확인 |
| 7 | Qwen3.5 호출·측정 (같은 8장) | 0.50 | 1.00 | 스크립트 재사용이라 4번보다 짧다 |
| 8 | 결과·로그 회수, teardown | 0.15 | 0.25 | 결과를 로컬 `results/`로 옮긴 뒤 종료 |
| | 대기·자리비움 버퍼 | 0 | 0.25 | |
| | **합계** | **2.05** | **4.50** | |

- 비용 환산은 infra-engineer(T02)가 이 시간으로 계산한다.
- 상한 4.5h를 넘기면 그 자리에서 멈추고 Pod를 종료(또는 정지)한 뒤 원인을 기록한다.

## 디스크 요구량
| 항목 | 크기 | 근거 |
|---|---|---|
| Qwen3-VL-8B-Instruct 가중치 | 17.55 GB | HF API 파일 합계 (확인) |
| Qwen3.5-9B 가중치 | 19.33 GB | HF API 파일 합계 (확인) |
| HF 캐시 합계 | 36.9 GB | 같은 Pod에서 순서대로 받으므로 두 개 모두 남는다(지우지 않으면 재기동 시 재다운로드 없음) |
| vLLM 컴파일 캐시, 로그, 결과 | ~2 GB (추정) | torch.compile/CUDA graph 캐시 |
| **볼륨 디스크 (`/workspace`, HF_HOME 지정)** | **권장 50 GB** | 36.9 + 2 + 여유 약 25% |
| **컨테이너 디스크** | **권장 20 GB** | pip 캐시, /tmp. 확인 필요: RunPod에서 이미지(압축 9.21GB, 압축 해제 크기 미확인)가 컨테이너 디스크 한도에 포함되는지 (infra-engineer) |
- 왜 Network Volume이 아닌가: M1은 Pod 1개를 짧게 쓰고 끝낸다. 볼륨을 계속 남기면 매달 보관 비용이 나간다. M2 이후 재사용이 필요해지면 그때 다시 정한다(결정은 infra-engineer와 사용자).

## 성공 기준 (전부 숫자)
1. 기동 성공 **2/2** 모델 (기동 로그에 오류 없이 API 준비 완료)
2. `GET /v1/models` **HTTP 200**, 응답에 served-model-name 포함 (모델별 1회)
3. 이미지 1장 `POST /v1/chat/completions` **HTTP 200**, `usage.prompt_tokens` 기록, 값 ≤ 8192
4. JSON 유효율 **100%** (모델별 8/8, `json.loads` 성공 + `schema.json` 검증 통과)
5. 필드 정답률 **기록** (모델별 필드 수 × 8장 기준 %, 금액 필드 따로). 통과 기준은 두지 않는다(표본이 작다). 참고 기대치 ≥ 90%
6. 기동 로그 값 기록: `Model loading took ... GiB`, `# GPU blocks`, `Maximum concurrency` (모델별 3개)
7. 가중치 메모리 계산값 대비 실측 차이 **±10% 이내** (17.53GB=16.33GiB, 19.31GB=17.98GiB와 비교. MTP 미로드면 Qwen3.5는 약 17.5GiB)
8. 실제 GPU 사용 시간 **≤ 4.5h**, 실험 종료 후 teardown 여부 확인 완료

## 범위 밖 (이번에 안 하는 것)
- 부하 테스트·동시성 스윕·지연 분위수(M2). 이번 지연은 동시성 1 참고값만 기록
- 양자화(AWQ/FP8) 비교(M3)
- LoRA 학습과 어댑터 서빙(M4). Qwen3-VL/Qwen3.5의 vLLM LoRA 지원 확인도 M4에서
- 본격 정확도 평가(양식 여러 개, 양식당 20~50장, 열화 이미지)(M5)
- 앱(`ocr-agent`) 연결(M6)
- Serverless, Network Volume
- `max-model-len`·해상도·thinking on/off 비교 (각각 별도 실험)
- 다른 후보(Gemma 4, PaddleOCR-VL, GLM-OCR, 외부 API)
- MTP speculative decoding

## 이번에 배울 개념 후보
1. **VRAM 산정** (가중치 + 비전 인코더 + KV + 여유) — 계산값과 기동 로그 `Model loading took`·`Maximum concurrency` 비교
2. **이미지 토큰** — 32×32 픽셀 = 토큰 1개, 해상도와 `max-model-len`의 관계, 실제 `prompt_tokens`
3. **하이브리드 attention (linear attention)과 KV cache** — 같은 8192 토큰에서 시퀀스당 1.21GB vs 0.32GB가 되는 이유
4. **구조화 출력(guided decoding)과 thinking 모드** — 형식 보장과 값 정확도의 차이, chat template 인자로 thinking 끄기

## 미확인 항목 정리 (`확인 필요:`)
- `--mm-processor-kwargs`의 픽셀 상한 키 이름(vLLM v0.32.0), 기본 상한(16,384 토큰) > max-model-len일 때 동작
- vLLM이 Qwen3.5 linear 상태를 fp32로 두는지(시퀀스당 0.050 vs 0.025GB), MTP 가중치를 기본 로드하는지
- 하이브리드 KV 할당기의 실제 `Maximum concurrency`(계산 65배는 근사)
- `vllm/vllm-openai:v0.32.0`의 CUDA/드라이버 요구와 RunPod 호스트 호환성, 압축 해제 이미지 크기와 컨테이너 디스크 포함 여부 (infra-engineer)
- Qwen3-VL OCR 지원 32개 언어에 한국어가 포함되는지(모델 카드에 언어 목록 없음). 실측으로 확인
- HF 다운로드 속도(현실값 0.10h 가정)

## 팀 전달 사항
- → infra-engineer (T02): GPU 1장, **최소 32GB / 권장 48GB급**, bf16 지원(compute capability ≥ 8.0), 컨테이너 디스크 20GB, 볼륨 디스크 50GB, 이미지 `vllm/vllm-openai:v0.32.0`, 노출 포트 8000(HTTP), HF_TOKEN 불필요(두 모델 모두 non-gated). GPU 시간 현실 2.05h / 상한 4.5h.
- → ocr-engineer: API 스펙 = OpenAI 호환 `POST /v1/chat/completions`, 이미지는 `image_url`에 base64 data URL 1장, `response_format: {"type":"json_schema", ...}`, `temperature 0`, `max_tokens 1024`. 데이터셋 `eval/datasets/vat-slip-v1/` 8장을 GATE-A 전에 로컬에서 준비.

## 0단계 확인 결과 (2026-11-21, ml-engineer)
위 "확인 필요" 중 서빙 관련 항목은 `03-run-log.md` `## Model`에 출처와 함께 정리했다. 요약:
- 픽셀 상한 키: `--mm-processor-kwargs`의 `max_pixels` (두 모델 같음). config에는 `--mm-processor-kwargs.max_pixels 2621440` (dot 표기)
- 상한 > max-model-len: 기동은 성공, 해당 요청만 400. 이미지는 상한 안으로 축소
- Qwen3.5 ssm 상태 float32(확인, 0.050GB/시퀀스 유지), MTP 미로드(확인) → 가중치 VRAM 17.53GiB 기준으로 성공 기준 7을 판정
- Qwen3-VL OCR 한국어: 기술 보고서 Figure 2에 포함(약 87%, 그래프 판독, 모델 크기 미명시)
- 이 표의 GPU 시간은 모두 (추정)이다 (05-review 지적 #4 반영)
- 사용 config: `serving/configs/qwen3vl-8b-instruct-bf16-a40.yaml`, `serving/configs/qwen3.5-9b-bf16-a40.yaml`
