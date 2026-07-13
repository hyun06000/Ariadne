# 기대 판정 (정답 고정)

> ⚠️ 이 문서는 **패키지 작성 전**에 고정되었다 (2026-07-14). 산출물에 맞춰 수정 금지.

| id | 판정 | 기준 |
|---|---|---|
| T1 | 신선 환경 재현 | 임시 디렉토리에 `rooms/deployment/ariadne-spec/`만 복사하고, QUICKSTART.md의 모든 ```bash 블록을 순서대로 이어붙여 `bash -e`로 실행하면 exit 0. 실행 후: 체인 `demo` 존재, `C001-first-question`의 status가 closed, fsck exit 0, `chains.html`이 존재하며 `id="ari-data"` JSON에 demo 체인 포함 |
| T2 | 도구 무드리프트 | `ariadne-spec/ari.py`의 sha256 = C005 최종본(`C005-web-viewer/3-verification/ari/ari.py`)의 sha256 |
| T3 | 스펙 완전성 | SPEC.md에 문자열 R1~R8 전부와 `log`·`fsck`·`open`·`close`·`verify`·`web` 6개 명령 전부 존재 |
| T4 | 배포 근거 | RELEASE.md에 근거 사이클 id 5개(C001-lineage-is-reconstructable ~ C005-web-viewer) 전부 명시 |
| T5 | 템플릿 무드리프트 | `ariadne-spec/template/`의 모든 파일이 `rooms/experiment/_template/`과 파일 단위 sha256 동일 (개수 포함) |
| T6 | 버저닝 | (릴리스 커밋 후) 깃 태그 `v0.1.0` 존재 + `rooms/deployment/CHANGELOG.md`에 `[0.1.0]` 항목 |

- T1의 정신: **문서가 곧 테스트다.** 퀵스타트가 낡으면 T1이 깨진다.
- T1 실행 중 실험의 방(rooms/experiment/chains의 실데이터)에 대한 어떤 참조도 있어서는 안 된다 — 복사되는 것은 릴리스 패키지뿐이다.
