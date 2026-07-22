# 2. 실험 설계

## 설계 — load_chain_records v3 분기가 계보 trailer를 읽어 record 채움

C040의 v3 record는 `parents=[]`·author 없음이었다. 여기에 그 사이클 커밋의
Cycle-Parent·Cycle-Author trailer를 git으로 읽어 채운다. build_graph는 record의
parents를 쓰므로, 채우면 log 그래프가 v3 계보를 그린다.

## 절차

1. **헬퍼 `_v3_lineage(entry_dir)`**: `git -C <entry_dir> log --format='%(trailers:...)'
   -- steps.yaml`로 그 사이클 루트 커밋의 Cycle-Parent(여러) ·Cycle-Author를 읽어
   `(parents_list, author_or_None)` 반환. git 아니거나 실패면 `([], None)` — 안정적 폴백.
2. **load_chain_records v3 분기가 헬퍼 호출**: `parents`·`author`를 채움. 나머지 record
   구조 불변. cycle.yaml 없는 v3만 대상(v2 경로 무영향).
3. **배포판 gil.py 적용**, 검증.

## 준비물

- 배포판 gil.py(`load_chain_records`), conformance.py(무회귀).
- Python 3.9, git. `git -C <dir> log --format='%(trailers:key=Cycle-Parent)'`.

## 측정 방법

- **M1 log v3 계보 표현**: C001-root·C002-child(--parent C001-root) v3 사이클 →
  `gil log` 계보 `C002-child ← C001-root`(root 아님). 기준=부모 연결.
- **M2 그래프 노드**: render_graph가 child를 root 밑에 그림(들여쓰기·연결). 기준=계보 반영.
- **M3 author 표시**: v3 record에 author 채워짐(log summarize/graph가 쓰면 표시).
  기준=author 복원.
- **M4 비-git 폴백**: git 아닌 곳에서 v3 사이클 로딩이 crash 없이 (root)로. 기준=무crash.
- **M5 v2 무회귀 + fsck + conformance**: 실저장소 fsck 위반 0, 게이트 상속 121/121.
  기준=불변.

## 사용자 컨펌

- 상현님 완전 자율 위임. C041 이월(계보 표현)의 자연 후속, C040 v3 분기 확장.
- [x] 컨펌 받음 (일자: 2026-07-23, 완전 자율 위임)
