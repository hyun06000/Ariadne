# 3. 가설 검증

설계(2-design.md)의 절차대로 4곳(+예제) 편집 후 5개 검증 항목 실행. gil 2.44.0(이 환경 PATH 없음 → `python3 …/gil.py`). Go는 단일 파일 빌드(`go build -o /tmp/gil-go2 main.go` — go.mod 없이 main.go 단독; 첫 시도의 옛 바이너리 오검을 재빌드로 교정).

## 편집한 4곳(+예제)

| 위치 | 변경 |
|---|---|
| README.ai.md:102 | 단일 `--parent`+lineage-오도 → 병합(`--parent A --parent B` → `parent:[A,B]`) 명시 + lineage는 다른 체인 전용(R3) |
| QUICKSTART.md:86 | 병합 워크드 예제(C036 인용) 블록 추가 + "같은 체인은 언제나 --parent" |
| SPEC.md §3.2 (O-table 뒤) | `--parent` 반복 가능·병합=`[A,B]`·lineage 다른 체인 전용을 규범 절에 연결 |
| gil.py:694 (참조) | 부모 누락 에러 "분기면 여러 번" → "분기·병합이면 여러 번; 같은 체인의 둘째 부모도 --parent" |
| gil.py:4233 (참조) | --lineage help에 "다른 체인 전용; 같은 체인은 --parent" |
| go/main.go:952 (Go parity) | 부모 누락 에러 메시지 동일 정합 |

## 재현 방법

```bash
# V1: 참조 에러 메시지 (비어있지 않은 체인에 부모 없이 open)
#   임시 체인 t/C001-x(closed) 만들고:
python3 rooms/deployment/ariadne-spec/gil.py open t y --author me --root <sandbox>/rooms/experiment/chains 2>&1 | grep "여러 번"
# V2: help
python3 rooms/deployment/ariadne-spec/gil.py help open 2>&1 | grep -i "parent\|lineage"
# V3: 참조 conformance
python3 rooms/deployment/ariadne-spec/conformance.py --gil "python3 $(pwd)/rooms/deployment/ariadne-spec/gil.py"
# V4: Go 빌드 + 메시지 + Go conformance
(cd rooms/deployment/ariadne-spec/go && go build -o /tmp/gil-go2 main.go)
/tmp/gil-go2 open t y --author me --root <sandbox>/rooms/experiment/chains 2>&1 | grep "여러 번"
python3 rooms/deployment/ariadne-spec/conformance.py --gil "/tmp/gil-go2"
# V5: 워크드 예제 존재
grep -l "parent A --parent B\|parent: \[A, B\]\|parent C020-go-web-port --parent C016" \
  README.ai.md rooms/deployment/ariadne-spec/QUICKSTART.md rooms/deployment/ariadne-spec/SPEC.md
```

## 검증 결과

| # | 항목 | 결과 |
|---|---|---|
| V1 | 참조 에러 메시지 실출력 | ✅ `--parent C001-x (분기·병합이면 여러 번; 같은 체인의 둘째 부모도 --parent)` |
| V2 | `gil help open` help | ✅ `--parent … 병합이면 여러 번` / `--lineage … 다른 체인 전용 … 같은 체인은 --parent` |
| V3 | 참조 conformance 무회귀 | ✅ **123/123 "이 구현은 gil이다"** |
| V4 | Go 에러 메시지 + Go conformance | ✅ 메시지 정합 · **105/105 "이 구현은 gil이다"** |
| V5 | 워크드 예제 존재 | ✅ README.ai.md · QUICKSTART.md · SPEC.md 모두 포함 |

## 기각 조건 대조

- 조건1(행동 회귀): 미발생 — 참조 123/123, Go 105/105. 메시지 문면은 계약 아님(§3.1)이라 판정 무영향.
- 조건2(여전히 오도): 미발생 — 워크드 예제(V5)+명시 문안(V1·V2)이 "둘째 같은 체인 조상은?"에 답.
- 조건3(범위 침범): 미발생 — 도구 **행동** 불변(다중부모 원래 지원). 코드 변경은 메시지 2줄(문면)뿐.
- 조건4(버전 표면): 4/5단계 릴리스 시 확인 — 문서 릴리스, `_GIL_VERSION` 범프 필요(README.ai.md는 패키지 밖 별도 커밋, C003).

## 실행 기록

- 일시: 2026-07-20. 환경: darwin, gil 2.44.0(python3 직접 호출), Go 단일파일 빌드.
- 특이사항: V4 첫 시도에서 `/tmp/gil-go`가 이전 빌드본이라 옛 메시지 출력 → `go build`가 go.mod 부재로 실패했는데 grep이 통과해 오검. `main.go` 단독 재빌드(`/tmp/gil-go2`)로 교정 후 정합 확인. **교훈: 바이너리 검증은 재빌드 성공을 먼저 확증하라(C094 "로컬≠CI" 리듬의 바이너리판).**

**5/5 통과. 기각 조건 0건 발동.**
