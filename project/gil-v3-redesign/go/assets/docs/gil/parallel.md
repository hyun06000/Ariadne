# 나란히 세워 겨룬다 — 경합·채택·벽의 지도

분석이 선택지를 셋 내놓았다. 하나를 골라 직렬로 미는 것은 **고른 근거가 없는** 판단이다 —
나머지 둘이 어땠는지 아무도 모르니까. gil 은 그 셋을 동시에 세우고, 겨루게 하고, 이긴 것을
**선언으로** 채택한다. 이 페이지가 그 문법과 운영이다.

관련: [사고의 생애](lifecycle.md) · [세 위계](concepts.md) · [명령 전체 표면](commands.md)

## 1. 매달린 잎과 경합 갈래는 다르다

같은 부모에서 난 형제 가지 둘이 화면에 똑같이 보여도 뜻은 정반대다.

| | 무엇인가 | gil 의 판정 |
|---|---|---|
| **매달린 잎** | 재분기로 HEAD 가 떠나 **잊혀서** 남은 미종결 가지 | fsck 위반 — 그 자리에 종결을 박아라(`--at`) |
| **경합 갈래** | 비교하려고 **일부러** 열어 둔 형제 가설 | `--competing` 선언이면 위반이 아니다 |

선언이 이 둘을 가른다. 선언 없이 나란히 열면 fsck 가 낙인을 찍고, 그 낙인을 피하려고
세션들은 병렬을 아예 안 쓰게 됐다(실사용 7사이클·스텝 90여 개 동안 병렬 분기 **0회**).

## 2. 경합을 여는 법

경합의 뿌리는 **조상 analyze 또는 define** 이다 — 선택지를 낳은 그 자리.

```
# 분석이 선택지를 셋 내놓았다
gil step tune/c001 --kind analyze --finding "캐시·인덱스·배치 세 축이 후보다" --body-file - <<'EOF'
…근거 전문…
EOF

# 갈래마다 한 번씩 — **모두** --competing 을 단다(첫 가지도 예외가 아니다)
gil step tune/c001 --kind hypothesis --to s4 --competing \
  --inherit "캐시는 아니다(s3 이 반증)" --advances "…" --plan "복합 인덱스 1개" \
  --falsify-to s4 --falsify "인덱스 후에도 스캔이 남으면 틀림" \
  --title "인덱스로 줄인다" --body-file - <<'EOF' …보고서… EOF

gil step tune/c001 --kind hypothesis --to s4 --competing … --title "병렬로 줄인다" …
gil step tune/c001 --kind hypothesis --to s4 --competing … --title "배치로 줄인다" …
```

- `--to` 가 겨루는 자리(뿌리)다. 세 갈래가 **같은 뿌리**를 가리켜야 한 경합이 된다.
- `--falsify` 는 갈래마다 다르게 적어라. 비교는 결국 **무엇이 관측되면 틀리는가**로 한다.
- 첫 가지에 `--competing` 이 없으면 둘째가 거부된다 — 그건 경합이 아니라 미종결이다.

## 3. 갈래는 차례로 판다 (동시에 밟을 수는 없다)

세 갈래를 열어 두는 것과 세 갈래에서 **동시에 일하는** 것은 다르다. git 도 두 브랜치를
한 번에 밟으려면 워크트리가 필요하다. 그러니 순서는 이렇다:

```
gil goto tune/c001/s5     # 갈래 A 의 끝으로 — 여기서 verify 를 붙인다
gil step tune/c001 --kind verify --plan-held --falsify-unmet "p95 121ms" --verdict supported …
gil goto tune/c001/s6     # 갈래 B 로 건너간다
…
```

`gil goto` 가 가지 사이를 오가는 **유일한** 길이다. 죽은 가지 끝에 선 채로 `--to` 를 쓰면
"조상이 아니다"로 거부된다(그건 버그가 아니라 자리를 알려 주는 것이다).

파일 산출물도 그 가지에 산다 — 손으로 `git checkout` 해서 긁어 오지 마라. 그렇게 옮긴
승계는 그래프에 안 남고, 나중에 아무도 그 자산이 어디서 왔는지 모른다.

## 4. 채택 — `gil adopt`

겨루기가 끝나면 하나를 고른다. 고르는 것은 **판단**이므로 근거가 남아야 한다.

```
gil adopt tune/c001/s8 --reason "배치가 p95 를 82ms 로 — 세 축 중 유일하게 기준 통과"
```

- 진 갈래마다 `fail` 벽을 남긴다(승자를 가리키는 `Gil-Lost-To` 와 함께).
- HEAD 를 승자 가지로 옮긴다 — 승자의 산출물도 거기 있다.
- `--over <스텝>…` 로 접을 갈래를 고를 수 있다(생략 = 같은 경합의 미종결 형제 전부).
- `--reason` 은 필수다. 없으면 나중에 아무도 그것이 측정이었는지 취향이었는지 모른다.

**진 갈래는 실패가 아니라 비교의 한쪽이다.** 대조가 없었으면 승자의 수치도 근거가 되지
못한다 — 그래서 gil 은 진 가지를 지우지 않고 벽으로 남긴다.

## 5. 벽의 지도 — 모른다고 적을 수 있다

죽은 잎은 `--to` 로 "여기서 막혔으니 어디로 되돌아가라"를 적는다(벽의 지도). 두 가지를
알아 두면 기록이 거짓말하지 않는다:

- **아직 모르면 `--to pending`.** 보수적 기본값을 적어 두면 그게 나중에 지도-행동
  불일치로 보인다. 다음 재분기(또는 사람의 판정)가 그 자리를 확정한다.
- **지도와 다른 자리에서 갈라지려면 `--despite <왜>`.** 지도를 고치는 것도 정당하다 —
  다만 이유가 남는다. 그 순간 옛 지도는 **갱신된 것**이 되고, 뷰어는 그 선을 회색 점선으로
  강등해 "지도 갱신됨 → s4 (s6, despite)" 라고 적는다.

`gil context` 도 같은 사실을 말한다(`⌖ 지도 미정` · `⟲ 이 지도는 s6 이 갱신했다`).
두 자리가 갈리면 사람은 어느 쪽이 사실인지 알 수 없으므로, 화면과 CLI 는 같은 것을 본다.

## 6. 화면에서 보기

뷰어의 **스텝 그래프**에서 사이클을 열면:

- 경합 갈래에 `⚖ 경합`(진 갈래는 `⚖ 졌음`) 표식이 붙는다.
- 그래프 아래에 **형제 비교 카드**가 선다 — 갈래·가설·반증조건·고정한 설계·지금 상태를
  한 줄씩 나란히. 상태는 추측이 아니라 그 갈래의 잎이 말한 것이다(채택됨 / 졌음 / 접힘 /
  겨루는 중).
- 갱신된 벽의 지도는 회색 점선, `⌖ 지도 미정`·`⟲ 지도 벗어남`도 그 자리에 뜬다.

`gil handoff` 는 텍스트로 같은 것을 센다(`⚖ 경합 중인 형제 가설 N개(미결)`).

## 7. 토너먼트 한 판 — 전체 흐름

```
gil open tune/c001 --author clew --purpose "p95 낮추기" --fits "…" --body-file - …
gil step tune/c001 --kind hypothesis --falsify-to s1 --plan … --title "캐시가 원인" …
gil step tune/c001 --kind verify --plan-held --falsify-met "캐시 무관" --verdict refuted …
gil step tune/c001 --kind analyze --finding "캐시·인덱스·배치 세 축이 후보다" …

gil step tune/c001 --kind hypothesis --to s4 --competing … --title "인덱스로 줄인다"   # s5
gil step tune/c001 --kind hypothesis --to s4 --competing … --title "병렬로 줄인다"     # s6
gil step tune/c001 --kind hypothesis --to s4 --competing … --title "배치로 줄인다"     # s7

gil goto tune/c001/s5 && gil step tune/c001 --kind verify …    # 갈래마다 재 본다
gil goto tune/c001/s6 && gil step tune/c001 --kind verify …
gil goto tune/c001/s7 && gil step tune/c001 --kind verify …

gil adopt tune/c001/s8 --reason "배치가 p95 82ms — 유일하게 기준 통과"
gil step tune/c001 --kind analyze --finding "배치 32 가 p95 를 82ms 로 낮춘다" …
gil step tune/c001 --kind success --toward … --next-design … --title "배치로 달성"
gil close tune/c001 --verdict supported
```

## 8. 체인·사이클 층위의 병렬

- **형제 사이클**: 한 체인에서 사이클을 동시에 열지는 못한다(원리적으로 — 워크트리가
  필요하다). 갈래는 차례로 내고, `gil open --parent <형제의 부모>` 로 계보를 선언한다.
- **동시 트랙 체인**: 열린 체인이 있는데 나란히 굴리는 것이면 `gil chain <이름>
  --parallel-with <그 체인>` 으로 **선언**한다. 선언 없이 얹히면 fsck 가 거짓 계승으로 읽는다.
- 얹혔지만 계승이 아닌 것을 사후에 바로잡으려면 `gil reconcile <chain> --as parallel
  --with <체인> --reason <왜>`.
