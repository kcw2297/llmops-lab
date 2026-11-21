# artifacts — 산출물 지도

| 파일 | 내용 | 작성자 | 누가 다시 읽나 |
|---|---|---|---|
| `cost-ledger.md` | 월별 GPU 비용 장부 | infra-engineer | orchestrator(Phase 0), reviewer |
| `improvement-log.md` | 하네스 개선 기록 | orchestrator | 하네스를 수정할 때 |
| `learning/roadmap.md` | 마일스톤 진도 | orchestrator | 다음 실험 추천 시 |
| `learning/concepts/*.md` | 개념 노트 누적 | learning-note | 개념 질문 시 먼저 확인 |
| `experiments/{YYYYMMDD}-m{n}-{slug}/` | 실험 1건 | 팀 전체 | 재실행, 이어하기 |

## 실험 폴더 구조
```
00-input.md          요청 원문, 모드
01-plan.md           ml-engineer
02-infra-plan.md     infra-engineer   🔴 승인 게이트 A
03-run-log.md        #Infra #Model #Extraction
04-eval.md           ml-engineer (+ocr-engineer)
05-review.md         reviewer
06-learning-note.md  learning-note
final-report.md      orchestrator      (이 파일이 없으면 미완료 실험)
results/             측정 원본(JSON/CSV)과 로그. 대용량은 results/raw/ (git 제외)
```
부분 재실행할 때 기존 파일은 `*.v1.md`로 보존한다.
