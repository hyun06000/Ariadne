# 3. 검증 — git notes로 유령에 지문을 소급 각인 (커밋 불변)

마이그레이션 4단계 중 ③ 소급각인. C017이 세운 읽기호환(유령 무해·가시) 위에서, pre-gil 유령에 v3 지문을 `git notes`로 소급 각인해 v3의 눈에 보이게 만든다 — 유령 수를 줄인다. 핵심: **커밋 SHA를 하나도 안 바꾸며**(append-only 준수).

## 재현

```bash
bash build_case.sh <scratch>     # 혼합 원장 + pre-gil 3개 notes 소급각인
python3 measure.py <scratch>     # 4측정 감사
```

## 산출물

- `retro_imprint.py` — 유령 커밋에 v3 지문을 git notes로 소급 각인. 커밋 불변 자기 집행 + pre-gil/close 구분.
- `rebuild_migrate.py` — C017판 진화. `parse_fingerprint`(trailer·notes 공유 파서)·`_notes_of`·notes fallback 추가.
- `build_case.sh`·`measure.py` — 혼합 원장 구성 + 4측정.
- `build-out.txt`/`measure-out.txt` — 출력(ALL PASS 4/4).

## ⭐ 핵심 — git notes가 append-only를 지키며 소급하는 유일한 수단

**난점:** 닫힌 커밋에 trailer를 넣으려면 `amend`/`rebase`가 필요한데 그건 히스토리 재작성 = append-only 위반(C014 `_assert_append_only` 거부). 마이그레이션이 자기 원리에 자기가 막힌다.

**해법:** `git notes`는 커밋을 안 건드리고 `refs/notes/*`의 별도 ref에 메타를 첨부한다. 커밋 SHA 불변(M1). "깃도 옛 커밋에 서명 없어도 그래프가 읽히듯" notes는 서명처럼 커밋 밖에서 커밋을 가리킨다. notes 본문 = trailer와 동일한 `Key: Value` 라인이라 재구성기가 **같은 파서**(`parse_fingerprint`)로 둘을 읽는다 — 우선순위 trailer > notes.

## ⭐ 측정 중 함정 — rev-list --all 이 notes 커밋을 센다

첫 실행에서 불변 집행식이 오판(FAIL)했다. 원인: **git notes는 `refs/notes/commits`라는 ref를 만드는데 그 ref 자체가 커밋 객체다**(notes는 커밋 트리로 저장). `rev-list --all`이 그 notes 커밋을 새로 세어 "커밋이 늘었다 = 재작성"으로 오판. 진짜 계약은 "원장 커밋(스텝·유령)이 불변인가"이지 "notes 메타 저장소가 안 느나"가 아니다. → `rev-list --exclude=refs/notes/* --all`로 원장만 순회. **notes 각인은 원장 커밋 SHA를 하나도 안 바꾼다**(가설 반증 아니라 계측기 결함 수리).

## 4측정 (ALL PASS)

| 측정 | 확인 | 결과 |
|---|---|---|
| **M1 커밋 불변** | notes 각인 전후 원장 SHA 동일, 유령 커밋 SHA 불변 — git notes가 커밋 안 바꿈(amend/rebase 아님) | PASS |
| **M2 notes=trailer** | 소급된 유령 L1·L2·L3이 스텝 노드로 복원, 지문 값(kind·parent)이 notes와 일치 — 같은 파서로 읽음 | PASS |
| **M3 유령 감소** | 소급 후 `--report` 유령 4→1(close만 남음). pre-gil 3개가 트리에 편입 | PASS |
| **M4 pre-gil/close 구분** | 소급각인이 pre-gil 3개만 notes 부여, close 커밋(이미 v3)은 건너뜀 — notes 없음 | PASS |

## 결론

**ALL PASS → supported.** git notes가 커밋 불변(append-only 준수)을 지키며 유령에 v3 지문을 소급 각인하고, 재구성기가 notes를 trailer와 동등하게 읽어 소급된 유령이 스텝 트리에 편입된다(유령 4→1). pre-gil vs close 구분(C017 이월)도 해결 — close는 이미 v3라 대상 아님. **마이그레이션 4단계 중 ③ 소급각인이 섰다** — 남은 건 ④ 백트래킹 복원과 규모 확장(v2 지문 자동 도출). "커밋을 안 지우고 밖에서 가리키는" 소급이 이 체인의 append-only 헌법과 맞물린다.
