---
name: runpod-ops
description: RunPod 리소스의 견적 → 승인 → 생성 → 검증 → 정리 → 비용 장부 기록 절차 매뉴얼. Pod, Serverless Endpoint, Network Volume을 만들거나 지우거나 비용을 계산할 때 사용한다. 세부 배포 방법은 runpod 플러그인 스킬에 넘긴다. 모델 선택이나 학습 레시피에는 사용하지 않는다.
---

# runpod-ops

## 어떤 플러그인 스킬에 넘길지
| 상황 | 스킬 |
|---|---|
| vLLM으로 LLM 서빙 (Pod/Serverless) | `runpod:runpod-vllm` |
| 학습용·개발용 Pod (SSH, Jupyter) | `runpod:runpod-pod-deploy` |
| vLLM이 아닌 Serverless 배포 | `runpod:runpod-serverless-deploy` |
| GPU 재고·가격 조회 | `runpod:runpod-discovery` |
| 비용 감사 | `runpod:runpod-cost-audit` |
| 고장 진단 | `runpod:runpod-pod-doctor`, `runpod:runpod-endpoint-ops` |
| 볼륨, 템플릿, 시크릿 | `runpod:runpod-lifecycle-crud` |
| 터미널, 파일 전송, SSH | `runpod:runpodctl` |

## 절차
1. **예산 확인**: `cost-ledger.md`에서 이번 달 누적 ₩을 계산한다. 80% 이상이면 경고를, 100% 이상이면 생성을 금지한다.
2. **조회**: 요구 VRAM 이상인 GPU의 실시간 재고와 가격을 MCP로 읽는다. 후보 2~3개를 비교한다.
3. **선택 기준**: 실험에 충분한 가장 싼 GPU를 고른다. 짧은 실험은 Community Cloud와 Spot을 검토한다. 체크포인트가 필요한 학습은 같은 데이터센터에 Network Volume을 둔다.
4. **견적**: `$/h × 예상 h × 1.2(여유) × 환율(CLAUDE.md 기준)`. 디스크와 볼륨 비용도 함께 계산한다.
5. **🔴 승인 대기**: 승인 전에는 어떤 create 도구도 호출하지 않는다.
6. **생성과 검증**: 생성한 뒤 get으로 상태를 확인한다. 엔드포인트는 실제 요청 1건으로 응답을 확인해야 "성공"으로 기록한다.
7. **기록**: 리소스 ID, 생성 시각, 이미지, GPU를 run-log에 남긴다.
8. **🔴 정리**: 실험이 끝나면 리소스별로 삭제, Stop, 유지 중 하나를 사용자가 고르게 한다. Serverless는 `workersMin=0`인지 확인한다(최소 워커가 1 이상이면 계속 과금된다).
9. **장부**: `cost-ledger.md`에 한 행을 추가한다. 실제 비용은 billing 조회값을 우선 쓰고, 조회가 안 되면 `시간 × 단가 (추정)`으로 적는다.

## 비용 표현 규칙
- 항상 `$x.xx/h (≈ ₩y/h)`처럼 달러와 원화를 함께 쓴다.
- 실험 1건 예상 비용이 ₩30,000을 넘으면 ⚠️로 강조한다.

## 하지 말 것
- 목록 조회에서 발견한 리소스를 "테스트 같아 보인다"는 이유로 지우지 않는다. 보고만 한다.
- 가격을 기억에 의존해 쓰지 않는다. 항상 실시간 조회값을 쓴다.
