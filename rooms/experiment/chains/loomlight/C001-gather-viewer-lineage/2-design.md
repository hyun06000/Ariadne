# 2. 실험 설계

오직 1-hypothesis.md의 가설 하나 — "lineage 수집이 불변성 위반 없이 성립하고,
gil log가 교차-체인 `⇠` 엣지로 계보를 드러내며, 백로그가 하나로 모인다" — 만을 검증한다.

## 절차

모든 명령은 워크트리 루트에서, 체인 루트는 `rooms/experiment/chains`로 실행한다.
gil 정본: `python3 rooms/deployment/ariadne-spec/gil.py`.

1. **수집의 규칙 준수 검증 (기각조건 1)** — `gil fsck`를 전체 체인에 돌려, loomlight/C001의
   lineage 10건에서 R2(존재하지 않는 참조)·R3(전역 표기/동일 체인 금지) 위반이 없는지 확인한다.
   출력 전문을 `3-verification/fsck.txt`에 저장한다.
2. **교차-체인 엣지 렌더 검증 (기각조건 2)** — `gil log --chain loomlight`를 실행해 C001 행에
   `⇠ lineage: loom/C005-web-viewer, …` 10건이 전부 나타나는지 확인한다. 출력을
   `3-verification/log-loomlight.txt`에 저장하고, 전체 `gil log`(체인 필터 없음)도
   `3-verification/log-all.txt`에 저장해 loom과 loomlight가 한 화면에 조망되는지 본다.
3. **엣지 개수 기계 측정 (기각조건 2 정량화)** — log-loomlight.txt에서 C001 행의 `⇠ lineage:`
   뒤 콤마 구분 참조 개수를 세어 10과 일치하는지 스크립트로 확인한다. 결과를
   `3-verification/edge-count.txt`에 저장한다.
4. **색인 링크 해소 검증 (기각조건 3)** — chain.md의 10개 상대경로 링크가 실제
   `../loom/<id>/5-report.md` 파일로 존재하는지 스크립트로 전수 확인한다. 결과를
   `3-verification/link-resolution.txt`에 저장한다.
5. **주제 일관성 확인 (기각조건 4)** — 10개 사이클의 title을 모아 전부 뷰어(log/web/pages/
   가시성/레이아웃) 주제인지 대조표로 정리한다. `3-verification/theme-coherence.txt`에 저장.
6. 검증 절차 전체를 재현 스크립트 `3-verification/verify.sh`로 남겨, 누구든 그대로 밟을 수 있게 한다.

## 준비물

- gil: `rooms/deployment/ariadne-spec/gil.py` (워크트리 내 정본), Python 3.
- 데이터: loom 체인의 10개 뷰어 사이클(전부 closed, 태그 `cycle/loom/*`), loomlight/C001(open).
- 환경: 격리 워크트리 `agent-aba7943f76c249471`, 브랜치 `loomlight`.

## 측정 방법

| 측정 | 성공 기준 | 기각 |
|---|---|---|
| fsck의 loomlight 관련 위반 수 | 0 | ≥1 (R2/R3) |
| gil log의 C001 `⇠` lineage 참조 수 | = 10 | < 10 |
| chain.md 링크 해소율 | 10/10 | < 10/10 |
| 10 사이클 뷰어 주제 일치 | 10/10 | < 10/10 |

전부 성공이면 verdict `supported`. 일부만 성공이면 `partial`.

## 사용자 컨펌

- 생략 — 사유: 소환자 Clew가 임무 프롬프트에서 설계 골격(open→chain.md→5스텝→검증 산출물을
  3-verification에→백로그 보고)을 이미 지정했다. 이 설계는 그 지시의 절차적 구체화이며 새 결정을
  요구하지 않는다. Clew의 관전은 브랜치 push로 이뤄진다.
- [x] 컨펌 받음 (일자: 2026-07-19, 소환 프롬프트로 사전 위임)
