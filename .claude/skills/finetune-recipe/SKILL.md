---
name: finetune-recipe
description: LoRA/QLoRA 파인튜닝 레시피 매뉴얼. 데이터셋 준비, 학습 프레임워크 선택(TRL/Unsloth/Axolotl), 하이퍼파라미터, 체크포인트 저장, 어댑터 서빙 연결이 필요할 때 사용한다. 풀 파인튜닝이나 사전학습 같은 대규모 학습은 예산 밖이므로 먼저 경고한다.
---

# finetune-recipe

## 개념 (백엔드 비유)
- **풀 파인튜닝**: 전체 코드베이스를 다시 컴파일하는 것과 같다. 비싸다.
- **LoRA**: 원본은 그대로 두고 작은 패치(어댑터)만 학습한다. 플러그인 방식에 가깝다. 패치 크기는 수십 MB 수준이다.
- **QLoRA**: 원본을 4bit로 압축해서 올리고 LoRA를 학습한다. 더 작은 GPU에서도 돌아간다.

## 절차
1. **목적 정의**: 무엇을 바꾸고 싶은지 정한다(말투나 형식, 도메인 지식, tool call 형식). 지식 주입이 목적이면 RAG가 더 나을 수 있다는 점을 먼저 짚는다.
2. **데이터**: chat 형식 JSONL(`{"messages":[...]}`)을 쓴다. 처음에는 500~2,000개면 충분하다. train/eval을 9:1로 나눈다. 라이선스를 확인한다.
3. **프레임워크**: 처음에는 Unsloth나 TRL `SFTTrainer`를 쓴다. 설정 파일 위주로 반복하려면 Axolotl을 쓴다.
4. **초기 하이퍼파라미터**: r=16, alpha=32, dropout=0.05, lr=2e-4, epoch=1~3, 4bit(QLoRA), max_seq_len=2048. target_modules는 attention과 MLP의 proj 레이어.
5. **인프라 요청**: infra-engineer에게 Pod와 **같은 데이터센터의 Network Volume**을 요청한다. 체크포인트와 HF 캐시는 볼륨에 저장한다.
6. **실행**: 처음에는 `max_steps=20`으로 스모크 테스트를 한다. loss가 떨어지는지 확인한 뒤 본 학습을 한다.
7. **기록**: train loss와 eval loss 곡선(로그 또는 이미지), 학습 시간, 최종 어댑터 경로를 남긴다.
8. **연결**: vLLM `--enable-lora`로 베이스 모델과 어댑터를 함께 서빙한다. 그다음 `model-eval`로 베이스 모델과 비교한다.

## 품질 체크
- eval loss가 오르기 시작하면 과적합 신호다. 해당 지점을 노트에 남긴다.
- 학습 전과 후를 같은 프롬프트 세트로 비교했는가?
- 🔴 HF Hub push는 사람 승인을 받는다(private repo가 기본값).

## 코드 위치
- 레시피(재사용 코드): `finetune/recipes/{method}/` (`train.py`, `requirements.txt`). 컨테이너에서 실행하므로 uv workspace 멤버가 아니다.
- 실험 설정: `finetune/configs/{model}-{method}-{dataset}.yaml`. 새 실험은 config만 추가한다.
- 데이터: `finetune/datasets/{name}-v{n}/`에는 데이터 카드(README: 출처, 라이선스, 형식, 건수)와 작은 샘플만 둔다. 원본은 `.data/` 또는 Network Volume에 둔다(git 제외).
- 학습 로그와 loss 기록: `artifacts/experiments/{id}/results/`
