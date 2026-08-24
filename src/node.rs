//! Node 의 종류와 상태.
//!
//! 종류는 `gil-spec.yaml` 이 이름으로 부르는 것과 같은 집합이다.
//! `cycle_entry`·`cycle_exit` 은 `step_kinds` 에 없다 — Grammar 의 시작과 끝을 가리키는
//! **경계 표식**이지 Step 이 아니다(제 close_requires 도, 제 규칙도 갖지 않는다).

use std::fmt;

use serde::Deserialize;

/// Node 의 종류. Interview 셋 · Experiment 넷 · 둘이 함께 쓰는 `outcome` · 경계 표식 둘.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum NodeKind {
    CycleEntry,
    // Interview Cycle 의 Step 들.
    Question,
    Interpretation,
    Synthesis,
    // Experiment Cycle 의 Step 들.
    Define,
    Hypothesis,
    Verify,
    Analysis,
    /// 두 Cycle Kind 가 **함께 쓰는** 이름. 요구하는 Report 는 서로 다르고, 그 차이는
    /// `gil-spec.yaml` 의 Cycle Kind 안에 적혀 있다.
    Outcome,
    CycleExit,
}

impl NodeKind {
    /// 모든 종류. 시험이 전수로 훑을 때 쓴다.
    pub const ALL: [NodeKind; 10] = [
        NodeKind::CycleEntry,
        NodeKind::Question,
        NodeKind::Interpretation,
        NodeKind::Synthesis,
        NodeKind::Define,
        NodeKind::Hypothesis,
        NodeKind::Verify,
        NodeKind::Analysis,
        NodeKind::Outcome,
        NodeKind::CycleExit,
    ];

    /// `gil-spec.yaml` 에 적히는 이름.
    pub fn as_str(self) -> &'static str {
        match self {
            NodeKind::CycleEntry => "cycle_entry",
            NodeKind::Question => "question",
            NodeKind::Interpretation => "interpretation",
            NodeKind::Synthesis => "synthesis",
            NodeKind::Define => "define",
            NodeKind::Hypothesis => "hypothesis",
            NodeKind::Verify => "verify",
            NodeKind::Analysis => "analysis",
            NodeKind::Outcome => "outcome",
            NodeKind::CycleExit => "cycle_exit",
        }
    }

    /// 사람이 적어 준 이름을 종류로 읽는다. 모르는 이름이면 `None`.
    ///
    /// 이름의 목록을 여기 다시 적지 않는다 — [`NodeKind::ALL`] 과 [`NodeKind::as_str`] 이
    /// 이미 그것을 안다. 종류가 늘면 이 함수는 고치지 않아도 함께 는다.
    pub fn parse(name: &str) -> Option<NodeKind> {
        NodeKind::ALL.into_iter().find(|kind| kind.as_str() == name)
    }

    /// Grammar 의 시작과 끝을 가리키는 표식인가.
    ///
    /// 경계 표식은 열고 닫는 대상이 아니라 자리를 가리키는 이름이다.
    pub fn is_boundary(self) -> bool {
        matches!(self, NodeKind::CycleEntry | NodeKind::CycleExit)
    }
}

impl fmt::Display for NodeKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// Node 의 상태. v0.1 은 이 둘만 쓴다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum NodeStatus {
    Open,
    Closed,
}

impl fmt::Display for NodeStatus {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(match self {
            NodeStatus::Open => "open",
            NodeStatus::Closed => "closed",
        })
    }
}

/// 종류와 상태를 함께 가진 Node 하나.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Node {
    pub kind: NodeKind,
    pub status: NodeStatus,
}

impl Node {
    pub fn open(kind: NodeKind) -> Self {
        Node { kind, status: NodeStatus::Open }
    }

    pub fn closed(kind: NodeKind) -> Self {
        Node { kind, status: NodeStatus::Closed }
    }

    /// Cycle 의 시작 자리.
    ///
    /// 경계 표식이라 여닫는 대상이 아니다 — 첫 Define 은 언제나 여기서 갈라진다.
    pub fn cycle_entry() -> Self {
        Node { kind: NodeKind::CycleEntry, status: NodeStatus::Closed }
    }

    pub fn is_closed(self) -> bool {
        self.status == NodeStatus::Closed
    }
}
