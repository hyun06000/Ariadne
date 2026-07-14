# 3. 가설 검증

## 구성

- `gil-go/main.go` — C014의 `main.go`(739줄, main 병합본을 그대로 복사)를 확장한
  단일 소스 (1088줄). 추가분: 깃 바인딩(`close --git`·`verify`, os/exec로 깃 CLI 호출),
  step 계열(open의 `step: 1`, `step` 명령 --git/--push 포함, fsck R9, close의 `step: 5`
  마감). `open --git/--push`·`web`·`release`는 정직한 미구현 거부(exit 3) 유지.
- `gil-go/gil` — 위 소스의 빌드 산출물 (go1.26.2 darwin/arm64).
- `runs/` — 실행 로그 4본 (아래).

## 재현 방법

이 저장소 루트에서 (요구: Go 1.26+, Python 3.9+, 깃 CLI):

```bash
CY=rooms/experiment/chains/loom/C017-go-git-binding
D=rooms/deployment/ariadne-spec

# run0 (a) 기준선 — C014 소스를 그대로 빌드해 배포본 판정기에 세운다 → 19/26
go build -o /tmp/gil-c014 rooms/experiment/chains/loom/C014-go-binary-open-close/3-verification/gil-go/main.go
python3 $D/conformance.py --gil /tmp/gil-c014
# run0 (b) 판정기 건전성 — 참조 구현 → 26/26
python3 $D/conformance.py --gil "python3 $D/gil.py"

# run1 본 판정 — 이 사이클의 확장 소스 → 24/26 (FAIL은 WEB 2종뿐)
go build -o $CY/3-verification/gil-go/gil $CY/3-verification/gil-go/main.go
python3 $D/conformance.py --gil "$CY/3-verification/gil-go/gil"

# run2 실데이터 교차 검증 — Go verify와 참조 verify의 stdout·stderr·exit 대조
python3 $D/gil.py verify   # vs
$CY/3-verification/gil-go/gil verify
# 변조 시나리오: 닫힌 사이클 파일에 1행 추가 → 양쪽 exit 1 + 동일 보고 → git checkout -- 복구

# run3 샌드박스 실측 — 일회용 깃 저장소에서 커밋 경로 격리·annotated 태그·거부 3종
# (정확한 명령 순서는 runs/run3-sandbox-git.txt 헤더의 절차 그대로)
```

## 실행 기록

- 일자: 2026-07-14. 환경: macOS Darwin arm64, go1.26.2 darwin/arm64,
  Python 3.9.6, git 2.49.0. 판정기·참조 구현은 배포본 v0.8 동봉 그대로
  (`git diff -- rooms/deployment` 0건으로 무수정 확인).
- `runs/run0-baseline.txt` — (a) C014 바이너리 기준선 **19/26** (가설의 예측 적중;
  FAIL: OPEN-CREATE·STEP-OK·FSCK-R9·WEB 2종·GIT-CLOSE·VERIFY-CLEAN).
  (b) 참조 구현 **26/26** (판정기 건전성).
- `runs/run1-conformance-go.txt` — 확장 Go 바이너리 **24/26**. FAIL은
  WEB-SELFCONTAINED·WEB-JSON(범위 밖)뿐. GIT-CLOSE·VERIFY-CLEAN·VERIFY-TAMPER 실질 PASS.
- `runs/run2-crosscheck-verify.txt` — 실데이터(이 저장소, 닫힌 사이클 20개):
  클린·변조 양쪽에서 Go와 참조 구현의 stdout·stderr **바이트 단위 동일**, exit 동일
  (0/0, 1/1). 변조 대상은 `git checkout --`으로 원상 복구 (잔여 변경 0행 확인).
- `runs/run3-sandbox-git.txt` — 샌드박스: ① close --git 커밋이 사이클 경로만 포함
  (무관 파일 더럽힘 미포함), ② 태그는 annotated(`git cat-file -t` = tag) +
  `cycle/<chain>/<id>` 규약, cycle.yaml `step: 5` 마감, ③ 태그 선존재 시 거부 +
  무변화, ④ 비깃 디렉토리에서 거부 + 무변화, ⑤ step --git 커밋도 사이클 경로만 포함.
- 특이사항: run1 최초 로그 생성 시 로그 **헤더**의 소스 줄 수 기입이 셸 경로 오타로
  누락되어 헤더만 정정 재생성했다 (판정 출력 자체는 동일 — 같은 바이너리·같은 판정기).
