# 3. 가설 검증

## 재현 방법 (불변 기준 / 가변 확인 — C019 규약)

```bash
S=/tmp/c043
A=/Users/user/Desktop/code/personal/Ariadne/rooms/deployment/ariadne-spec/gil.py  # 절대 경로! (C028 함정)
P="python3 $A"
mkdir -p $S && (cd rooms/deployment/ariadne-spec/go && go build -o $S/gil-go main.go)
G=$S/gil-go
D=rooms/experiment/chains/loom/C043-number-reservation/3-verification

# ① C037의 그 순간을 재현 — 예약 → 선점 → 승격
bash $D/fixture.sh $S/fx "$P"

# ② 계약 준수 (두 구현). 반드시 --gil에 절대 경로.
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$P"      # 62/62 (54 + 예약 8)
python3 rooms/deployment/ariadne-spec/conformance.py --gil "$G"      # 54/54 (예약 미구현 — 정직히 호명됨)

# ③ 변이 시험 — 판정기가 행동을 보는가
python3 $D/mutants.py $S/mut \
  rooms/deployment/ariadne-spec/gil.py rooms/deployment/ariadne-spec/conformance.py   # 5/5 격추

# ④ 교차 판정 — 두 몸, 한 계약
bash $D/cross-check.sh $S/cross "$P" "$G"
```

## 실행 기록

- 실행 일시: 2026-07-15, macOS(darwin 25.2.0), Python 3.9(CommandLineTools), Go 표준 라이브러리 빌드.
- 결과: 참조 **62/62**, Go **54/54**, 변이 **5/5 격추**, 교차 판정 **통과**(web·json 바이트 동일 + Go 정직한 부재).
- 특이사항: `--gil`에 **상대 경로**를 주면 conformance가 샌드박스 cwd에서 gil.py를 못 찾아 web 계열이 무더기로 FAIL한다(C028의 함정 재발). 절대 경로로 교정.

## 관측 1 — C037의 함정이 이제 불가능하다 (조건 1·2, 선점·승격)

`fixture.sh`가 loom/C037의 그 순간을 재현한다: Clew가 Weft에게 번호를 예약하고, 자기가 main에서 사이클을 연다.

```
① Clew가 Weft에게 C002를 예약     → reservations.tsv: "2 weft go-web-port …"
② Clew가 main에서 자기 사이클을 연다 → 열림: loom/C003-clew-work   ← 예약을 건너뛰었다!
③ Weft가 자기 예약을 승격          → 열림: loom/C002-actual-work (예약 승격)
```

| | C037 (수기 규율) | C043 (데이터) |
|---|---|---|
| Clew의 open | **C002 재발급** — Weft의 번호를 뺏음 | **C003** — 예약을 건너뜀 (선점) |
| 해소 | Clew가 손으로 C037로 개명 (양보) | 도구가 자동으로 회피 |
| Weft의 번호 | 소환자에게 빼앗김 | 예약된 C002 그대로 (승격) |

**push 경합이 아니라 예약 마커의 존재만으로** 선점된다 — C016(§6-6)이 못 풀던 "예정된 것의 충돌"이 데이터가 되어 풀렸다.

## 관측 2 — 예약은 사이클이 아니다 (조건 3, 비침습)

예약이 있는 저장소에서 `fsck` 위반 0, `verify` OK, `log` 그래프에 예약 노드 없음. 근거는 코드가 아니라 **파일 위치**다: `load_chain_records`는 `<entry>/cycle.yaml`만 record로 수집하므로, 체인 최상위의 `reservations.tsv`는 fsck·verify·`build_graph`의 눈에 **record로 들어가지 않는다.** "예약은 사이클이 아니다"를 물리적으로 보증한 것 — 코드 곳곳의 예외처리(스텁 사이클 방식)를 피했다.

`log`는 예약을 **별도 섹션**으로 보인다 ("예약됨 (아직 사이클 아님 — 번호 공간 선점)"). 창이 침묵하면 낡은 화면이 되므로(C042), 원장 데이터인 예약을 사람의 창에도 노출한다 — web JSON `reservations` + 표까지.

## 관측 3 — 두 몸, 한 계약: 부분 구현은 합법, 거짓 보고만 불법

예약은 참조 구현만 구현했다(Go는 Weft의 영역). `cross-check.sh`가 계약의 두 축을 대조한다:

- **(A) 무예약 기준선**: 예약을 안 쓰는 저장소에서 두 구현의 web·json이 **바이트 동일**. (예약 키는 있을 때만 JSON에 넣어 파서 계약을 보존했다.) `log` 텍스트는 계약이 아니다(C021 "렌더는 계약이 아니다") — 의미 대조만 한다.
- **(B) 정직한 부재**: Go의 `reserve`·`unreserve` → **exit 3**(미구현 신호). `CONTRACT_COMMANDS`에 예약을 넣어 **HELP-COMPLETE가 Go의 부재를 판정**한다. C036의 교훈 — "판정기가 안 보는 계약은 없는 계약이다"의 예방적 적용: 새 표면을 계약에 적는 같은 커밋에서 판정기에도 적었다.

## 관측 4 — 변이 5/5 격추, 첫 실행부터 (C041 교훈의 예방)

| 변이 | 무력화한 주장 | 격추한 항목 |
|---|---|---|
| m1-ignore-reserved | `_next_number`가 예약 무시 (C037 이전) | OPEN-SKIPS-RESERVED |
| m2-no-promotion | 예약자를 못 알아봄 | OPEN-PROMOTES-OWNER |
| m3-no-owner-required | 예약이 주인을 지어냄 (§3.2 위반) | RESERVE-NEEDS-FOR |
| m4-keep-consumed | 승격 후 예약을 안 지움 | OPEN-PROMOTES-OWNER |
| m5-silent-log | log가 예약을 침묵 | RESERVE-IN-LOG |

각 변이가 **정확히 기대 항목 하나로만** 실패했다(동반 실패 0). C041에서 배운 "심층 방어가 변이를 가린다"를 설계에 미리 넣어 — 각 판정 항목이 다른 방어선이 침묵하는 입력을 쓰게 짜 — 첫 실행부터 5/5.

## 판정

성공 조건 6개(가설) 전부 충족:

1. 선점 ✓ (관측 1, OPEN-SKIPS-RESERVED)
2. 승격 ✓ (관측 1, OPEN-PROMOTES-OWNER)
3. 비침습 ✓ (관측 2, RESERVE-NON-INVASIVE·RESERVE-IN-LOG)
4. 출처 계약 ✓ (RESERVE-NEEDS-FOR — `--for` 필수)
5. 두 구현 ✓ (관측 3 — 참조 구현 + Go의 정직한 부재를 판정기가 호명)
6. 판정기 확장 + 회귀 0 ✓ (54→62, 기존 54 전원 통과)

**채택 (supported).**
