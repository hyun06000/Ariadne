# gil v3 명세 — 커밋 그래프 위의 체인·사이클·스텝

**손 시연이 이 명세를 만든다.** 이 문서는 gil v3 코드가 구현할 청사진이다. 폴더도 md 파일도
없다 — 모든 위계는 커밋의 trailer로, 모든 본문은 커밋 로그로.

## 1. 노드 = 커밋

모든 스텝은 커밋 하나다.

- **제목(subject)**: `gil <chain>/<cycle>/<step> <kind>: <사람이 읽는 요약>`
  예: `gil gil-v3-redesign/C001/s3 verify: trailer 파싱 실증`
- **본문(body)**: 스텝 디테일 (자유 markdown). `git log --format=%b <sha>`로 읽는다.
- **트레일러(trailer)**: 구조 메타 (아래 §2). `git log --format='%(trailers:key=K,valueonly)'`.

산출물(코드·figure·field)이 있으면 그 커밋에 파일로 포함한다. 없으면 `--allow-empty` 노드.

## 2. 트레일러 키셋 (`Gil-` 네임스페이스, 원자적 분리)

키마다 값 하나. 나중에 키를 추가할 여지를 위해 최대한 분리한다.

### 위계 — 모든 스텝 커밋 필수
| 키 | 값 | 뜻 |
|---|---|---|
| `Gil-Chain` | 체인명 | 어느 체인. **없거나 미선언 체인이면 gil이 거부** |
| `Gil-Cycle` | 사이클 id | 어느 사이클 |
| `Gil-Step` | 스텝 id (s1, s2…) | 어느 스텝 |
| `Gil-Kind` | define\|hypothesis\|verify\|analyze\|success\|fail\|pending | 스텝 종류 |
| `Gil-Parent` | 부모 스텝 id \| null | 스텝 트리 부모 |

### 사이클 루트 스텝(s1)에만
| 키 | 값 | 뜻 |
|---|---|---|
| `Gil-Cycle-Author` | 존재명 | 이 사이클을 연 존재 |
| `Gil-Cycle-Parent` | 부모 사이클 참조 \| null | 사이클 계보. **여러 줄 = 사이클 머지(두 조상)** |

### 분석 결과 스텝에만
| 키 | 값 | 뜻 |
|---|---|---|
| `Gil-Outcome` | success \| backtrack \| fail | 분석 결말 |
| `Gil-Backtrack` | 조상 define 스텝 id | backtrack일 때 되돌아갈 곳 |

### 체인/사이클 머지에만 (git 머지 개념 차용)
| 키 | 값 | 뜻 |
|---|---|---|
| `Gil-Merge` | 합류하는 다른 체인/사이클 참조 | **여러 줄. 이 커밋 이후 노드는 양쪽 조상을 상속** |

> **머지 = 두 조상 (상현님, 2026-07-23)**: git 커밋이 머지되면 두 부모를 갖듯, gil 노드도
> 머지되는 순간부터 그 다음 노드들이 두 갈래의 조상을 물려받는다. 체인 간·사이클 간 관계는
> 이 머지로 표현한다. (옛 loom/C015 lineage 머지의 v3 네이티브 실현.)

## 3. gil이 방어하는 무결성 (fsck)

gil은 커밋 그래프를 훑어 아래를 검사한다. 위반이면 새 노드 선언을 거부하거나 fsck가 보고한다.

1. **위계 무결성** (상현님 핵심):
   - 체인 없는(=`Gil-Chain` 미선언·미존재 체인) 사이클 선언 거부.
   - 사이클 없는 스텝 선언 거부.
   - `Gil-Parent`가 가리키는 부모 스텝이 실재해야 함 (dangling parent 거부).
   - 스텝 트리에 순환 없음.
2. **id 문법·중복**: chain·cycle·step id는 소문자·숫자·하이픈만(git ref 안전, 마침표 금지).
   같은 체인에서 사이클 id 중복 금지. (옛 R1 계승.)
3. **스텝 순환 규칙**: define→hypothesis→verify→analyze 순환. analyze는 `Gil-Outcome` 강제.
   backtrack이면 `Gil-Backtrack`가 조상 define을 가리켜야 함.
4. **계보 참조 무결성**: `Gil-Cycle-Parent`·`Gil-Merge`가 실재하는 사이클/체인을 가리켜야 함
   (옛 R6의 v3판, C041 이월).

## 4. 명령 표면 (gil이 구현할 것)

손 시연으로 규약을 확립한 뒤 이 명령들을 빌드한다:

- `gil open <chain>/<cycle> --author <who> [--parent <cyc>...]` — 루트 define 커밋 새김.
- `gil step --kind <k> [--outcome <o>] [--to <define>]` — 스텝 전이 커밋.
- `gil close [--verdict <v>]` — 산 잎 봉인.
- `gil merge <a> <b>` — 두 갈래 합류(이후 노드 양쪽 조상).
- `gil log [<chain>]` — 커밋 그래프에서 위계·계보·본문 조회 (뷰어의 데이터원).
- `gil fsck` — §3 무결성 검사.

각 명령은 **git 커밋을 새기고 trailer를 붙이는 얇은 래퍼**다. 진실원은 언제나 커밋 그래프.
