# 3. 가설 검증 — Go 이식

## 재현
```bash
go build -o /tmp/gil-go rooms/deployment/ariadne-spec/go/main.go
python3 rooms/deployment/ariadne-spec/conformance.py --gil /tmp/gil-go        # Go
python3 rooms/deployment/ariadne-spec/conformance.py --gil /tmp/gilbin/gil    # 참조(무회귀)
```

## 결과 (점진)
| 이식 | 항목 | Go 전 | Go 후 |
|---|---|---|---|
| ① C085 refresh | WEB-REFRESH-DEFAULT | 100/104 | 101/104 |
| ② C090 open/step | OPEN-CREATE·STEP-OK·STEP-SCOPE·STEP-GATE | 101 | 103/104 |
| ③ C088 md렌더 | WEB-MD-RENDER | 103 | **104/104** |

- **Go 104/104 "이 구현은 gil이다"** · 참조 **122/122** 무회귀.
- 보너스: Go 헤더에 gil 버전(C087)도 함께 이식(참조와 동형).

## 코드 변경 (go/main.go)
- refresh: `webDefaultRefresh` 상수, web 파싱 미지정→5, bake `>=0`(0 기록), bakeMeta `*int`(nil→5).
- open/step: `stepScaffold`·`contentSubstantive`(C092판)·`stepWritten`·`createStepFile` 헬퍼. open 1스텝, step 전이 가드+생성+안내.
- md렌더: webAppJS에 renderMd/inlineMd/safeUrl/stepHtml + 토글 핸들러, 헤더 mdtoggle 버튼+gilver, CSS.

## 밟은 것 (Go 특유)
- JS 백틱·펜스(```)·${} 를 Go raw string(백틱)에 넣으려 `` ` + "`" + ` `` 로 이스케이프.
- `*int`로 "키 부재(nil) vs 명시 0"을 구별(Go zero value 0이 둘을 못 가름 → C085 계약 재현).

## 미이식 (정직)
- C088 이미지 base64 임베드(Go collectCycleDocs) — conformance 정적 검사가 안 잡음. 실제 이미지 표시 동형은 후속.
