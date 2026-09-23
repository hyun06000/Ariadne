//! **정확한 Project root 로 여는 문** — MCP 진입점의 계약.
//!
//! CLI 와 **일부러 다르다.** 사람은 Project 안 어디에서나 `gil status` 를 치고, 그래서 CLI 는
//! 서 있는 자리에서 위로 거슬러 오른다. 그것은 사람의 편의이고 옳다.
//!
//! Agent 는 아니다. `project_root` 라는 이름은 "여기서부터 찾아라" 가 아니라 **"이것이 그
//! Project 다"** 라는 뜻이다. 위로 오르는 것을 허용하면 이런 일이 벌어진다.
//!
//! ```text
//! /project-a/        ← GIL Project
//! /project-a/tmp/    ← Agent 가 실수로 project_root 로 넘겼다
//! ```
//!
//! 조상 탐색은 이 요청을 말없이 `/project-a` 로 옮긴다. 사람이 겨눈 적 없는 Project 가
//! 열리고, 쓰는 명령이었다면 거기에 적힌다. 장수 MCP server 에서는 이것이 사고다 —
//! 요청마다 범위가 조용히 넓어지고, 넓어진 사실은 어디에도 남지 않는다.
//!
//! 그래서 이 문은 `<project_root>/.gil/state.yaml` **하나만** 본다. 없으면 없다고 답한다.
//! cwd 를 읽지 않고, `chdir` 하지 않으며, 상위로 물러서지 않는다.
//!
//! 나뉘는 것은 여기까지다. 검증된 [`ProjectSession`] 을 손에 넣은 뒤의 domain 판독과
//! renderer 는 CLI 와 **같은 것**을 쓴다([`crate::where_now`]).

use std::path::Path;

use crate::{ProjectSession, RuleSet, SessionError, StoreError};

/// 정확 경로로 열지 못한 이유. **경로를 싣지 않는다** — 부르는 쪽이 이미 아는 값이고,
/// 답에 실으면 사용자에게 가는 문장에 절대경로가 새는 문이 하나 더 생긴다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RootError {
    /// 반쪽 경로를 받았다. 서 있는 자리에 따라 다른 것을 가리키므로 받지 않는다.
    NotAbsolute,
    /// 그 자리에 GIL Project 가 없다. **위로 오르지 않았다**는 사실이 이 이름에 있다.
    NoProjectHere,
    /// 열 수는 있었으나 세계 쪽이 거절했다 — 이유는 이미 사람의 말로 적혀 있다.
    Session(String),
}

impl std::fmt::Display for RootError {
    fn fmt(&self, out: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NotAbsolute => out.write_str(
                "project_root 는 온전한 경로여야 한다.\n\n\
                 이유\n  \
                 반쪽 경로는 서 있는 자리에 따라 다른 것을 가리킨다.\n\n\
                 다음\n  \
                 GIL Project 의 절대경로를 적는다.\n",
            ),
            Self::NoProjectHere => out.write_str(
                "그 자리에 걷기가 없다.\n\n\
                 이유\n  \
                 준 자리에서 기록을 찾지 못했다. 위로 거슬러 오르지 않았다 — \
                 project_root 는 찾기 시작할 곳이 아니라 Project 그 자체다.\n\n\
                 다음\n  \
                 Project 의 root 를 정확히 적거나, 거기서 `gil start` 로 시작한다.\n",
            ),
            Self::Session(said) => out.write_str(said),
        }
    }
}

/// `<root>/.gil/state.yaml` 하나만 열어 검증된 Session 을 준다.
///
/// 이 함수는 위로 오르지 않고, cwd 를 읽지 않고, 작업 디렉터리를 바꾸지 않는다.
pub fn open_project_root(rules: RuleSet, root: &Path) -> Result<ProjectSession, RootError> {
    if !root.is_absolute() {
        return Err(RootError::NotAbsolute);
    }
    let state = root.join(crate::STATE_PATH);
    if !state.exists() {
        // 앞 형식만 있는 자리도 **여기서 멈춘다.** 조용히 지나치면 사람은 제 기록이
        // 사라진 줄 안다 — 그 판정은 CLI 와 같다.
        let legacy = root.join(crate::LEGACY_WALK_PATH);
        if legacy.exists() {
            return Err(RootError::Session(
                StoreError::LegacyFormat {
                    path: crate::said_path(&legacy),
                }
                .to_string(),
            ));
        }
        return Err(RootError::NoProjectHere);
    }

    ProjectSession::open(rules, &state).map_err(|err| match err {
        // 방금 있는 것을 보고 왔다. 그새 사라졌다면 그건 다른 이야기다.
        SessionError::Store(StoreError::NotFound { .. }) => RootError::NoProjectHere,
        other => RootError::Session(other.to_string()),
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn rules() -> RuleSet {
        RuleSet::builtin().expect("함께 실린 명세")
    }

    fn started(at: &Path) {
        std::fs::create_dir_all(at).expect("자리");
        let session =
            ProjectSession::start(rules(), at.join(crate::STATE_PATH)).expect("시작한다");
        session.commit().expect("눕힌다");
    }

    fn scratch(name: &str) -> std::path::PathBuf {
        let at = std::env::temp_dir().join(format!("gil-root-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&at);
        std::fs::create_dir_all(&at).expect("자리");
        at
    }

    #[test]
    fn a_relative_root_is_refused_before_anything_is_opened() {
        let said = open_project_root(rules(), Path::new("some/where")).unwrap_err();
        assert_eq!(said, RootError::NotAbsolute);
    }

    #[test]
    fn an_empty_place_is_refused_without_climbing() {
        let at = scratch("empty");
        let said = open_project_root(rules(), &at).unwrap_err();
        assert_eq!(said, RootError::NoProjectHere);
        std::fs::remove_dir_all(&at).ok();
    }

    /// **이 조각의 핵심 불변식.** 부모가 Project 여도 자식은 자식이다.
    #[test]
    fn a_child_of_a_project_is_not_that_project() {
        let parent = scratch("parent");
        started(&parent);
        let child = parent.join("tmp");
        std::fs::create_dir_all(&child).expect("자리");

        let said = open_project_root(rules(), &child).unwrap_err();
        assert_eq!(
            said,
            RootError::NoProjectHere,
            "자식 자리를 받고 부모 Project 를 열었다"
        );
        std::fs::remove_dir_all(&parent).ok();
    }

    #[test]
    fn the_refusal_never_carries_an_absolute_path() {
        for said in [
            RootError::NotAbsolute.to_string(),
            RootError::NoProjectHere.to_string(),
        ] {
            assert!(!said.contains('/'), "경로가 새어 나왔다: {said}");
        }
    }

    #[test]
    fn an_exact_root_opens_and_the_session_points_at_it() {
        let at = scratch("exact");
        started(&at);
        let session = open_project_root(rules(), &at).expect("연다");
        assert_eq!(session.state_path(), at.join(crate::STATE_PATH));
        drop(session);
        std::fs::remove_dir_all(&at).ok();
    }
}
