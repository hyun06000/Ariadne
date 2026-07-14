# 3. 가설 검증

## 구성

- `gil-go/main.go` — C017의 `main.go`(1088줄)를 그대로 복사해 확장한 단일 소스
  (1737줄). 추가분: **web 계열** — `layoutColumns`(레이아웃)·`renderSVG`·
  `renderTables`·`renderWebPage`(문자열 조립)·`webJSONPayload`(gil-data JSON)·
  `stepBadge`(●●●○○ n/5)·`lastActivity`/`agoStr`(깃 가용 시 최근 활동, 비깃이면
  null — web은 깃 무의존)·`htmlEscape`/`jsonStr`(파이썬 `html.escape`·
  `json.dumps(ensure_ascii=False)`의 문자면 재현). `release`·`open --git`은
  정직한 미구현 거부(exit 3) 유지.
- `gil-go/gil` — 위 소스의 빌드 산출물 (go1.26.2 darwin/arm64).
- `runs/` — 실행 로그 4본 (아래).

## 재현 방법

이 저장소 루트에서 (요구: Go 1.26+, Python 3.9+, 깃 CLI).
**주의**: conformance의 `--gil`에는 **절대 경로**를 줄 것 — 판정기는 자기가 만든
샌드박스를 cwd로 구현을 실행하므로 상대 경로는 끊어진다 (실행 기록의 특이사항).

### 불변 기준 (픽스처 대상 — 시점 무관)

```bash
CY=$PWD/rooms/experiment/chains/loom/C020-go-web-port
D=$PWD/rooms/deployment/ariadne-spec

# run0 (a) 기준선 — C017 소스를 그대로 빌드해 배포본 판정기에 세운다 → 24/26 (FAIL: WEB 2종)
go build -o /tmp/gil-c017 rooms/experiment/chains/loom/C017-go-git-binding/3-verification/gil-go/main.go
python3 $D/conformance.py --gil /tmp/gil-c017
# run0 (b) 판정기 건전성 — 참조 구현 → 26/26
python3 $D/conformance.py --gil "python3 $D/gil.py"

# run1 본 판정 — 이 사이클의 확장 소스 → 26/26
go build -o $CY/3-verification/gil-go/gil $CY/3-verification/gil-go/main.go
python3 $D/conformance.py --gil "$CY/3-verification/gil-go/gil"

# run3 음성 대조 + 픽스처 대조 — 픽스처 원문은 runs/run3-negative-fixture.txt 하단 그대로
# (a) 깨진 체인: 두 구현 모두 exit 1 + 동일 stderr + 출력 파일 무생성
# (b) 비깃 디렉토리의 분기·병합·lineage 픽스처: 두 구현 exit 0 + HTML 바이트 단위 동일
#     + last_activity 전부 null + 스텝 배지·특수문자 이스케이프·lineage 점선(mx 소수) 확인
```

### 가변 확인 (실데이터 대상 — 저장소 성장에 따라 달라짐)

```bash
# run2 — 같은 분(minute) 안에 연속 실행해 ago 경계를 통제하고 상호 일치를 판정한다
python3 $D/gil.py web -o /tmp/ref.html --title "Ariadne — 사이클 체인"
$CY/3-verification/gil-go/gil web -o /tmp/go.html --title "Ariadne — 사이클 체인"
diff /tmp/ref.html /tmp/go.html   # 및 gil-data JSON 추출·파싱·심층 비교 (로그의 인라인 스크립트)
```

## 실행 기록

- 일자: 2026-07-14. 환경: macOS Darwin arm64, go1.26.2 darwin/arm64, Python 3.9.6,
  git 2.49.0. 판정기·참조 구현은 배포본 v0.9.1 동봉 그대로
  (`git diff -- rooms/deployment` 0건, 각 로그 헤더에 기록).
- `runs/run0-baseline.txt` — (a) C017 바이너리 **24/26** (FAIL: WEB-SELFCONTAINED·
  WEB-JSON — 가설의 예측 적중). (b) 참조 구현 **26/26** (판정기 건전성, 기각 조건 4 해제).
- `runs/run1-conformance-go.txt` — 확장 Go 바이너리 **26/26 — "이 구현은 gil이다"**.
  퇴행 0 (기각 조건 1·2 해제).
- `runs/run2-crosscheck-web.txt` — 실데이터(이 저장소, 체인 3개·사이클 24개·열린
  사이클 1개): gil-data JSON **파싱 후 심층 비교 일치 + 원문 문자열 동일**(7271바이트,
  기각 조건 3 해제), HTML 전문 **바이트 단위 동일**(36173바이트 — 지향 상한 도달),
  실산출물 외부 리소스 0건.
- `runs/run3-negative-fixture.txt` — (a) 깨진 체인: 양쪽 exit 1, **stderr 바이트
  단위 동일**, 출력 파일 무생성. (b) 비깃 분기·병합·lineage 픽스처(체인 2개,
  병합 parents 2개, 레인 횡단 lineage, 특수문자 제목): 양쪽 exit 0, HTML **바이트
  단위 동일**(8500바이트), last_activity 전부 null, 스텝 배지(3/5·2/5)·HTML
  이스케이프·lineage 점선의 반픽셀(mx `.0`/`.5`) 표기 확인.
- 특이사항: run0 최초 실행에서 `--gil`에 상대 경로를 주어 참조 구현이 16/26으로
  나왔다 — 판정기 결함이 아니라 호출 규약(샌드박스 cwd) 미준수. 절대 경로로
  재실행해 26/26. 이 함정은 위 재현 방법에 명시했다.
