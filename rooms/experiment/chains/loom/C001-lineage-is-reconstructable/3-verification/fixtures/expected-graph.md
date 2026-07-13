# 기대 구조 (정답 고정)

> ⚠️ 이 문서는 **도구 작성 전**에 고정되었다 (2026-07-14). 도구의 출력에 맞춰 이 문서를 수정하는 것을 금한다.
> 픽스처 `chains/test-maze/`는 검증용 **가상 체인**이다 — 실제 실험 기록이 아니다.

## 가상 체인 test-maze의 구조

가상의 문제 "미로 탈출"을 푸는 6개 사이클. 분기 1회, 병합 1회 포함.

### 노드 (6)

| id | parent | status |
|---|---|---|
| C001-enter | (없음, root) | closed |
| C002-crossroad | C001-enter | closed |
| C003-left-path | C002-crossroad | closed |
| C004-right-path | C002-crossroad | closed |
| C005-reunion | C003-left-path, C004-right-path | closed |
| C006-exit | C005-reunion | open |

### 구조적 사실 (도구 출력이 일치해야 하는 것)

- **root**: C001-enter 하나
- **분기점**: C002-crossroad (자식: C003-left-path, C004-right-path)
- **병합점**: C005-reunion (부모: C003-left-path, C004-right-path)
- **간선 (6)**: C001→C002, C002→C003, C002→C004, C003→C005, C004→C005, C005→C006
- **토폴로지 순서** (동순위는 id 오름차순으로 결정): C001, C002, C003, C004, C005, C006

### 손으로 그린 기대 그래프 (오래된 것이 위)

```
● C001-enter
● C002-crossroad
├─┐
● │  C003-left-path
│ ●  C004-right-path
├─┘
● C005-reunion   (병합: C003 + C004)
● C006-exit
```

## 판정 규칙

도구 출력의 **구조**(노드 집합, 간선 집합, root/분기/병합 판정, 토폴로지 순서)가
위와 일치하면 통과. 그래프의 시각적 문자 표현은 구조를 왜곡하지 않는 한 자유.
