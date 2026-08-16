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
//! 계보는 **읽기만** 한다([`Walk::lineage`]) — `parent` 사슬을 뿌리부터 훑을 뿐,
//! 자리를 옮기지 않는다.
//!
//! [`Walk::revisit`] 은 닫힌 Outcome 에 **이미 확정된** 되돌아감을 실행한다. 갈 곳을 새로
//! 고르는 것이 아니라 적혀 있는 것을 밟는 것이고, 그래서 근거와 이동이 떨어지지 않는다.
//! 되돌아온 자리에서는 **새 가설만** 열린다 — 갈래는 언제나 가설에서 시작한다.
//! 그렇게 난 첫 가설은 제 출처([`StepNode::revisit_from`])를 지닌다 — 어느 결정이 이 갈래를
//! 낳았는지를 실행 순서에서 되짚지 않기 위해서다.
//!
//! 아직 없는 것: 임의 이동 · 저장 · Artifact · Journey · Chain · Cycle.

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
    /// 이 Node 가 **되돌아감으로 시작된 갈래의 첫 Node** 라면, 그 갈래를 낳은 Outcome.
    ///
    /// **계보의 변이 아니다.** [`Walk::lineage`] 는 이것을 절대 타지 않는다 —
    /// 두 번째 부모로 읽으면 버린 갈래가 계보에 섞인다.
    ///
    /// 태어날 때 한 번 정해지고 바뀌지 않으며, 자손에게 전파되지 않는다.
    /// 평범하게 이어 걸어 난 Node 는 `None` 이다.
    pub revisit_from: Option<NodeId>,
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
    /// 되돌아온 직후, 아직 새 가설을 열지 않았다면 **어디에서 되돌아왔는지**.
    ///
    /// GIL 의 개념이 아니라 이 걷기의 **실행 상태**다 — 새 갈래의 첫 Node 가 가설이 되도록
    /// 붙잡아 두는 자리이고, 그 가설이 열리는 순간 풀린다.
    pending_revisit: Option<NodeId>,
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
            pending_revisit: None,
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

        // 되돌아온 직후에는 새 가설만 연다. 문법은 여기서 다른 것도 허락하지만
        // (되돌아간 자리가 Analysis 라면 Outcome 도 열린다), 되돌아간 뜻이 그것이 아니다.
        if self.pending_revisit.is_some() && kind != NodeKind::Hypothesis {
            return Err(WalkError::ExpectedHypothesis { opened: kind });
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
            // 되돌아옴이 걸려 있는 동안 열리는 것은 새 갈래의 첫 가설뿐이다(위에서 막았다).
            // 그 자리에서만 출처가 남고, 바로 아래 줄에서 실행 상태는 풀린다.
            revisit_from: self.pending_revisit,
            status: NodeStatus::Open,
            report: None,
        });
        self.current = Some(id);
        self.pending_revisit = None; // 새 갈래가 시작됐다.
        Ok(())
    }

    /// 지금 자리에 **확정되어 있는** 되돌아감을 실행한다.
    ///
    /// 어디로 갈지는 부르는 쪽이 고르지 않는다 — 닫힌 Outcome 의 Report 에 이미 적혀 있고,
    /// 그래서 *왜 그리로 갔는가* 와 실제 이동이 떨어지지 않는다.
    ///
    /// 그래프는 한 글자도 바뀌지 않는다. 바뀌는 것은 **서 있는 자리**와, 다음 한 번은 새
    /// 가설이어야 한다는 실행 상태뿐이다.
    pub fn revisit(&mut self) -> Result<(), WalkError> {
        if self.finished {
            return Err(WalkError::AlreadyFinished);
        }

        let source = self.current.ok_or(WalkError::NothingToRevisit)?;
        let target = {
            let node = self
                .node(source)
                .expect("current 는 언제나 실재하는 Node 를 가리킨다");

            // 되돌아감은 닫힌 자리에서만 시작한다.
            if node.status != NodeStatus::Closed {
                return Err(WalkError::NothingToRevisit);
            }
            let report = node.report.as_ref().ok_or(WalkError::NothingToRevisit)?;

            // 여기에 되돌아가겠다는 결정이 적혀 있는가. 적혀 있지 않으면 실행할 것이 없다.
            if report.get(NEXT_ACTION) != Some(ACTION_REVISIT) {
                return Err(WalkError::NothingToRevisit);
            }

            // 갈 곳의 구조적 적법성(조상인가·거기서 가설을 열 수 있는가)은 이 Outcome 을
            // 닫을 때 이미 봤다. 여기서는 **실행에 필요한 것만** 다시 본다 —
            // 그 이름이 실재하고 여전히 닫혀 있는가.
            let target = report.get(NEXT_TARGET).ok_or(NextDirectionError::TargetMissing)?;
            let target: NodeId = target
                .parse::<u32>()
                .map(NodeId)
                .map_err(|_| NextDirectionError::TargetUnreadable(target.to_string()))?;
            let target_node = self
                .node(target)
                .ok_or(NextDirectionError::UnknownTarget(target))?;
            if target_node.status != NodeStatus::Closed {
                return Err(NextDirectionError::TargetIsOpen(target).into());
            }
            target
        };

        self.current = Some(target);
        self.pending_revisit = Some(source);
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
        self.check_next_direction(id, &report)?;

        self.nodes[at].status = NodeStatus::Closed;
        self.nodes[at].report = Some(report);
        Ok(())
    }

    /// Report 가 적어 둔 다음 방향이 **이 그래프에서 구조적으로 가능한가**.
    ///
    /// 문법은 어떤 칸이 있어야 하고 어떤 값이 올 수 있는지까지만 안다.
    /// `target_node_id` 는 이 걷기 안에서만 뜻이 있는 이름이라 여기서 본다.
    ///
    /// 고른 target 이 **옳은가**는 보지 않는다 — 그건 계보를 읽은 Agent 의 판단이다.
    fn check_next_direction(&self, source: NodeId, report: &Report) -> Result<(), WalkError> {
        let Some(action) = report.get(NEXT_ACTION) else {
            return Ok(()); // 이 Kind 는 다음 방향을 적지 않는다.
        };
        let target = report.get(NEXT_TARGET);

        if action != ACTION_REVISIT {
            // 되돌아가지 않는 방향에는 갈 곳이 없어야 한다.
            return match target {
                Some(_) => Err(NextDirectionError::TargetNotAllowed(action.to_string()).into()),
                None => Ok(()),
            };
        }

        let Some(target) = target else {
            return Err(NextDirectionError::TargetMissing.into());
        };
        let target: NodeId = target
            .parse::<u32>()
            .map(NodeId)
            .map_err(|_| NextDirectionError::TargetUnreadable(target.to_string()))?;

        // ① 이 그래프에 있는 Node 인가
        let node = self
            .node(target)
            .ok_or(NextDirectionError::UnknownTarget(target))?;

        // ② 닫혀 있는가 — 되돌아갈 곳은 확정된 자리여야 한다
        if node.status != NodeStatus::Closed {
            return Err(NextDirectionError::TargetIsOpen(target).into());
        }

        // ③ 지금 자리의 조상인가 (자기 자신은 조상이 아니다)
        let lineage = self.lineage(source)?;
        let is_ancestor = lineage
            .iter()
            .filter(|node| node.id != source)
            .any(|node| node.id == target);
        if !is_ancestor {
            return Err(NextDirectionError::TargetNotAnAncestor(target).into());
        }

        // ④ 거기서 새 가설을 열 수 있는가 — 갈래는 언제나 Hypothesis 에서 시작한다
        if self
            .rules
            .validate_open(Node::closed(node.kind), NodeKind::Hypothesis)
            .is_err()
        {
            return Err(NextDirectionError::TargetCannotBranch {
                target,
                kind: node.kind,
            }
            .into());
        }

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

    /// 이 Node 까지의 **구조적 계보**를 뿌리부터 차례로 본다.
    ///
    /// `parent` 사슬만 따라간다 — 만든 순서도, 형제 가지도, Journey 도 아니다.
    /// 읽기만 하므로 걷기의 어떤 값도 바뀌지 않고, **열려 있는 Node 도 볼 수 있다**
    /// (그 자리는 `status = Open`·`report = None` 인 채로 그대로 보인다).
    pub fn lineage(&self, target: NodeId) -> Result<Vec<&StepNode>, WalkError> {
        let mut path = Vec::new();
        let mut cursor = Some(target);

        while let Some(id) = cursor {
            let node = self.node(id).ok_or(WalkError::UnknownNode(id))?;
            path.push(node);
            cursor = node.parent;

            // 부모는 언제나 자신보다 먼저 난 Node 라 사슬은 반드시 끝난다.
            // 그래도 돌아 나가지 못하는 일이 없도록 길이로 못을 박는다.
            assert!(
                path.len() <= self.nodes.len(),
                "parent 사슬이 Node 수보다 길다 — 이 Step Graph 에 순환이 있다"
            );
        }

        path.reverse();
        Ok(path)
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

/// Report 가 다음 방향을 적을 때 쓰는 칸 이름.
///
/// 문법(`gil-spec.yaml`)이 어떤 Kind 가 이 칸들을 요구하는지 정한다. 여기서는 그 값을
/// 이 걷기의 자리로 옮겨 읽기 위해 이름만 안다.
const NEXT_ACTION: &str = "next_direction.action";
const NEXT_TARGET: &str = "next_direction.target_node_id";
const ACTION_REVISIT: &str = "revisit";

/// 적어 둔 다음 방향이 이 그래프에서 성립하지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NextDirectionError {
    /// 되돌아가겠다면서 갈 곳을 적지 않았다.
    TargetMissing,
    /// 되돌아가지 않는 방향인데 갈 곳을 적었다.
    TargetNotAllowed(String),
    /// 갈 곳이 Node 이름으로 읽히지 않는다.
    TargetUnreadable(String),
    /// 이 그래프에 없는 Node 다.
    UnknownTarget(NodeId),
    /// 아직 열려 있는 자리로는 되돌아갈 수 없다.
    TargetIsOpen(NodeId),
    /// 지금 자리의 조상이 아니다 — 형제·자손·무관한 Node 로는 되돌아갈 수 없다.
    TargetNotAnAncestor(NodeId),
    /// 거기서는 새 가설을 열 수 없다.
    TargetCannotBranch { target: NodeId, kind: NodeKind },
}

impl fmt::Display for NextDirectionError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            NextDirectionError::TargetMissing => write!(
                f,
                "{ACTION_REVISIT} 인데 {NEXT_TARGET} 이(가) 없다 — 어디로 돌아갈지 적어야 한다"
            ),
            NextDirectionError::TargetNotAllowed(action) => write!(
                f,
                "{action:?} 에는 {NEXT_TARGET} 을(를) 적을 수 없다 — 돌아갈 자리가 없는 방향이다"
            ),
            NextDirectionError::TargetUnreadable(value) => {
                write!(f, "{NEXT_TARGET} 의 {value:?} 는 Node 이름으로 읽히지 않는다")
            }
            NextDirectionError::UnknownTarget(target) => {
                write!(f, "{target} 은(는) 이 Step Graph 에 없는 Node 다")
            }
            NextDirectionError::TargetIsOpen(target) => write!(
                f,
                "{target} 은(는) 아직 열려 있다 — 확정된 자리로만 되돌아갈 수 있다"
            ),
            NextDirectionError::TargetNotAnAncestor(target) => write!(
                f,
                "{target} 은(는) 지금 자리의 조상이 아니다 — 걸어온 길 위의 자리로만 되돌아간다"
            ),
            NextDirectionError::TargetCannotBranch { target, kind } => write!(
                f,
                "{target} 은(는) {kind} 라 새 가설을 열 수 없다 — 갈래는 언제나 가설에서 시작한다"
            ),
        }
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
    /// 이 Step Graph 에 그런 이름의 Node 가 없다.
    UnknownNode(NodeId),
    /// Report 가 적어 둔 다음 방향이 이 그래프에서 성립하지 않는다.
    NextDirection(NextDirectionError),
    /// 지금 자리에는 실행할 되돌아감이 적혀 있지 않다.
    NothingToRevisit,
    /// 되돌아온 직후인데 새 가설이 아닌 것을 열려 했다.
    ExpectedHypothesis { opened: NodeKind },
}

impl From<GrammarError> for WalkError {
    fn from(err: GrammarError) -> Self {
        WalkError::Grammar(err)
    }
}

impl From<NextDirectionError> for WalkError {
    fn from(err: NextDirectionError) -> Self {
        WalkError::NextDirection(err)
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
            WalkError::UnknownNode(id) => {
                write!(f, "{id} 은(는) 이 Step Graph 에 없는 Node 다")
            }
            WalkError::NextDirection(err) => write!(f, "{err}"),
            WalkError::NothingToRevisit => write!(
                f,
                "지금 자리에 실행할 되돌아감이 없다 — 되돌아가겠다고 적어 둔 \
                 닫힌 Outcome 에 서 있어야 한다"
            ),
            WalkError::ExpectedHypothesis { opened } => write!(
                f,
                "되돌아온 자리에서는 새 가설만 열 수 있다 — {opened} 이(가) 아니라 hypothesis 다"
            ),
        }
    }
}

impl std::error::Error for WalkError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            WalkError::Grammar(err) => Some(err),
            WalkError::NextDirection(err) => Some(err),
            WalkError::NothingToClose
            | WalkError::AlreadyFinished
            | WalkError::UnknownNode(_)
            | WalkError::NothingToRevisit
            | WalkError::ExpectedHypothesis { .. } => None,
        }
    }
}

impl std::error::Error for NextDirectionError {}
