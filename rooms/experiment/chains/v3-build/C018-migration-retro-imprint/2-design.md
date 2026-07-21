# 2. 설계 — git notes 소급각인 + 재구성기 notes 읽기

## 설계 원칙

- **커밋 불변이 최우선.** append-only(C014 "커밋 불소멸")는 이 체인의 헌법이다. 소급각인은 커밋 SHA를 하나도 안 바꿔야 한다 — `git notes`가 유일하게 이를 만족(amend/rebase는 재작성).
- **notes 형식 = trailer 형식.** notes 본문을 trailer와 동일한 `Key: Value` 라인으로 쓰면, 재구성기가 **같은 파서**로 둘을 읽는다(재구현 0).
- **재구성기가 진실원을 넓힌다.** C017 재구성기는 커밋 trailer만 봤다. C018은 "trailer 있으면 그것, 없으면 notes"로 진실원을 넓힌다 — 소급된 유령이 v3 커밋과 동등해진다.

## git notes 성질 (probe로 확인)

```
git notes add -m "Step-Id: s0\nKind: define\n..." <ghost-sha>
→ 커밋 SHA 불변 (첨부 전후 동일)
→ git log --format="%N" 로 조회 (trailer %(trailers)와 나란히)
→ refs/notes/commits 별도 ref (커밋 객체 안 건드림)
```
이것이 "깃도 옛 커밋에 서명 없어도 그래프 읽히듯"의 도구적 대응 — notes는 서명처럼 커밋 밖에서 커밋을 가리킨다.

## 무엇을 만드나 — 두 조각

### 조각 1 — 소급각인 도구 `retro_imprint.py`
pre-gil 유령 커밋에 v3 지문을 notes로 첨부.

```python
def retro_imprint(repo, commit, trailers):
    """유령 커밋에 v3 지문을 git notes로 소급 각인 — 커밋 불변.
    trailers: [(key, val), ...] → notes 본문 = trailer와 동일한 Key: Value 라인.
    append-only 준수: git notes는 커밋 SHA를 안 바꾼다(refs/notes/* 별도)."""
    before = <커밋 SHA 스냅샷>
    body = "\n".join("%s: %s" % (k, v) for k, v in trailers)
    git notes add -m body <commit>
    after = <커밋 SHA 스냅샷>
    assert before == after   # 커밋 불변 자기 집행 (H1a)
```

- **pre-gil vs close 구분(H1d):** 소급 대상은 **trailer 없는 커밋 중 pre-gil만**. close 커밋도 trailer 없지만 이미 v3 각인 이력(gilv3 close subject)이라 소급 대상 아님. 판별: subject가 `gilv3 `로 시작하면 v3 네이티브(close 포함) → 건너뜀. pre-gil(임의 subject)만 각인.

### 조각 2 — 재구성기 확장 `rebuild_migrate.py` (C017판 진화)
trailer + notes 둘 다 읽기.

```python
_FMT = SEP + "%H" + FSEP + "%N" + FSEP + <trailer 키들>
#             해시      notes    trailer 값들

for rec:
    hash, notes_raw, *trailer_vals = split
    d = trailer 파싱(trailer_vals)
    if not d["Step-Id"] and notes_raw:
        d = notes 파싱(notes_raw)   # ⭐ fallback: trailer 없으면 notes를 지문으로
    sid = d["Step-Id"]
    if not sid:
        ghosts.append(hash)          # 여전히 유령(소급 안 된 것)
        continue
    nodes.append(...)                # trailer든 notes든 동등하게 노드
```
- **notes 파서 = trailer 파서** — 둘 다 `Key: Value` 라인이라 `parse_fingerprint(text)` 하나로 공유.
- **우선순위: trailer > notes** — v3 네이티브 커밋(trailer 있음)은 notes를 안 봄. 소급된 유령(trailer 없고 notes 있음)만 notes로.

## 측정 설계 (build_case + measure)

C017 혼합 원장(pre-gil 3 + v3 트리)을 재사용. pre-gil 3개에 notes 소급 각인.
- **M1 커밋 불변(H1a):** notes 각인 전후 `rev-list --all` + 모든 커밋 SHA 동일.
- **M2 notes=trailer(H1b):** 소급된 pre-gil이 스텝 노드로 복원, 지문 값이 notes와 일치.
- **M3 유령 감소(H1c):** 소급 후 `--report` 유령 수 = 원래(4) − pre-gil(3) = 1(close만).
- **M4 pre-gil/close 구분(H1d):** 소급각인이 pre-gil 3개만 notes 부여, close 커밋 notes 없음.

## 정직한 경계
- 소급각인만(④ 복원·①동결백업 다음).
- pre-gil 지문 값은 **주어진 것으로 가정**(합리적 v3 지문 수동 지정 — 예: pre-gil 3개를 s0 이전 legacy 노드로). v2 cycle.yaml → v3 steps 자동 도출은 규모 확장/다음 카브.
- notes 충돌·병합(여러 머신에서 notes 각인)은 안 다룸 — 단일 원장 소급.
- gilv3.py 명령 불변 — 소급각인은 재구성(읽기) 축 + notes 도구.
