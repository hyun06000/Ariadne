# 3. 가설 검증

## 산출물

```
3-verification/
├── gil/gil.py           # v0.7.0: web 최근 활동 주석 (_last_activity — 깃 무의존 유지)
└── runs/run1-web-tests.txt  # T1~T4
```

검증 대상 본체: [워크플로의 브랜치 렌더](../../../../../../.github/workflows/ariadne-pages.yml), SPEC §6-5·6-6.

## 재현 방법

```bash
python3 rooms/deployment/ariadne-spec/gil.py web -o /tmp/v.html && grep "활동" /tmp/v.html | head -1
python3 rooms/deployment/ariadne-spec/conformance.py --gil "python3 rooms/deployment/ariadne-spec/gil.py"
# 워크플로 추출 실행은 run1 참조 (C007 방식)
```

## 실행 기록

- 2026-07-14. T1 활동 주석 ✓, T2 깃 없는 환경 정상(주석 0건) ✓, T3 신선 클론 워크플로 추출 — Weft 브랜치 페이지까지 렌더 ✓, T4 conformance 26/26 ✓.
- 병행 사건: 병렬 번호 경합(C014) 실물 발생 → 소환자 양보(개명)로 해소, SPEC §6-6에 알려진 문제로 명문화.
