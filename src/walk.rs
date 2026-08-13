//! Walk — 지금 어디에 서 있는가.
//!
//! Grammar 는 *무엇이 허락되는지* 만 안다. 여기서 더하는 것은 **자리**다: 어떤 Node 가
//! 있고, 어느 Node 에서 어느 Node 가 났고, 지금 어디에 서 있는가.
//!
//! **계승은 기록이지 추론이 아니다.** 새 Node 는 태어나는 순간 제 부모를 적는다.
//! 실행 순서로 부모를 되계산하지 않는다 — 되돌아가기가 생기면 "직전에 실행한 것"과
//! "이 Node 의 부모"는 갈라지고, 그때 순서로 세운 계보는 조용히 거짓이 된다.
//!
//! 판정은 전부 [`RuleSet`] 에 넘긴다. 같은 규칙을 여기서 다시 구현하지 않는다.
//!
//! 아직 없는 것: 되돌아가기 · 분기 · 계보 API · 저장 · Artifact · Chain · Cycle.

use std::fmt;

use crate::node::{Node, NodeKind, NodeStatus};
use crate::report::Report;
use crate::rules::RuleSet;
use crate::validate::GrammarError;

/// 한 [`Walk`] 의 Step Graph 안에서만 유일한 Node 의 이름.
///
/// 저장소를 건너서도, 프로젝트 전체에서도 유일하다고 주장하지 않는다 — 그건 저장이
/// 생길 때 다시 볼 자리다. 다른 계층(Cycle·Chain)의 이름도 아니다. 발급은 `Walk` 만 한다.
///
/// 자리(`nodes` 의 인덱스)와 섞이지 않도록 일부러 newtype 이다.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct NodeId(u32);

impl fmt::Display for NodeId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "#{}", self.0)
    }
}

/// Step Node 하나 — 열려 있든 닫혀 있든 같은 자리에 산다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StepNode {
    pub id: NodeId,
    pub kind: NodeKind,
    /// 이 Node 가 **같은 Step Graph 안에서** 어느 Node 의 사고를 직접 이어받아 났는가.
    ///
    /// 한 번 적히면 바뀌지 않는다. 실행 순서로 되계산하지 않는다.
    ///
    /// `None` 은 **고아라는 뜻이 아니다.** 이 Step Graph 의 *local root* 이며 상위 Container 인
    /// Cycle 의 Entry Boundary 를 통해 들어왔다는 뜻이다.
    ///
    /// 계층이 다른 Node 를 여기에 넣지 않는다 — 앞 Cycle 의 마지막 Outcome 도, Cycle Node
    /// 자신도 Step 의 parent 가 될 수 없다. Cycle 사이의 계승은 Cycle Graph 가, 어느 Cycle 에
    /// 담겼는지는 Containment 가 따로 말한다(둘 다 아직 없다).
    pub parent: Option<NodeId>,
    pub status: NodeStatus,
    /// 닫히면서 받는다. 열려 있는 동안은 `None`.
    pub report: Option<Report>,
}

/// 한 Cycle 안의 Step 을 걸어 온 자리.
#[derive(Debug, Clone)]
pub struct Walk {
    rules: RuleSet,
    nodes: Vec<StepNode>,
    current: Option<NodeId>,
    finished: bool,
    next_id: u32,
}

impl Walk {
    /// Cycle 의 시작 경계에 선다. 아직 아무 Node 도 없다.
    pub fn start(rules: RuleSet) -> Self {
        Walk {
            rules,
            nodes: Vec::new(),
            current: None,
            finished: false,
            next_id: 1,
        }
    }

    /// 지금 자리에서 다음 Node 를 연다.
    ///
    /// 새 Node 의 부모는 **여는 그 순간의 `current`** 이고, 그대로 기록된다.
    /// 경계(`cycle_exit`)를 열면 그것은 지나가는 것이다 — Node 가 되지 않고 걷기가 끝난다.
    pub fn open(&mut self, kind: NodeKind) -> Result<(), WalkError> {
        if self.finished {
            return Err(WalkError::AlreadyFinished);
        }

        // 판정이 먼저다 — 거절되면 Node 도, 이름도 생기지 않는다.
        self.rules.validate_open(self.here(), kind)?;

        if kind.is_boundary() {
            // 경계는 Step 이 아니다. 이름도 안 받고 기록에도 안 남으며,
            // 서 있던 자리(current)는 그대로 둔다.
            self.finished = true;
            return Ok(());
        }

        let id = NodeId(self.next_id);
        self.next_id += 1;
        self.nodes.push(StepNode {
            id,
            kind,
            parent: self.current,
            status: NodeStatus::Open,
            report: None,
        });
        self.current = Some(id);
        Ok(())
    }

    /// 지금 서 있는 Node 를 이 Report 로 닫는다. 자리는 그대로 남는다.
    pub fn close(&mut self, report: Report) -> Result<(), WalkError> {
        if self.finished {
            return Err(WalkError::AlreadyFinished);
        }
        let Some(id) = self.current else {
            return Err(WalkError::NothingToClose);
        };
        let at = self
            .position_of(id)
            .expect("current 는 언제나 실재하는 Node 를 가리킨다");
        if self.nodes[at].status != NodeStatus::Open {
            return Err(WalkError::NothingToClose);
        }

        self.rules.validate_close(self.nodes[at].kind, &report)?;

        self.nodes[at].status = NodeStatus::Closed;
        self.nodes[at].report = Some(report);
        Ok(())
    }

    /// 지금 서 있는 Node 의 이름.
    ///
    /// 열려 있는지와는 무관하다 — 닫아도 그 자리에 그대로 서 있다.
    /// `None` 은 아직 아무 Node 도 열지 않았다는 뜻이다.
    pub fn current(&self) -> Option<NodeId> {
        self.current
    }

    /// 이 걷기가 만든 Step Node 전부, 만든 순서대로(열린 것도 포함).
    pub fn nodes(&self) -> &[StepNode] {
        &self.nodes
    }

    /// 이름으로 하나를 찾는다.
    pub fn node(&self, id: NodeId) -> Option<&StepNode> {
        self.nodes.iter().find(|node| node.id == id)
    }

    /// 닫힌 Node 들을 만든 순서대로 본다.
    ///
    /// 따로 쌓아 두는 것이 아니라 [`Walk::nodes`] 를 걸러 보는 **시야**다 —
    /// 같은 것을 두 자리에 담지 않는다.
    pub fn history(&self) -> impl Iterator<Item = &StepNode> {
        self.nodes
            .iter()
            .filter(|node| node.status == NodeStatus::Closed)
    }

    /// 끝 경계를 지났는가. 어디에 서 있는가와는 다른 물음이다.
    pub fn is_finished(&self) -> bool {
        self.finished
    }

    /// 이 걷기가 따르는 Grammar.
    pub fn rules(&self) -> &RuleSet {
        &self.rules
    }

    /// 지금 서 있는 자리 — Grammar 에게 물을 때 쓰는 꼴.
    fn here(&self) -> Node {
        match self.current.and_then(|id| self.node(id)) {
            Some(node) => Node {
                kind: node.kind,
                status: node.status,
            },
            None => Node::cycle_entry(),
        }
    }

    /// 이름이 놓인 자리. 지금은 이름 순서와 자리가 같지만 그 우연에 기대지 않는다.
    fn position_of(&self, id: NodeId) -> Option<usize> {
        self.nodes.iter().position(|node| node.id == id)
    }
}

/// 걷기가 거절한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WalkError {
    /// Grammar 가 거절했다.
    Grammar(GrammarError),
    /// 열려 있는 Node 가 없다 — 닫을 것이 없다.
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
