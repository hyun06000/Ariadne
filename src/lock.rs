//! 프로젝트 트랜잭션 잠금 — **한 프로젝트에 한 번에 한 명령.**
//!
//! 두 `gil` 이 같은 프로젝트를 동시에 만지면 조용히 잃는 것이 생긴다.
//!
//! ```text
//! A: state 읽기 ─── Graph 변경 ──── state 쓰기
//! B:      state 읽기 ─── Journey 변경 ──── state 쓰기   ← A 의 변경이 사라진다
//! ```
//!
//! Snapshot 이름도 마찬가지다. 둘이 같은 `next_id` 를 읽으면 같은 `snapshot:A7` 을 서로 다른
//! 세계에 준다. 그러면 「이름이 같으면 세계가 같다」가 무너진다.
//!
//! # 파일이 있는 것은 잠긴 것이 아니다
//!
//! `.gil/project.lock` 은 **계속 남아 있는다.** 잠금 상태는 그 파일에 건 운영체제의
//! advisory lock 이 진다.
//!
//! ```text
//! 파일이 있다      아무 뜻도 없다 — 지난 명령이 남긴 자리일 뿐이다
//! lock 이 걸렸다   지금 다른 gil 명령이 이 프로젝트 안에 있다
//! ```
//!
//! 그래서 프로세스가 죽어도 **운영체제가 푼다.** 사람이 잔해를 지울 일이 없고, PID 파일을
//! 읽어 살아 있는지 추측할 일도 없다. `create_new` sentinel 이나 lock 디렉터리 polling 은
//! 정확히 그 추측을 되살리는 방식이라 쓰지 않는다.
//!
//! # 이 잠금이 막지 못하는 것
//!
//! **advisory 다.** 편집기·`rm`·다른 프로그램이 `.gil` 을 직접 고치는 것을 막지 않는다.
//! 서로 협력하는 것은 GIL 명령끼리뿐이다. 네트워크 파일 시스템에서는 그마저 보장되지
//! 않을 수 있다(§10.6).

use std::fmt;
use std::fs::{self, File, TryLockError};
use std::path::{Path, PathBuf};

/// 루트 `.gil/` 안에서 잠금이 사는 자리. **내용은 쓰지 않는다.**
pub(crate) const LOCK_FILE: &str = "project.lock";

/// 이 프로젝트를 지금 이 명령이 쥐고 있다는 증거.
///
/// # 살아 있는 동안만 유효하다
///
/// 잠금은 **열린 파일 handle** 에 걸린다. 그래서 handle 의 수명과 잠금의 수명이 같아야
/// 한다 — 그 둘을 한 값 안에 묶어 둔 이유다. 정상 반환·오류 반환·panic unwind 어느
/// 길로 나가든 이 값이 떨어지면서 풀리고, 프로세스가 죽으면 운영체제가 푼다.
///
/// **임시 값으로 두지 않는다.** `let _ = acquire(..)` 는 그 자리에서 바로 떨어져 잠금이
/// 없는 채로 이어진다. 이름 있는 변수로 받아 명령이 끝날 때까지 살려 둔다.
#[derive(Debug)]
pub(crate) struct ProjectLock {
    /// 잠금이 걸린 그 handle. **이것이 닫히면 잠금도 없다.**
    ///
    /// 여기 있는 것은 이것뿐이다 — 경로를 함께 들고 다니면 그 경로가 잠금의 상태를
    /// 말하는 것처럼 읽힌다. 잠금을 말하는 것은 handle 하나다.
    file: File,
}

impl ProjectLock {
    /// 이미 있는 `.gil/` 의 잠금을 **기다리지 않고** 잡는다.
    ///
    /// 이미 다른 GIL 명령이 쥐고 있으면 [`LockError::Busy`] 로 **즉시** 돌아온다. v0 은
    /// 기다리지 않는다 — 무기한 sleep 은 Agent 의 턴을 삼키고, 얼마나 기다릴지는 사람이
    /// 정할 일이지 도구가 몰래 정할 일이 아니다.
    pub(crate) fn acquire(gil_dir: &Path) -> Result<ProjectLock, LockError> {
        ProjectLock::hold(gil_dir.join(LOCK_FILE))
    }

    /// 아직 `.gil/` 이 없을 수 있는 자리에서 잡는다 — `gil start` 의 입구.
    ///
    /// 디렉터리를 먼저 만들고 잠근다. **그 다음에** 무엇이 이미 있는지 본다 — 잠그기 전에
    /// 보면 두 `gil start` 가 나란히 "비어 있다" 를 읽고 각자 다른 최초 상태를 세운다.
    pub(crate) fn bootstrap(gil_dir: &Path) -> Result<ProjectLock, LockError> {
        fs::create_dir_all(gil_dir).map_err(|source| LockError::Unavailable {
            path: gil_dir.to_path_buf(),
            doing: "내부 저장소 자리를 만들지",
            source: source.to_string(),
        })?;
        ProjectLock::acquire(gil_dir)
    }

    fn hold(path: PathBuf) -> Result<ProjectLock, LockError> {
        // 파일은 **없으면 만들고, 있으면 그대로 쓴다.** 매번 만들고 지우면 그 자체가
        // 경쟁이 되고, 지우는 쪽이 남의 잠금을 들고 있는 파일을 치우게 된다.
        let file = File::options()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(&path)
            .map_err(|source| LockError::Unavailable {
                path: path.clone(),
                doing: "잠금 파일을 열지",
                source: source.to_string(),
            })?;

        match file.try_lock() {
            Ok(()) => Ok(ProjectLock { file }),
            // 진짜 경쟁이다 — 다른 GIL 명령이 쥐고 있다.
            Err(TryLockError::WouldBlock) => Err(LockError::Busy { path }),
            // 잠금 자체를 걸 수 없는 자리다(파일 시스템이 지원하지 않는 등). 경쟁과 **구분해**
            // 말한다 — 사람이 할 일이 서로 다르다.
            Err(TryLockError::Error(source)) => Err(LockError::Unavailable {
                path,
                doing: "이 프로젝트를 잠그지",
                source: source.to_string(),
            }),
        }
    }

}

impl Drop for ProjectLock {
    fn drop(&mut self) {
        // 실패해도 할 수 있는 것이 없고, 할 필요도 없다 — 곧 닫히는 handle 과 함께
        // 운영체제가 어차피 푼다. 여기서 푸는 것은 **의도를 코드에 남기기 위해서**다.
        let _ = self.file.unlock();
    }
}

/// 잠그지 못한 이유. **어느 쪽이든 상태를 읽지도 바꾸지도 않았다.**
#[derive(Debug)]
pub(crate) enum LockError {
    /// 다른 GIL 명령이 이 프로젝트를 쥐고 있다. 나중에 다시 하면 된다.
    Busy { path: PathBuf },
    /// 잠금 자체를 걸 수 없었다. 다시 해도 같을 것이다.
    Unavailable {
        path: PathBuf,
        doing: &'static str,
        source: String,
    },
}

impl fmt::Display for LockError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            LockError::Busy { .. } => write!(
                f,
                "다른 GIL 명령이 이 프로젝트를 사용하고 있다.\n\n\
                 현재 상태를 읽거나 변경하지 않았다.\n\
                 앞선 명령이 끝난 뒤 다시 시도한다."
            ),
            LockError::Unavailable {
                path,
                doing,
                source,
            } => write!(
                f,
                "{doing} 못했다 ({}) — {source}.\n\n\
                 현재 상태를 읽거나 변경하지 않았다.\n\
                 `.gil` 이 잠금을 지원하는 파일 시스템에 있는지 확인한다 \
                 (네트워크 파일 시스템에서는 지원되지 않을 수 있다).",
                path.display()
            ),
        }
    }
}

impl std::error::Error for LockError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn scratch(label: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("gil-lock-{label}")).join(".gil");
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만들 수 있어야 한다");
        dir
    }

    #[test]
    fn a_lock_can_be_taken_and_the_file_stays_behind() {
        let gil = scratch("basic");
        let held = ProjectLock::acquire(&gil).expect("빈 프로젝트를 잠근다");
        assert!(gil.join(LOCK_FILE).exists(), "잠그면서 자리를 만들지 않았다");

        drop(held);
        // **파일은 남는다.** 남은 파일은 잠금이 아니다.
        assert!(gil.join(LOCK_FILE).exists(), "정상 코드가 잠금 파일을 지웠다");
    }

    #[test]
    fn a_leftover_lock_file_does_not_block_anyone() {
        let gil = scratch("leftover");
        fs::write(gil.join(LOCK_FILE), b"").expect("잔해를 놓는다");
        // 존재만으로 거절하면 사람이 손으로 지워야 하는 stale lock 이 된다.
        ProjectLock::acquire(&gil).expect("남은 파일이 길을 막았다");
    }

    #[test]
    fn a_second_hold_in_this_process_is_refused_not_granted() {
        let gil = scratch("reentrant");
        let _held = ProjectLock::acquire(&gil).expect("첫 번째가 잡는다");

        let err = ProjectLock::acquire(&gil).expect_err("같은 프로세스가 두 번 잡았다");
        assert!(matches!(err, LockError::Busy { .. }), "{err}");
        // 그래서 **명령 경계에서 한 번만** 잡는다 — 안쪽 함수가 다시 잡으면 제 발에 걸린다.
    }

    #[test]
    fn dropping_the_guard_releases_it() {
        let gil = scratch("release");
        drop(ProjectLock::acquire(&gil).expect("잡는다"));
        drop(ProjectLock::acquire(&gil).expect("풀린 뒤 다시 잡는다"));
    }

    #[test]
    fn a_lock_is_per_project_not_global() {
        let one = scratch("project-one");
        let two = scratch("project-two");
        let _held = ProjectLock::acquire(&one).expect("한쪽을 잡는다");
        ProjectLock::acquire(&two).expect("다른 프로젝트가 막혔다");
    }

    #[test]
    fn bootstrap_makes_the_place_it_locks() {
        let root = std::env::temp_dir().join("gil-lock-bootstrap");
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        let gil = root.join(".gil");
        assert!(!gil.exists());

        let _held = ProjectLock::bootstrap(&gil).expect("자리를 만들며 잠근다");
        assert!(gil.is_dir());
        assert!(gil.join(LOCK_FILE).exists());
    }

    #[test]
    fn contention_and_a_place_that_cannot_lock_are_different_words() {
        let gil = scratch("words");
        let _held = ProjectLock::acquire(&gil).unwrap();
        let busy = ProjectLock::acquire(&gil).expect_err("경쟁이다");
        assert!(matches!(busy, LockError::Busy { .. }));
        assert!(busy.to_string().contains("다른 GIL 명령이"));
        assert!(busy.to_string().contains("읽거나 변경하지 않았다"));

        let nowhere = ProjectLock::acquire(Path::new("/이런/자리는/없다"))
            .expect_err("없는 자리를 잠갔다");
        assert!(
            matches!(nowhere, LockError::Unavailable { .. }),
            "OS 오류를 경쟁이라고 말했다: {nowhere}"
        );
    }
}
