//! Walk — 지금 어디까지 걸었는가.
//!
//! Grammar 는 *무엇이 허락되는지* 만 안다. 여기서 더하는 것은 **지금 어디에 서 있는가** 하나다.
//! 그래서 부르는 쪽이 부모를 손으로 지어낼 자리가 사라진다 — 부모는 걸어온 자리에서 나온다.
//!
//! 판정은 전부 [`RuleSet`] 에 넘긴다. 같은 규칙을 여기서 다시 구현하지 않는다.
//!
//! 아직 없는 것: 되돌아가기 · 분기 · 저장 · Artifact · Lineage · Chain · Cycle.
//! `Walk` 는 Cycle 객체가 아직 없는 지금, 한 Cycle 안의 Step 을 메모리에서 걸어 보기 위한
//! **구현 이름**이다 — GIL 의 개념이 아니다.

use std::fmt;

use crate::node::{Node, NodeKind};
use crate::report::Report;
use crate::rules::RuleSet;
use crate::validate::GrammarError;

/// 닫힌 Step 하나 — 그때 남긴 Report 와 함께.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClosedNode {
    pub kind: NodeKind,
    pub report: Report,
}

/// 한 Cycle 안의 Step 을 걸어 온 자리.
#[derive(Debug, Clone)]
pub struct Walk {
    rules: RuleSet,
    current: Option<Node>,
    closed: Vec<ClosedNode>,
    finished: bool,
}

impl Walk {
    /// Cycle 의 시작 경계에 선다. 아직 아무것도 열지 않았다.
    pub fn start(rules: RuleSet) -> Self {
        Walk {
            rules,
            current: None,
            closed: Vec::new(),
            finished: false,
        }
    }

    /// 다음 Node 를 연다.
    ///
    /// 부모는 걸어온 자리가 정한다 — 열린 것이 있으면 그것, 없으면 마지막에 닫은 것,
    /// 그것도 없으면 Cycle 의 시작 경계다. 열려 있는 것이 있으면 Grammar 가 거절한다.
    ///
    /// 경계(`cycle_exit`)를 열면 그것은 **지나가는 것**이다 — 열린 Node 로 남지 않고
    /// 걷기가 끝난다.
    pub fn open(&mut self, kind: NodeKind) -> Result<(), WalkError> {
        if self.finished {
            return Err(WalkError::AlreadyFinished);
        }

        // 판정이 먼저다 — 거절되면 아래 한 줄도 실행되지 않는다.
        self.rules.validate_open(self.parent(), kind)?;

        if kind.is_boundary() {
            self.finished = true;
        } else {
            self.current = Some(Node::open(kind));
        }
        Ok(())
    }

    /// 열려 있는 Node 를 이 Report 로 닫는다.
    pub fn close(&mut self, report: Report) -> Result<(), WalkError> {
        if self.finished {
            return Err(WalkError::AlreadyFinished);
        }
        let Some(node) = self.current else {
            return Err(WalkError::NothingToClose);
        };

        self.rules.validate_close(node.kind, &report)?;

        self.closed.push(ClosedNode {
            kind: node.kind,
            report,
        });
        self.current = None;
        Ok(())
    }

    /// 지금 열려 있는 Node. 없으면 `None`.
    pub fn current(&self) -> Option<Node> {
        self.current
    }

    /// 닫은 순서대로의 Step 들.
    pub fn history(&self) -> &[ClosedNode] {
        &self.closed
    }

    /// 끝 경계를 지났는가.
    pub fn is_finished(&self) -> bool {
        self.finished
    }

    /// 이 걷기가 따르는 Grammar.
    pub fn rules(&self) -> &RuleSet {
        &self.rules
    }

    /// 다음에 열릴 것의 부모가 되는 자리.
    fn parent(&self) -> Node {
        match (self.current, self.closed.last()) {
            (Some(open), _) => open,
            (None, Some(last)) => Node::closed(last.kind),
            (None, None) => Node::cycle_entry(),
        }
    }
}

/// 걷기가 거절한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WalkError {
    /// Grammar 가 거절했다.
    Grammar(GrammarError),
    /// 닫을 것이 없다 — 열려 있는 Node 가 없다.
    NothingToClose,
    /// 끝 경계를 이미 지났다.
    AlreadyFinished,
}

impl From<GrammarError> for WalkError {
    fn from(err: GrammarError) -> Self {
        WalkError::Grammar(err)
    }
}

impl fmt::Display for WalkError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            WalkError::Grammar(err) => write!(f, "{err}"),
            WalkError::NothingToClose => {
                write!(f, "지금 열려 있는 Node 가 없어 닫을 것이 없다")
            }
            WalkError::AlreadyFinished => {
                write!(f, "끝 경계를 이미 지났다 — 이 걷기에서는 더 열 수 없다")
            }
        }
    }
}

impl std::error::Error for WalkError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            WalkError::Grammar(err) => Some(err),
            WalkError::NothingToClose | WalkError::AlreadyFinished => None,
        }
    }
}
