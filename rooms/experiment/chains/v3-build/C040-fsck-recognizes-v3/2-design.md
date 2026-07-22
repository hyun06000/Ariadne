# 2. 실험 설계

## 설계 결정 — 길3(v3 전용 최소 검사) + records 형태 통일 (자율 판단)

상현님 완전 자율 위임("묻지도 멈추지도 말고"). 세 길 중 **길3**을 판단으로 택함:

- **길1(얇은 cycle.yaml) 기각**: migrate가 "cycle.yaml 불변"을 계약(C018)으로 삼는데
  v3가 새 cycle.yaml을 쓰면 충돌. steps.yaml 진실원 철학과 이중화(동기화 부담).
- **길2(steps.yaml 직접수집·전면 R매핑) 기각**: fsck R규칙 전체를 v3 층으로 재매핑 →
  거짓위반 위험(기각조건 2).
- **길3 채택**: v2 R규칙 무손상 + v3에 맞는 검사만. C038 "안전 계약은 검사 경로만
  v3화"의 연장.

**핵심 이득 실측 — 번호 중복 검사가 이미 R1에 있다**(gil.py 495: 같은 번호 여러 cid →
위반). 그래서 v3 사이클을 records로 편입만 하면 **C039의 병렬 번호 충돌이 자동으로
잡힌다**(기각조건 3 해소). 이것이 "records 형태 통일" 접근의 결정적 근거.

## 절차

1. **`load_chain_records`가 v3 사이클도 수집**: `<entry>/cycle.yaml`이 없고
   `<entry>/steps.yaml`이 있으면 최소 record 생성 — `id=entry`, `chain=<체인명 주입>`,
   `_dir=entry`, `_v3=True`, `parents=[]`, `lineage_list=[]`. status/verdict/step 미설정
   (None) → cycle.yaml 필드 의존 R규칙(R8·R9·R10·R11·R13·R15)이 조건부라 자연 스킵.
   단 `load_chain_records`는 chain명을 모르므로 chain 필드는 호출측(_scan_chains)이 알거나,
   R4 검사를 v3에서 건너뛴다. → **v3 record는 chain을 entry 부모 디렉토리에서 못 얻으니
   R4는 `_v3`면 스킵**(chain 필드 자체가 없음).
2. **v3 전용 최소 검사 추가**(fsck_collect): `_v3` record에 대해 (a) `steps.yaml`에 루트
   define(parent:null, kind:define) 존재, (b) R1(id 형식)·R5(dir=id)·번호 중복은 공용
   적용. 루트 define 부재면 새 위반 `V3-ROOT`.
3. **cycle.yaml 필드 의존 R규칙이 v3 record에서 거짓위반 안 내는지 확인**: status None →
   R8 스킵, verdict None → R10 스킵 등. 안 되는 규칙은 `if not r.get("_v3")`로 가드.
4. **배포판 gil.py 적용**, 검증.

## 준비물

- 배포판 gil.py(`load_chain_records`·`fsck_collect`·`_scan_chains`), conformance.py(무회귀).
- Python 3.9, git. v3 사이클 생성은 `gil v3 open <dir>`.

## 측정 방법

- **M1 v3 인식**: v3 네이티브 사이클 1개 있는 저장소 `fsck` → "사이클 **1개**"(0개 아님).
  기준=v3 사이클이 카운트됨.
- **M2 번호 중복 검출**: 같은 번호 v3 사이클 둘(C039 병렬 재현) → fsck R1 번호 중복 위반.
  기준=위반 검출(기각조건 3 해소).
- **M3 v3 거짓위반 0**: 정상 v3 사이클(루트 define 있음)에 R8·R9·R10 거짓위반 안 남.
  기준=정상 v3는 위반 0.
- **M4 루트 define 검사**: 루트 define 없는 훼손 v3 → V3-ROOT 위반. 기준=검출.
- **M5 v2 무회귀**: 기존 v2 사이클 인식·R규칙 불변. 기준=기존 fsck 결과 동일.
- **M6 conformance**: 게이트 상속 121/121. 기준=불변.

## 사용자 컨펌

- 상현님 완전 자율 위임("앞으로도 물어보지 말고 너의 판단으로 위임, 묻지도 멈추지도
  말고 계속"). 길3 선택은 자율 판단(migrate 계약 정합·거짓위반 회피 근거).
- [x] 컨펌 받음 (일자: 2026-07-23, 완전 자율 위임)
