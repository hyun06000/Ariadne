# GIL Storage Model v0.1

> 이 문서는 GIL의 논리 Graph와 Artifact 세계를 로컬 파일 시스템에 보존하는 **물리 저장
> 계약**을 정의한다.

Artifact의 의미, Snapshot 선택과 restore 목표는 `GIL Artifact Model v0.1`이 정한다. 이
문서는 그 의미를 어떤 파일과 객체로 내구성 있게 보존하는지만 맡는다. 내부 저장 주소는 공개
`SnapshotRef`가 아니며 사용자와 Agent의 공개 문법에 노출하지 않는다.

---

## 1. 범위

이 문서가 소유하는 것:

- `.gil` 내부의 format 4 배치
- canonical manifest binary 형식
- blob과 manifest 객체의 내용 주소와 append-only 확정
- `state.yaml`과 객체 저장 순서
- 프로젝트 단위 잠금과 임시 객체 회수
- load 시 구조·객체·참조 검증 순서

이 문서가 소유하지 않는 것:

- 어떤 Step이 세계를 바꿀 권한을 갖는가
- 어떤 Snapshot을 현재 세계나 restore 목표로 고르는가
- Cycle revisit, merge와 Dataset의 의미
- 인간에게 보이는 story, context와 receipt의 표현

---

## 2. 프로젝트 저장 배치

```text
.gil/
├─ state.yaml
├─ project.lock
├─ artifacts/
│  ├─ blobs/sha256/<앞 두 글자>/<나머지>
│  ├─ manifests/sha256/<앞 두 글자>/<나머지>
│  └─ tmp/
└─ restore/
   ├─ preparing-<pid>-<표>/
   ├─ active/
   │  ├─ PLAN
   │  ├─ backup/<불투명한 서수>
   │  └─ COMMITTED
   └─ cleanup-<pid>-<표>/
```

- `state.yaml`은 World Graph, Existence/Journey와 Snapshot registry를 함께 담는 현재 공개 저장
  형식이다.
- `project.lock`의 존재는 잠김을 뜻하지 않는다. 운영체제 advisory lock의 대상일 뿐이다.
- `artifacts` 아래의 hash 경로는 내부 주소다. Report와 오류 메시지는 `snapshot:A1` 같은 공개
  참조를 사용한다.
- 사용자 Artifact 관측은 프로젝트 루트의 `.gil/` 하나를 제외한다.

---

## 3. format 4의 Snapshot registry

format 4의 `state.yaml`은 다음 논리 구조를 지닌다.

```yaml
format: 4
artifacts:
  next_snapshot_id: 2
  snapshots:
    - id: A1
      manifest:
        algorithm: sha256
        digest: <소문자 canonical hex>
```

불변식:

- registry 안 객체 자신의 `id`는 bare `A1`이고, Graph에서 가리킬 때는 `snapshot:A1`이다.
- `A0`는 없으며 ID는 오름차순이고 빈틈이 없다.
- 한 manifest 세계에는 하나의 `SnapshotRef`만 존재한다.
- 같은 세계를 다시 확정하면 기존 참조를 다시 가리키고 `next_snapshot_id`를 늘리지 않는다.
- 열린 Cycle은 실재하는 Entry만, 닫힌 Cycle은 실재하는 Entry와 Exit를 가진다.
- 닫힌 Verify만 실재하는 `snapshot_ref`를 가진다.
- World Current Snapshot은 저장하지 않고 Graph에서 유도한다.

format 3에는 관측된 Artifact 세계가 없으므로 자동 변환하지 않는다. 파일을 수정하거나
삭제하지 않고 앞 형식임을 알려 거절한다.

### 3.1 M4의 `pending_cycle_revisit`은 format 4의 선택적 전이 상태다

M4 Cycle-level revisit은 `StoredCycles`에 다음 선택적 필드를 더한다.

```yaml
cycles:
  pending_cycle_revisit: 3    # 없거나 null이면 pending 없음
```

이 필드는 새 영구 객체의 schema가 아니라 두 명령 사이의 **일시적인 Graph 전이 상태**다.
따라서 format 번호를 올리지 않고 format 4 안에 둔다.

- 기존 format 4 파일에 필드가 없으면 `null`과 같은 뜻으로 읽는다.
- pending이 없을 때는 필드를 저장하지 않는다.
- pending이 있을 때 값은 Graph 안의 숫자 Cycle ID 하나다. `parent`·`current`와 같은 저장
  계층 표현이며, 공개 Report와 오류 메시지에서는
  같은 대상을 typed `cycle:C3`로 표현한다.
- 값이 가리키는 실패 Cycle, 현재 Cycle, 그 실패 Cycle의 Report가 선언한 revisit 대상 사이의
  구조적 관계를 load 때 다시 검사한다.
- 다음 `gil open <kind>`가 새 Cycle의 `revisit_from`으로 값을 옮긴 뒤 pending 필드를 제거한다.
- 모르는 다른 필드는 계속 거절한다. 이 선택적 필드 하나가 format 4 전체를 확장 가능한
  임의 mapping으로 바꾸지는 않는다.

새 바이너리는 이 필드가 없는 기존 format 4를 근거 손실 없이 읽을 수 있다. 앞 바이너리가
pending 필드를 모른다고 거절하는 것은 안전한 동작이다. pending 상태를 무시하고 다른 Graph
전이를 실행하는 것보다 명시적 거절이 낫다.

---

## 4. canonical manifest binary

manifest는 구현체의 native 자료 구조를 그대로 직렬화하지 않는다. 모든 플랫폼이 같은
바이트를 만들도록 다음 순서와 폭을 고정한다.

```text
header
  magic       8 bytes   "GILMANIF"
  format      u32       big-endian, 현재 1
  algorithm   u8        현재 1 = SHA-256
  entry_count u64       big-endian

entry (entry_count번)
  path_len    u32       big-endian, 1..4096
  path        path_len  UTF-8 bytes
  digest      32 bytes  파일 원본 바이트의 SHA-256
```

- entry는 경로 UTF-8 바이트 오름차순이다.
- 중복 경로와 비canonical 순서는 정렬해 고치지 않고 거절한다.
- decoder는 길이 필드를 신뢰해 무제한 메모리를 먼저 할당하지 않는다.
- trailing bytes, 모르는 format과 algorithm은 거절한다.
- manifest 주소는 canonical manifest 전체 바이트의 SHA-256이다.

---

## 5. 객체 확정

blob은 파일의 원본 바이트 그대로이며 헤더, 압축, 암호화와 줄바꿈 변환을 하지 않는다.

blob과 manifest는 같은 확정 절차를 지난다.

1. `tmp/`의 이 명령 전용 이름에 스트리밍하며 digest를 계산한다.
2. 파일을 flush하고 `fsync`한다.
3. digest로 최종 주소를 정하고 부모 디렉터리를 만든다.
4. 임시 파일을 최종 주소에 hard link로 건다.
5. 이미 있으면 기존 객체를 건드리지 않고 내용을 다시 확인한다.
6. 확정 뒤 최종 객체를 다시 열어 주소와 내용을 검증한다.
7. 임시 이름을 회수하고 가능한 플랫폼에서 부모 디렉터리를 `fsync`한다.

최종 주소가 이미 있을 때 `rename`으로 덮어쓰지 않는다. hard link를 지원하지 않는 자리에서
보장이 약한 방법으로 물러서지 않고 명시적으로 거절한다. 같은 바이트는 같은 객체 하나를
공유하며, 아직 참조되지 않은 올바른 객체가 남아 있는 것은 손상이 아니다.

---

## 6. 논리 상태 확정 순서

객체는 `state.yaml`보다 먼저 내구성 있게 확정한다.

```text
관측과 Report 검증
→ blob과 manifest 객체 확정
→ Snapshot registry intern
→ Graph·Will·Journey의 새 논리 상태 구성
→ 새 state.yaml을 임시 파일에 쓰고 flush·fsync
→ rename으로 state.yaml 교체
→ 가능한 플랫폼에서 .gil 디렉터리 fsync
```

객체가 먼저 남고 상태 저장이 실패하면 그 객체는 미참조 객체일 뿐이다. 반대로 state가 아직
확정되지 않은 객체를 가리키는 순서는 허용하지 않는다.

---

## 7. 프로젝트 잠금

모든 프로젝트 상태 접근 명령은 상태를 읽기 전에 `.gil/project.lock`의 exclusive advisory
lock을 한 번 획득하고 명령이 끝날 때까지 보유한다.

- 경쟁하면 기다리거나 빼앗지 않고 즉시 거절한다.
- 정상 종료, 오류, panic과 프로세스 종료에서는 운영체제가 lock을 해제한다.
- lock 파일의 존재나 기록된 PID로 잠김을 추측하지 않는다.
- `--version`과 프로젝트를 읽지 않는 정적 help는 잠그지 않는다.
- 공유 read lock, retry, timeout은 실제 필요성이 확인되기 전에는 두지 않는다.

---

## 8. load와 복원 검증 순서

load는 다음 순서를 지킨다.

1. format과 Snapshot registry의 구조를 검증한다.
2. registry의 모든 manifest 객체가 실재하고 주소와 내용이 맞는지 검증한다.
3. Cycle Entry/Exit와 Verify의 모든 `snapshot_ref`가 registry에 실재하는지 검증한다.
4. World Graph와 Existence/Journey 불변식을 검증한다.

일반 load에서 모든 blob을 전수 hash하지 않는다. blob은 실제로 읽는 시점에 주소와 내용을
검증한다. 따라서 load 성공은 모든 manifest와 참조의 정합성을 뜻하지만, 읽지 않은 모든 blob
바이트의 완전성까지 증명한다는 뜻은 아니다.

---

## 9. 임시 객체 회수

프로젝트 lock을 얻은 직후, 상태를 읽기 전에 `artifacts/tmp`를 검사한다.

- GIL이 만드는 canonical 이름의 일반 파일만 회수한다.
- 모르는 이름, 디렉터리, 심볼릭 링크와 특수 항목은 조용히 지우지 않고 거절한다.
- `blobs`, `manifests`, `tmp` 외의 창고 최상위 항목도 거절한다.

이는 중단된 객체 쓰기의 잔해를 회수하는 규칙이다. 미참조 canonical 객체를 지우는 prune은
별도 기능이며 v0 범위에 없다.

---

## 10. `gil restore`의 저장 책임

restore 목표, Artifact-only 효과와 사용자 receipt는 `GIL Artifact Model v0.1` §8 및
`GIL Agent UX Model v0.1` §4.4가 정한다.

### 10.1 단계

```text
preflight → prepare → apply → verify → commit → cleanup
                         │       │
                         └───────┴──→ 실패하면 rollback
```

preflight는 파일을 바꾸기 전에 목표 manifest의 모든 blob을 흘려 읽어 주소와 실제 바이트를
검증하고, 현재 세계를 안정적으로 관측한 뒤 차이를 계산한다. 일반 load가 생략하는 blob 전수
검증을 실제 바이트를 쓰는 restore가 맡는다.

### 10.2 준비와 publish

```text
preparing 만들기
→ 덮어쓰거나 지울 현재 파일만 backup에 보관
→ PLAN 쓰기
→ 각 파일과 디렉터리 fsync
→ preparing을 active로 원자적 rename
→ restore 디렉터리 fsync
```

`preparing-*`은 아직 rollback 책임이 생기지 않은 준비 자료다. `active`가 publish된 뒤에만
사용자 Artifact를 바꿀 수 있고, 프로젝트 잠금 때문에 `active`는 최대 하나다. rollback
자료는 Snapshot이 아니며 registry에 넣거나 새 `SnapshotRef`를 발급하지 않는다.

### 10.3 PLAN

`PLAN`은 사람이 고치는 YAML이 아니라 엄격한 versioned binary다.

```text
magic      8 bytes  "GILPLAN\0"
version              고정 폭 big-endian
algorithm            현재 SHA-256
before world
operation count
operations           Replace | Delete | Create
```

- Replace는 경로, 실행 전 내용과 권한, backup 서수, 목표 내용을 기록한다.
- Delete는 경로, 실행 전 내용과 권한, backup 서수를 기록한다.
- Create는 경로와 목표 내용을 기록한다.
- 경로를 다시 정규화 검증하여 절대경로와 `..`가 프로젝트 밖을 가리키지 못하게 한다.
- 항목은 엄격한 오름차순이며 중복, 잘림, trailing bytes와 모르는 값은 거절한다.
- backup 파일 이름은 사용자 경로가 아니라 불투명한 서수다.

### 10.4 적용과 검증

목표 파일은 blob과 inode를 공유하지 않는다. 대상과 같은 폴더의 임시 파일에 blob을 흘려
복사하며 digest를 다시 검증하고, flush·fsync·권한 적용 뒤 rename하고 부모 디렉터리를
fsync한다. 내용 교체는 실행 전 권한을 보존하고 새 파일은 시스템 기본 권한을 사용한다.

각 적용 직전에 현재 자리가 계획이 본 before 상태와 같은지 확인한다. 전부 적용한 뒤에는
프로젝트를 다시 관측해 목표 manifest와 같은지 검증한다. 어느 단계든 실패하면 실행 전
Artifact 세계로 rollback한다.

### 10.5 commit과 cleanup

```text
COMMITTED 쓰기 → fsync → active 디렉터리 fsync
→ active를 cleanup-*로 rename → restore 디렉터리 fsync
→ 잔해 제거
```

`COMMITTED`가 내구성 있게 기록된 뒤에는 rollback하지 않는다. backup을 먼저 지우고 commit
표식을 나중에 쓰는 순서는 금지한다. 성공한 restore는 `state.yaml`을 저장하지 않으며
Graph·Will·Journey·Snapshot registry를 바꾸지 않는다.

### 10.6 다음 명령의 복구

모든 프로젝트 명령의 시작 순서는 다음과 같다.

```text
프로젝트 잠금 → restore 복구 → artifact tmp 회수 → state load → 원래 명령
```

| 흔적 | 처리 |
|---|---|
| `preparing-*` | rollback 책임 전이므로 잔해만 제거 |
| `active/`, `COMMITTED` 없음 | PLAN과 backup을 검증하고 rollback한 뒤 제거 |
| `active/COMMITTED` | forward가 확정됐으므로 rollback하지 않고 잔해만 제거 |
| `cleanup-*` | 이미 결정된 transaction의 잔해만 제거 |
| 모르는 이름·링크·특수 항목 | 조용히 지우지 않고 거절 |

복구에 실패하면 원래 명령을 실행하지 않는다. 외부 writer가 rollback과 계속 경쟁하면 안전한
완료를 주장하지 않고 recovery-required 상태를 유지한다.

### 10.7 내구성의 경계

디렉터리 `fsync`는 Unix에서만 수행한다. macOS의 일반 `fsync`는 드라이브 쓰기 캐시까지
비우는 `F_FULLFSYNC`가 아니므로 보장은 파일 시스템 계층까지다. rename 원자성은 같은 파일
시스템 안에서만 기대하므로 적용 임시 파일을 대상과 같은 폴더에 둔다.

---

## 11. 핵심 불변식

```text
public_snapshot_refs_never_expose_internal_addresses
canonical_manifest_bytes_are_platform_independent
an_existing_object_is_never_overwritten
objects_become_durable_before_state_references_them
one_manifest_world_has_one_snapshot_ref
every_graph_snapshot_ref_resolves_on_load
format_3_is_preserved_and_refused_not_guessed
an_absent_pending_cycle_revisit_means_none_in_format_4
a_pending_cycle_revisit_is_validated_and_consumed_exactly_once
project_state_is_read_and_written_under_one_lock
unknown_internal_entries_are_never_silently_deleted
restore_never_changes_graph_will_journey_or_registry
restore_blobs_are_verified_before_the_first_artifact_change
a_restore_plan_never_escapes_the_project
an_uncommitted_active_restore_rolls_back_before_state_load
a_committed_restore_is_never_rolled_back
a_restored_working_file_never_shares_an_inode_with_a_blob
```

---

## 12. 핵심 문장

> **공개 `SnapshotRef`는 세계의 이름이고, 내부 내용 주소는 그 세계를 저장소에서 찾는
> 방법이다. 둘을 분리한 채 객체를 먼저 내구성 있게 확정하고 Graph가 나중에 가리킨다.**
