# 02-infra-plan — 20261120-m1-qwen3vl-8b-vllm

- 작성: infra-engineer (T02-infra-quote), 2026-11-20
- 상태: **승인됨 (GATE-A, 2026-11-21)** — 문서 끝 "GATE-A 결과" 참고. 이 문서를 쓰면서 리소스는 하나도 만들지 않았다. RunPod MCP는 조회 도구만 썼다.
- 입력: `01-plan.md` 팀 전달 사항. GPU 1장, 최소 32GB / 권장 48GB, bf16 지원(CC ≥ 8.0), 컨테이너 디스크 20GB, 볼륨 디스크 50GB, 이미지 `vllm/vllm-openai:v0.32.0`, 포트 8000/http, HF_TOKEN 불필요, GPU 시간 현실 2.05h / 상한 4.5h
- 환율: 1 USD = ₩1,450 (CLAUDE.md)
- 예산: 11월 누적 ₩0 / ₩200,000 (0%), `cost-ledger.md` 기준. 경고선(80%)과 차단선(100%) 모두 해당 없음

## 0. 인프라 비유로 먼저 정리
| RunPod | AWS/K8s 대응 | 이번 실험에서 |
|---|---|---|
| Pod | GPU가 붙은 EC2 1대 (컨테이너 1개만 도는 ECS task라고 봐도 된다) | `vllm/vllm-openai` 이미지 1개를 실행 |
| Secure Cloud / Community Cloud | 자사 데이터센터 온디맨드 / 개인 호스트 마켓플레이스 | Secure 사용 |
| 컨테이너 디스크 | 인스턴스 루트 볼륨 (재시작하면 초기화) | 30GB, pip·/tmp |
| Pod 볼륨 디스크 (`/workspace`) | 인스턴스에 붙은 EBS, delete-on-termination=true | 50GB, HF 캐시 |
| Network Volume | EFS (AZ 단위, 여러 인스턴스가 붙일 수 있음, 따로 과금) | 이번엔 쓰지 않음 |
| Stop | EC2 stop (컴퓨트 과금 중단, EBS 과금 계속) | 막힐 때만 |
| Terminate | EC2 terminate + EBS 삭제 | 측정이 끝나면 즉시 |

## 1. GPU 후보 비교 (실시간 조회)
조회: `list-gpu-types`(`include=AVAILABILITY`, `product=POD`)를 `cloud=SECURE`와 `cloud=COMMUNITY`로 각 1회, `get-capacity`(Secure 전용, CUDA 12.8/12.9/13.0/13.2 probe), `list-data-centers`(`include=GPU_AVAILABILITY`, `regions=EUROPE`). 조회 시각 2026-11-20 (이 문서 작성 직전). 재고는 수시로 바뀌므로 생성 직전에 다시 조회한다.

| GPU (catalog id) | VRAM | Secure $/h (≈₩/h) | Secure 재고 / DC | Community $/h | Community 재고 | 재고가 있는 호스트 CUDA |
|---|---|---|---|---|---|---|
| **A40** (`NVIDIA A40`) | 48GB | **$0.59 (≈₩856)** | **LOW / EU-SE-1** | $0.35 | NONE | Secure 13.2만 Low (12.8·12.9·13.0 Out) |
| RTX PRO 4500 (`NVIDIA RTX PRO 4500 Blackwell`) | 32GB | $0.72 (≈₩1,044) | MEDIUM / EU-RO-1(MEDIUM), EU-CZ-1·EUR-IS-1(LOW) | $0.34 | NONE (Community 미제공) | Secure 13.2만 Medium |
| L40S (`NVIDIA L40S`) | 48GB | $1.09 (≈₩1,581) | LOW / 응답에 DC 목록 없음 | $0.79 | NONE | Secure 13.2만 Low |
| RTX 5090 (`NVIDIA GeForce RTX 5090`) | 32GB | $1.39 (≈₩2,016) | LOW / EU-RO-1, EUR-NO-1 | $0.69 (≈₩1,001) | LOW (DC 목록 없음) | Secure 13.2 Low. Community 12.8·13.0·13.2·13.4 있음 |

같은 조회에서 48GB급 중 **재고가 없는 것**: RTX A6000(Secure $0.69, Community $0.33 모두 NONE), L40(Secure $0.82 NONE), RTX 6000 Ada(Secure $1.09 NONE), RTX PRO 5000(NONE), PRO 6000 MIG 48GB(NONE). 80GB 이상(A100 PCIe Secure $2.09, A100 SXM $2.19, RTX PRO 6000 96GB $2.69 등)은 재고는 있지만 이번 요구량에 비해 3~4배 비싸서 제외했다.

### CUDA 호환성
- `vllm/vllm-openai:v0.32.0`은 CUDA 13 빌드이고 이미지 설정에 `NVIDIA_REQUIRE_CUDA=cuda>=13.0`이 있다. 출처: runpod 플러그인 `runpod-vllm` 스킬 문서(`reference/pod.md`). 이미지 config를 직접 열어 확인하지는 않았다(아래 미확인 항목 참고).
- `get-capacity` 결과, Secure에서 위 4개 GPU의 재고는 **모두 호스트 CUDA 13.2에만** 있다. 13.2 ≥ 13.0이라 호환된다.
- 생성할 때 `gpu.minCudaVersion: "13.0"`을 반드시 넣는다. 넣지 않으면 오래된 드라이버 호스트에 배치되어 컨테이너가 `OCI runtime create failed`로 뜨지 않을 수 있다. (비유: AMI가 요구하는 커널 버전보다 낮은 호스트에 배치되는 것)
- bf16: A40은 Ampere(CC 8.6), RTX PRO 4500·RTX 5090은 Blackwell, L40S는 Ada(CC 8.9)이다. 모두 CC ≥ 8.0이라 bf16을 지원한다.

## 2. 선택

### 1순위: A40 48GB x1, Secure Cloud, EU-SE-1
- **권장 48GB를 만족하는 GPU 중 가장 싸다.** $0.59/h로, 48GB급 다음 후보 L40S($1.09)의 절반 수준이다. 32GB인 RTX PRO 4500($0.72)보다도 싸다.
- 48GB면 `01-plan.md`의 VRAM 계산(가중치 약 16.3~18GiB + 비전 인코더 + KV)에 여유가 커서 `--gpu-memory-utilization`이나 `max-model-len` 때문에 재기동하는 일이 줄어든다. 재기동 1회가 곧 GPU 시간이므로 여유 VRAM이 결국 비용을 줄인다.
- 속도는 L40S보다 느리지만, M1은 동시성 1 스모크 테스트라 처리량이 핵심 지표가 아니다(부하 테스트는 M2).
- **위험: 재고가 LOW이고 EU-SE-1 한 곳뿐이다.** 생성 시 capacity 오류가 나면 바로 차선안으로 넘어간다. 오류가 난 생성 시도는 과금되지 않는다.
- Community A40($0.35)은 재고가 NONE이라 고를 수 없다. Spot은 중간에 회수되면 이미지 pull과 가중치 다운로드를 다시 해야 해서 2시간짜리 실험에는 이득이 작다. 이번에는 검토만 하고 쓰지 않는다.

### 차선안: RTX PRO 4500 32GB x1, Secure Cloud, EU-RO-1
- $0.72/h (≈₩1,044/h). 재고가 MEDIUM이라 4개 후보 중 가장 안정적이고, DC도 3곳이다.
- 32GB는 `01-plan.md`의 최소 요구를 맞춘다. 다만 KV 여유가 줄어 `max-model-len 8192`에서 동시성 여유가 작다. 스모크(동시성 1)에는 충분하다고 본다(ml-engineer 확인 필요).
- 48GB를 꼭 유지해야 한다면 3순위는 L40S Secure $1.09/h이다. 상한 4.5h 기준 ×1.2 ₩8,621로 이것도 ₩30,000보다 한참 낮다.

### 실행 형태: Pod (Serverless 아님)
- 두 모델을 순서대로 교체하고 기동 로그(`Model loading took`, `# GPU blocks`)를 읽어야 한다. Serverless(GPU Lambda + 큐)는 콜드 스타트와 워커 교체 때문에 이런 디버깅에 맞지 않는다.
- 모델 교체 방법: 기본 vLLM 이미지는 컨테이너 1개 = `vllm serve <model>` 1개다. Qwen3.5로 바꿀 때는 `update-pod`로 `args`를 바꾼다. 이렇게 하면 **Pod가 리셋되어 컨테이너 디스크는 지워지지만 `/workspace`(HF 캐시)는 남는다**. 이 작업은 이미 만든 Pod의 설정 변경이므로 실행 직전에 다시 확인을 받는다.
- 이 이미지에는 sshd가 없어 SSH로 접속할 수 없다. 로그는 `stream-pod-logs`로 읽고, 호출과 결과 저장은 로컬에서 OpenAI 호환 HTTP로 한다. 그래서 결과는 처음부터 로컬 `results/`에 쌓인다.

## 3. 스토리지 결정: Pod 볼륨 디스크만 사용 (Network Volume 없음)
| 항목 | 설정 | 근거 |
|---|---|---|
| 컨테이너 디스크 | **30GB** (요청 20GB에서 상향) | runpod-vllm 문서는 "가중치를 볼륨 디스크에 두면 30GB면 충분"하다고 한다. 9.21GB(압축) 이미지가 컨테이너 디스크 한도에 포함되는지 확인하지 못해 안전하게 올렸다. 추가 비용은 10GB × $0.10/GB/월 ≈ 시간당 $0.0014로 무시할 만하다 |
| 볼륨 디스크 `/workspace` | **50GB**, `HF_HOME=/workspace/hf` | 가중치 36.9GB + 캐시 2GB + 여유. 모델 교체나 재기동 때 다시 다운로드하지 않는다 |
| Network Volume | **사용 안 함** | 아래 참고 |

- **Network Volume을 쓰지 않는 이유**
  1. 1순위 DC인 EU-SE-1은 `list-data-centers`에서 `networkVolumeTypes: []`이다. 이곳에는 Network Volume을 만들 수 없다.
  2. Network Volume은 만든 순간부터 지울 때까지 GB 단위로 과금된다. 50GB × 약 $0.07/GB/월 ≈ $3.5/월(≈₩5,075/월, 추정 단가)이고, 단발 실험에서는 보관비만 남는다.
  3. Network Volume은 그 DC 안에서만 붙일 수 있어 GPU 선택 폭도 좁아진다. 재고가 LOW인 지금은 불리하다.
- **M2·M4 재사용**: 가중치는 HF Hub에서 다시 받으면 되므로(약 0.1h, 약 ₩90) 보관할 필요가 없다. M4(LoRA 학습)는 체크포인트를 남겨야 하므로 그때 학습 GPU가 있는 DC에 Network Volume을 두는 것을 다시 검토한다.
- **Stop 상태에서도 디스크 비용이 나간다**: Pod를 Stop하면 GPU 과금은 멈추지만 볼륨 디스크(50GB)는 **실행 중보다 높은 단가**로 계속 과금된다. 약 $0.20/GB/월 기준 50GB면 $0.0137/h, 하루 ≈ $0.33(≈₩477), 한 달이면 ≈ $10(≈₩14,500)이다. 컨테이너 디스크는 Stop 중에 과금되지 않는다. 과금을 완전히 끝내려면 Terminate해야 한다.
  - 디스크 단가($0.10/GB/월 실행 중, $0.20/GB/월 Stop 중, Network Volume $0.07/GB/월)는 MCP 가격 조회 결과에 없다. runpod 플러그인 문서(`runpod-usage/reference/storage.md`)의 "roughly" 값이므로 **추정**이다. Stop 중 단가가 더 높다는 사실 자체는 `lookup-concept pod-billing`의 `pod-billing.stopped-disk-rate` 규칙으로 확인했다.

## 4. 비용 견적
- 시간당 합계(실행 중): GPU $0.59 + 디스크 80GB × $0.10/730 ≈ $0.011 = **$0.601/h (≈₩871/h)**. 디스크 단가는 추정이다.
- 과금 단위: 초 단위(`pod-billing.per-second`).
- 공식: `$/h × h × 1.2(여유) × 1,450` (runpod-ops 절차)

| 시나리오 (1순위 A40 Secure) | 시간 | GPU+디스크 (여유 없음) | ×1.2 여유 포함 | 월 누적 |
|---|---|---|---|---|
| 현실값 | 2.05h | $1.23 ≈ ₩1,786 | **$1.48 ≈ ₩2,144** | 0% → **1.07%** |
| 상한값 (이미 버퍼 0.25h 포함) | 4.5h | $2.70 ≈ ₩3,921 | **$3.25 ≈ ₩4,706** | 0% → **2.35%** |

| 비교 (×1.2 여유 포함) | 현실 2.05h | 상한 4.5h |
|---|---|---|
| 차선안 RTX PRO 4500 Secure ($0.731/h) | ₩2,607 (1.30%) | ₩5,723 (2.86%) |
| L40S Secure ($1.101/h) | ₩3,927 (1.96%) | ₩8,621 (4.31%) |
| RTX 5090 Community ($0.701/h) | ₩2,500 (1.25%) | ₩5,489 (2.74%) |

- **₩30,000 초과 여부: 해당 없음.** 최악(상한 4.5h ×1.2)도 ₩4,706으로 기준의 약 16%다.
- 따로 생길 수 있는 비용: 막혀서 Stop한 채 하루를 넘기면 ₩477/일(추정)이 더 붙는다. 아래 정리 계획으로 막는다.
- 첫 Pod 생성 조건: 계정 잔액이 선택한 구성 1시간 이상(≈$0.60)이어야 한다(`pod-billing.deploy-needs-an-hour`). 잔액은 확인하지 않았다.

## 5. 생성 사양 (승인 후 사용, 지금은 만들지 않음)
```json
{
  "name": "m1-qwen3vl-8b-vllm",
  "image": "vllm/vllm-openai:v0.32.0",
  "args": "<ml-engineer의 serving config에서 생성: Qwen/Qwen3-VL-8B-Instruct + 플래그>",
  "env": { "HF_HOME": "/workspace/hf", "VLLM_API_KEY": "<로컬에서 생성, .env에만 저장>" },
  "disk": 30,
  "mounts": { "persistent": { "size": 50, "path": "/workspace" } },
  "ports": ["8000/http"],
  "gpu": { "id": "NVIDIA A40", "count": 1, "minCudaVersion": "13.0" },
  "cloud": "SECURE",
  "dataCenterIds": ["EU-SE-1"]
}
```
- 차선안은 `gpu.id: "NVIDIA RTX PRO 4500 Blackwell"`, `dataCenterIds: ["EU-RO-1"]`이고 나머지는 같다.
- `VLLM_API_KEY`: Pod의 proxy URL(`https://<pod-id>-8000.proxy.runpod.net`)은 인터넷에 공개되어 있으므로 API 키를 반드시 건다. 키는 로컬에서 생성해 `.env`에만 두고 산출물이나 로그에는 적지 않는다. RunPod 계정 시크릿(`create-secret`)은 쓰지 않고 Pod env로만 넣는다.
- 생성한 뒤에는 `get-pod`로 `desiredStatus=RUNNING`, `cudaVersion ≥ 13.0`, GPU 종류를 확인한다. `stream-pod-logs`에서 `Application startup complete.`가 보이고 `GET /v1/models`가 200을 돌려줘야 "성공"으로 기록한다.

## 6. 정리(teardown) 계획
| 시점 | 조치 | 기준 |
|---|---|---|
| 측정 완료 (`01-plan.md` 8단계) | **즉시 Terminate** (`delete-pod`) | 결과가 로컬 `results/`에 있는지 확인한 직후. `/workspace`의 가중치는 HF에서 다시 받을 수 있어 보관하지 않는다. 삭제 후 `get-pod`/`list-pods`로 사라졌는지 확인 |
| 중간에 막힘, **30분 안에** 재개 가능 | Running 유지 | Stop/Start 왕복 비용(재배치 대기, 같은 호스트에 GPU가 없으면 0 GPU로 뜰 위험)이 30분 GPU 비용(≈₩430)보다 크다 |
| 중간에 막힘, 재개까지 **30분 넘게 ~ 24시간 이내** | **Stop** | GPU 과금이 멈추고 볼륨 50GB만 ≈₩20/h(추정)로 과금된다. 재개할 때 가중치를 다시 받지 않는다. 단, 재시작할 때 같은 호스트에 빈 GPU가 없으면 0 GPU로 뜰 수 있다 |
| 재개가 **24시간 넘게** 걸리거나 불확실 | **Terminate** | 재다운로드 비용(약 0.25h ≈ ₩220)이 하루치 Stop 디스크 비용(≈₩477)보다 싸다 |
| 누적 GPU 시간이 **4.5h 도달** | **그 자리에서 Stop 또는 Terminate**, 원인 기록 | `01-plan.md` 상한 규칙 |

- **유휴 과금 방지책**
  1. RunPod Pod API에는 자동 종료(TTL) 필드가 없다(`describe-tool create-pod` 스키마에서 확인). 그래서 사람이 관리하는 체크포인트를 둔다. 생성 시각을 run-log에 기록하고, 오케스트레이터가 **경과 1.5h / 3.0h / 4.5h**에 경과 시간과 누적 비용을 보고한다. 4.5h에서는 종료를 결정한다.
  2. 실험 세션이 끝날 때(대화 종료 전)는 항상 `list-pods`로 이 실험의 Pod 상태를 확인하고, Terminate/Stop/유지 중 하나를 사용자가 고르게 한다.
  3. 다음 날 첫 세션에서도 `list-pods`로 Stop된 채 남은 Pod가 없는지 확인한다.
  4. 이 실험에서 만들지 않은 리소스는 발견해도 보고만 한다.

## 7. 확인하지 못한 항목
- **디스크 단가**: MCP 가격 조회에 디스크·볼륨 단가가 없어 플러그인 문서의 대략값($0.10 / $0.20 / $0.07 per GB/월)을 썼다. 금액이 작아 결론에는 영향이 없다. 실제 금액은 실행 후 `list-pod-billing`의 `diskAmount`로 확정한다.
- **이미지의 CUDA 요구**: `cuda>=13.0`은 플러그인 문서 값이다. Docker Hub 이미지 config의 `NVIDIA_REQUIRE_CUDA`를 직접 읽지는 않았다. `minCudaVersion: "13.0"`을 걸면 호스트 쪽은 안전하다.
- **압축 해제 이미지 크기와 컨테이너 디스크 포함 여부**: 확인하지 못했다. 그래서 컨테이너 디스크를 30GB로 올렸다. 생성 후 이미지 pull에서 디스크 부족 오류가 나면 run-log에 기록하고 늘린다.
- **L40S·Community RTX 5090의 DC별 재고**: 이번 응답에 `dataCenters`가 없었다. 3순위 이하로 내려갈 때 다시 조회한다.
- **EU-SE-1 `/workspace` 쓰기 속도**: 플러그인 문서의 2026-10-26 live probe에서 EU-SE-1의 `/workspace`는 fuse(네트워크) 마운트, 약 443MB/s였다. 17~19GB 가중치를 받는 데는 충분하지만 HF 다운로드 속도 자체는 실측해야 한다(`01-plan.md`는 0.10h로 가정).
- **계정 잔액**: 조회하지 않았다(생성하려면 1시간치 이상 필요).
- **재고 변동**: A40 재고는 LOW이고 DC가 1곳뿐이다. 승인 후 생성 직전에 `get-capacity`로 다시 조회한다.

---

## GATE-A (오케스트레이터 승인 블록) — 상태: **승인됨 (2026-11-21)**
```
GPU: NVIDIA A40 (48GB) x1 @ EU-SE-1 (Secure)  |  $0.59/h ≈ ₩856/h  (디스크 포함 $0.601/h ≈ ₩871/h)
예상 시간: 2.05h (상한 4.5h)  →  예상 ₩2,144 (상한 ₩4,706, 모두 ×1.2 여유 포함)  (월 누적 0% → 1.07%, 상한 시 2.35%)
정리 계획: 측정 완료 후 결과가 로컬 results/에 있는지 확인한 즉시 Pod Terminate(컨테이너 30GB + 볼륨 50GB 함께 삭제). 막히면 30분 넘게 쉴 때 Stop, 24h 넘게 쉬면 Terminate. 4.5h에 도달하면 강제 종료. Network Volume 없음
```
- 차선안: RTX PRO 4500 Blackwell (32GB) x1 @ EU-RO-1 (Secure), $0.72/h ≈ ₩1,044/h. 예상 ₩2,607 (상한 ₩5,723). A40 생성 시 capacity 오류가 나면 이것으로 전환(승인 범위에 포함할지 사용자 결정)
- ₩30,000 초과: 아니오

## GATE-A 결과 — ✅ 승인 (2026-11-21, 사용자 "진행해주세요")
승인 범위(오케스트레이터 제시 기본값 그대로):
1. A40 재고가 없어 생성에 실패하면 자동 전환하지 않고 사용자에게 다시 묻는다 (대안 L40S 48GB, 상한 ₩8,621).
2. 이번에 만든 Pod 1대에 한해 Qwen3.5 교체용 `update-pod`와 측정 완료 후 Terminate(`delete-pod`)를 사전 승인한다.
3. Pod 생성 시각부터 4.5h가 지나면 Terminate한다. 그전에 ₩4,706을 넘을 것 같으면 멈추고 묻는다. 자리를 비우기 전에는 Stop 또는 Terminate.
4. vLLM API 키는 로컬 `.env`와 Pod 환경변수(`VLLM_API_KEY`)에만 둔다. RunPod 시크릿 등록 안 함. `get-pod` 원문을 기록할 때 키는 가린다. `--api-key` 인자는 쓰지 않는다.
추가: 생성 직전에 계정 잔액과 A40 재고를 다시 조회한다. 0단계(로컬 준비)를 끝낸 뒤에만 Pod를 만든다.

### GATE-A 추가 결정 (2026-11-21, 사용자 선택 "받아들이고 진행")
- vLLM v0.32.0은 `VLLM_API_KEY`를 걸어도 `/invocations`, `/ping`을 키 없이 연다(ml-engineer가 소스로 확인, 03-run-log `## Model`). M1은 합성 문서만 쓰고 시간 과금이라 위험을 받아들인다.
- 대응: Pod 프록시 URL 전체를 산출물·대화에 적지 않는다(`.env`의 `LLM_BASE_URL`에만). 측정이 끝나면 즉시 Terminate.
- 후속: 실서류를 다루기 전(M2 Serverless 계획)에 키 없는 경로 차단 방법을 반드시 정한다.
