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
//! [`Walk::restore`] 는 저장에서 되살릴 때만 쓰는 문이다. 그리로 들어온 값은 **걸어서 만든
//! 것이 아니므로** 불변식을 처음부터 다시 잰다 — 자세한 것은 [`Walk::check_restored`] 에 있다.
//!
//! 아직 없는 것: 임의 이동 · Artifact · Journey · Chain · Cycle.

use std::fmt;

use crate::cycle::CycleKind;
use crate::refs::{CycleRef, ExistenceRef, JourneyRef, RefSyntaxError, StepRef};
use crate::cycles::CycleId;
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

impl NodeId {
    /// 저장이 파일에 적힌 수를 이름으로 되돌릴 때만 쓴다.
    ///
    /// 이 문으로 만든 이름은 **아직 아무것도 보증하지 않는다** — 실재하는지는
    /// [`Walk::check_restored`] 가 판정한다.
    pub(crate) fn from_raw(raw: u32) -> Self {
        NodeId(raw)
    }

    /// 저장이 이름을 파일에 적을 때만 쓴다.
    pub(crate) fn raw(self) -> u32 {
        self.0
    }
}

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
    /// **누가 이 Node 를 열었는가.** Open 시 Current Existence 로 고정되고 lifetime 동안
    /// 바뀌지 않는다(Node Model §2). 연 Existence 만 이 Node 를 닫을 수 있다.
    pub existence: ExistenceRef,
    /// **어느 Journey 판에서 닫았는가.** Close 시 확정된다.
    ///
    /// 열려 있는 동안은 `None` 이다 — 아직 닫지 않은 것에 닫은 판을 적어 둘 수 없다.
    pub journey: Option<JourneyRef>,
    /// 닫히면서 받는다. 열려 있는 동안은 `None`.
    pub report: Option<Report>,
}

impl StepNode {
    /// 이 Node 가 닫혔는가. 상태의 뜻은 이 크레이트가 정한다 — 밖에서 다시 정하지 않게.
    pub fn is_closed(&self) -> bool {
        self.status == NodeStatus::Closed
    }
}

/// 저장이 되살려 온 걷기의 값들 — [`Walk::restore`] 의 입구.
///
/// **저장 형식이 아니라 걷기의 상태다.** 디스크에 어떤 꼴로 눕는지는 `store` 만 안다.
pub(crate) struct WalkState {
    pub nodes: Vec<StepNode>,
    pub current: Option<NodeId>,
    pub next_id: u32,
    pub pending_revisit: Option<NodeId>,
}

/// 한 Cycle 안의 Step 을 걸어 온 자리.
#[derive(Debug, Clone)]
pub struct Walk {
    rules: RuleSet,
    /// **어느 Cycle 의 Step Graph 인가.**
    ///
    /// Step 의 이름은 이 걷기 안에서만 유일하고, 영구 주소는 `step:C2/S3` 처럼 소속 Cycle 을
    /// 함께 지닌다(Node Model §2.1). 그 주소를 읽고 쓰는 자리가 여기이므로, 걷기는 제가 어느
    /// Cycle 에 담겼는지 알아야 한다.
    cycle: CycleRef,
    /// **어느 Cycle Kind 의 문법을 따르는가.**
    ///
    /// Interview 와 Experiment 는 열 수 있는 Step 이 다르고, 같은 `outcome` 도 요구하는
    /// Report 가 다르다.
    kind: CycleKind,
    /// **이 Cycle 을 연 존재.** 안에서 나는 Step 은 모두 같은 주인을 지닌다 — 열린 Cycle 이
    /// 있는 동안 존재를 바꿀 수 없으므로(Existence Model §7), Cycle 하나의 Step 들이
    /// 서로 다른 주인을 갖는 상태는 걸어서 만들 수 없다.
    existence: ExistenceRef,
    nodes: Vec<StepNode>,
    current: Option<NodeId>,
    next_id: u32,
    /// 되돌아온 직후, 아직 새 가설을 열지 않았다면 **어디에서 되돌아왔는지**.
    ///
    /// GIL 의 개념이 아니라 이 걷기의 **실행 상태**다 — 새 갈래의 첫 Node 가 가설이 되도록
    /// 붙잡아 두는 자리이고, 그 가설이 열리는 순간 풀린다.
    pending_revisit: Option<NodeId>,
}

impl Walk {
    /// Cycle 의 시작 경계에 선다. 아직 아무 Node 도 없다.
    pub fn start(rules: RuleSet, cycle: CycleRef, kind: CycleKind, existence: ExistenceRef) -> Self {
        Walk {
            rules,
            cycle,
            kind,
            existence,
            nodes: Vec::new(),
            current: None,
            next_id: 1,
            pending_revisit: None,
        }
    }

    /// 저장이 읽어 온 값으로 걷기를 다시 세운다.
    ///
    /// **이 값들은 걸어서 만들어진 것이 아니다.** 파일은 [`Walk`] 의 메서드를 거치지 않는
    /// **두 번째 통로**이고, 손으로 고칠 수 있다. 그래서 여기서 불변식을 처음부터 다시 잰다 —
    /// 통과하지 못하면 걷기는 태어나지 않는다.
    pub(crate) fn restore(
        rules: RuleSet,
        cycle: CycleRef,
        kind: CycleKind,
        existence: ExistenceRef,
        state: WalkState,
    ) -> Result<Walk, RestoreError> {
        let walk = Walk {
            rules,
            cycle,
            kind,
            existence,
            nodes: state.nodes,
            current: state.current,
            next_id: state.next_id,
            pending_revisit: state.pending_revisit,
        };
        walk.check_restored()?;
        Ok(walk)
    }

    /// 되살아난 값이 **걸어서 만들 수 있는 것**인지 판정한다.
    ///
    /// 재는 것은 걷기가 스스로 지키는 불변식뿐이다. 문법은 [`RuleSet`] 에게 다시 묻고,
    /// 다음 방향은 [`Walk::check_next_direction`] 에게 다시 묻는다 — 판정은 한 자리에서만 난다.
    fn check_restored(&self) -> Result<(), RestoreError> {
        let mut seen: Vec<NodeId> = Vec::with_capacity(self.nodes.len());

        for node in &self.nodes {
            if seen.contains(&node.id) {
                return Err(RestoreError::DuplicateNode(node.id));
            }
            // 이름은 발급된 것이어야 한다 — next_id 보다 크면 다음 Node 가 이름을 훔친다.
            if node.id.raw() >= self.next_id {
                return Err(RestoreError::NameBeyondNextId {
                    node: node.id,
                    next_id: self.next_id,
                });
            }

            // Step 으로 실린 것은 Step Kind 여야 한다. 경계 표식은 지나가는 자리지
            // 기록에 남는 Node 가 아니다 — 실려 있으면 그 파일은 걷기가 만든 것이 아니다.
            if !self.rules.declares(self.kind, node.kind) {
                return Err(RestoreError::NotAStepKind {
                    node: node.id,
                    kind: node.kind,
                });
            }

            // 부모는 **먼저 난 Node** 여야 한다. 이 한 줄이 순환을 원리적으로 막는다.
            let parent = match node.parent {
                None => Node::cycle_entry(),
                Some(parent) => {
                    if !seen.contains(&parent) {
                        return Err(RestoreError::ParentNotEarlier {
                            node: node.id,
                            parent,
                        });
                    }
                    let parent = self.node(parent).expect("방금 앞에서 본 Node 다");
                    // 부모의 상태를 그대로 넘긴다 — 닫힌 척 물으면 거짓 통과가 난다.
                    Node {
                        kind: parent.kind,
                        status: parent.status,
                    }
                }
            };
            // 경계 표식이 Step 으로 실려 있으면 여기서 걸린다(제 규칙이 없어 전이가 없다).
            self.rules
                .validate_open(self.kind, parent, node.kind)
                .map_err(|source| RestoreError::Grammar {
                    node: node.id,
                    source,
                })?;

            if let Some(from) = node.revisit_from {
                // 갈래의 첫 Node 는 언제나 가설이다.
                if node.kind != NodeKind::Hypothesis {
                    return Err(RestoreError::RevisitFromOnNonHypothesis {
                        node: node.id,
                        kind: node.kind,
                    });
                }
                if !seen.contains(&from) {
                    return Err(RestoreError::RevisitFromNotEarlier {
                        node: node.id,
                        from,
                    });
                }
                if self.node(from).expect("방금 앞에서 본 Node 다").status != NodeStatus::Closed {
                    return Err(RestoreError::RevisitFromOpen {
                        node: node.id,
                        from,
                    });
                }
            }

            // 닫힌 Node 는 **어느 판에서 닫았는지**를 지닌다. 열린 Node 는 아직 닫지
            // 않았으니 그 자리가 비어 있어야 한다(Node Model §2).
            match (node.status, node.journey) {
                (NodeStatus::Closed, None) => {
                    return Err(RestoreError::ClosedWithoutJourney(node.id));
                }
                (NodeStatus::Open, Some(journey)) => {
                    return Err(RestoreError::JourneyOnOpenNode {
                        node: node.id,
                        journey,
                    });
                }
                _ => {}
            }
            // 한 Cycle 의 Step 은 모두 그 Cycle 의 주인을 지닌다.
            if node.existence != self.existence {
                return Err(RestoreError::StepOfAnotherExistence {
                    node: node.id,
                    owner: node.existence,
                    cycle: self.existence,
                });
            }

            match (node.status, &node.report) {
                (NodeStatus::Open, Some(_)) => {
                    return Err(RestoreError::ReportOnOpenNode(node.id));
                }
                (NodeStatus::Closed, None) => {
                    return Err(RestoreError::ClosedWithoutReport(node.id));
                }
                (NodeStatus::Closed, Some(report)) => {
                    self.rules.validate_close(self.kind, node.kind, report).map_err(|source| {
                        RestoreError::Grammar {
                            node: node.id,
                            source,
                        }
                    })?;
                }
                (NodeStatus::Open, None) => {
                    // 열린 Node 아래로는 아무것도 열 수 없으니, 열린 것은 서 있는 자리뿐이다.
                    if self.current != Some(node.id) {
                        return Err(RestoreError::OpenNodeNotCurrent {
                            node: node.id,
                            current: self.current,
                        });
                    }
                }
            }

            seen.push(node.id);
        }

        if let Some(current) = self.current
            && self.node(current).is_none()
        {
            return Err(RestoreError::UnknownCurrent(current));
        }

        // 다음 방향은 그래프 전체(조상 관계)를 봐야 판정된다 — 전부 실린 뒤에 잰다.
        for node in &self.nodes {
            if let Some(report) = &node.report {
                self.check_next_direction(node.id, report)
                    .map_err(|source| RestoreError::NextDirection {
                        node: node.id,
                        source: Box::new(source),
                    })?;
            }
        }

        if let Some(pending) = self.pending_revisit {
            let source = self
                .node(pending)
                .ok_or(RestoreError::UnknownPendingRevisit(pending))?;
            // 되돌아옴은 **적힌 것을 밟은** 결과다. 그 자리에 그 결정이 없으면 위조다.
            let declared = source
                .report
                .as_ref()
                .and_then(|report| declared_revisit_target(report, self.cycle).ok())
                .flatten();
            if declared.is_none() || declared != self.current {
                return Err(RestoreError::PendingRevisitNotDeclared {
                    pending,
                    current: self.current,
                });
            }
        }

        Ok(())
    }

    /// 지금 자리에서 다음 Node 를 연다.
    ///
    /// 새 Node 의 부모는 **여는 그 순간의 `current`** 이고, 그대로 기록된다.
    ///
    /// 경계(`cycle_entry`·`cycle_exit`)는 열리지 않는다 — Step 이 아니라 Cycle 의 자리이고,
    /// 그 자리를 지나는 것은 Cycle 을 닫는 행위다.
    pub fn open(&mut self, kind: NodeKind) -> Result<(), WalkError> {
        if kind.is_boundary() {
            return Err(WalkError::BoundaryIsNotAStep { kind });
        }

        // 되돌아온 직후에는 새 가설만 연다. 문법은 여기서 다른 것도 허락하지만
        // (되돌아간 자리가 Analysis 라면 Outcome 도 열린다), 되돌아간 뜻이 그것이 아니다.
        if self.pending_revisit.is_some() && kind != NodeKind::Hypothesis {
            return Err(WalkError::ExpectedHypothesis { opened: kind });
        }

        // 판정이 먼저다 — 거절되면 Node 도, 이름도 생기지 않는다.
        self.rules.validate_open(self.kind, self.here(), kind)?;

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
            // Open 시 고정되는 주인. 이 걷기가 담긴 Cycle 의 주인과 같다.
            existence: self.existence,
            // 닫은 판은 아직 없다 — 닫을 때 [`Walk::record_journey`] 가 적는다.
            journey: None,
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
            let Some(target) = declared_revisit_target(report, self.cycle)? else {
                return Err(WalkError::NothingToRevisit);
            };

            // 갈 곳의 구조적 적법성(조상인가·거기서 가설을 열 수 있는가)은 이 Outcome 을
            // 닫을 때 이미 봤다. 여기서는 **실행에 필요한 것만** 다시 본다 —
            // 그 이름이 실재하고 여전히 닫혀 있는가.
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
        let Some(id) = self.current else {
            return Err(WalkError::NothingToClose);
        };
        let at = self
            .position_of(id)
            .expect("current 는 언제나 실재하는 Node 를 가리킨다");
        if self.nodes[at].status != NodeStatus::Open {
            return Err(WalkError::NothingToClose);
        }

        self.rules.validate_close(self.kind, self.nodes[at].kind, &report)?;
        self.check_next_direction(id, &report)?;

        self.nodes[at].status = NodeStatus::Closed;
        self.nodes[at].report = Some(report);
        Ok(())
    }

    /// 방금 닫은 자리에 **어느 판에서 닫았는지**를 새긴다.
    ///
    /// 판은 Journey 쪽의 것이라 걷기가 스스로 알 수 없다. 그래서 이 문은
    /// [`Project`](crate::Project) 의 통합 transaction 에만 열려 있고, 닫은 직후에만 부른다 —
    /// Report·Closed·판이 한 save 에 함께 들어가야 하기 때문이다(Existence Model §4).
    pub(crate) fn record_journey(&mut self, id: NodeId, journey: JourneyRef) {
        if let Some(at) = self.position_of(id) {
            self.nodes[at].journey = Some(journey);
        }
    }

    /// 이 걷기를 연 존재.
    pub fn existence(&self) -> ExistenceRef {
        self.existence
    }

    /// Report 가 적어 둔 다음 방향이 **이 그래프에서 구조적으로 가능한가**.
    ///
    /// 문법은 어떤 칸이 있어야 하고 어떤 값이 올 수 있는지까지만 안다.
    /// `target_node_ref` 는 이 Cycle 안에서만 뜻이 있는 주소라 여기서 본다.
    ///
    /// 고른 target 이 **옳은가**는 보지 않는다 — 그건 계보를 읽은 Agent 의 판단이다.
    fn check_next_direction(&self, source: NodeId, report: &Report) -> Result<(), WalkError> {
        let Some(target) = declared_revisit_target(report, self.cycle)? else {
            return Ok(()); // 되돌아가는 방향이 아니다 — 볼 자리가 없다.
        };

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
            .validate_open(self.kind, Node::closed(node.kind), NodeKind::Hypothesis)
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

    /// **지금 실제로 열 수 있는** 종류들.
    ///
    /// 문법이 허락하는 것과 다르다. 문법은 자리만 보지만 여는 것은 자리 말고도 걷기의
    /// 실행 상태를 본다 — 되돌아온 직후에는 새 가설뿐이고, 열려 있는 자리 아래로는
    /// 아무것도 열리지 않으며, 끝 경계를 지났으면 아무것도 열리지 않는다.
    ///
    /// **이 목록과 [`Walk::open`] 은 반드시 같은 답을 해야 한다.** 갈리면 안내를 믿은
    /// Agent 가 한 번 실패하고서야 옳은 수를 알게 된다(실사용 보고 #123 이 그것이다).
    /// 그래서 여기서 규칙을 다시 쓰지 않고, **열어 보고 되돌리는 방식으로** 답한다 —
    /// 판정은 언제나 [`Walk::open`] 한 곳에서만 난다.
    pub fn openable_here(&self) -> Vec<NodeKind> {
        NodeKind::ALL
            .into_iter()
            .filter(|kind| {
                // 걷기를 복제해서 실제로 열어 본다. 원본은 한 글자도 바뀌지 않는다.
                self.clone().open(*kind).is_ok()
            })
            .collect()
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

    /// 이 걷기가 **끝 경계에 닿았는가** — 여기서 Cycle 을 닫을 수 있는가.
    ///
    /// 걷기 자신은 끝났는지 모른다. 끝냈다는 사실은 Cycle 이 갖는다([`Cycle::status`]).
    /// 여기서 답하는 것은 자리뿐이고, 그 판정은 문법에게 묻는다.
    ///
    /// [`Cycle::status`]: crate::Cycle::status
    pub fn at_exit(&self) -> bool {
        self.rules
            .validate_open(self.kind, self.here(), NodeKind::CycleExit)
            .is_ok()
    }

    /// 이 걷기가 따르는 Grammar.
    pub fn rules(&self) -> &RuleSet {
        &self.rules
    }

    /// 이 걷기가 어느 Cycle Kind 의 문법을 따르는가.
    pub fn kind(&self) -> CycleKind {
        self.kind
    }

    /// 이 걷기가 담긴 Cycle.
    pub fn cycle(&self) -> CycleRef {
        self.cycle
    }

    /// 이 걷기 안의 Step 을 가리키는 **영구 주소** — `step:C2/S3`.
    pub fn step_ref(&self, step: NodeId) -> StepRef {
        StepRef::new(self.cycle, step.raw()).expect("발급된 Step 이름은 1 부터 센다")
    }

    /// 아직 아무에게도 주지 않은 다음 이름 — 저장이 적어 두기 위해 읽는다.
    ///
    /// 이름을 되계산하지 않고 그대로 싣는다. 남은 이름은 지금까지 무엇이 났는지의 결과지
    /// 실린 Node 로부터 다시 셀 수 있는 값이 아니다.
    ///
    /// **다만 지금은 그 차이를 잴 수 없다.** 이름은 판정을 통과한 뒤에만 발급되고 Node 는
    /// 사라지지 않아서, `next_id` 는 언제나 `가장 큰 이름 + 1` 이다 — 다시 세는 구현과
    /// 관측상 같다(돌연변이가 아무 시험도 못 빨갛게 만들었다, 2026-08-17).
    ///
    /// **언제 재게 되는가**: 이름이 소모되는 일이 생기는 순간 갈라진다 —
    /// 발급 뒤에 실패하는 경로 · Node 를 지우는 연산 · 여러 걷기가 이름을 나눠 갖는 경우.
    /// 그중 하나를 짓는 Step 에서 이 규칙을 함께 재라.
    pub(crate) fn next_id(&self) -> u32 {
        self.next_id
    }

    /// 되돌아온 직후인가 — 그렇다면 어디에서 왔는지. 저장이 읽는다.
    ///
    /// 이 값이 파일에 안 실리면 "되돌아온 뒤엔 가설만" 이라는 규칙이 프로세스 경계에서 증발한다.
    pub(crate) fn pending_revisit(&self) -> Option<NodeId> {
        self.pending_revisit
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
const NEXT_TARGET: &str = "next_direction.target_node_ref";
const ACTION_REVISIT: &str = "revisit";

/// 이 Report 가 **되돌아가겠다고 적었다면** 그 갈 곳의 이름.
///
/// `Ok(None)` 은 되돌아가는 방향이 아니라는 뜻이다 — 다음 방향을 아예 안 적는 Kind 도,
/// 되돌아가지 않겠다고 적은 Report 도 여기로 온다.
///
/// **Report 에서 다음 방향을 읽는 자리는 여기 하나뿐이다.** 닫을 때·실행할 때·저장에서
/// 되살릴 때가 같은 읽기를 쓴다 — 세 자리에 따로 적으면 한 자리가 낡는다.
fn declared_revisit_target(
    report: &Report,
    cycle: CycleRef,
) -> Result<Option<NodeId>, NextDirectionError> {
    let Some(action) = report.get(NEXT_ACTION) else {
        return Ok(None); // 이 Kind 는 다음 방향을 적지 않는다.
    };
    let target = report.get(NEXT_TARGET);

    if action != ACTION_REVISIT {
        // 되돌아가지 않는 방향에는 갈 곳이 없어야 한다.
        return match target {
            Some(_) => Err(NextDirectionError::TargetNotAllowed(action.to_string())),
            None => Ok(None),
        };
    }

    let Some(raw) = target else {
        return Err(NextDirectionError::TargetMissing { cycle });
    };
    let target: StepRef = raw
        .parse()
        .map_err(|source| NextDirectionError::TargetUnreadable {
            value: raw.to_string(),
            source,
            suggestion: suggest(raw, cycle),
        })?;
    if target.cycle() != cycle {
        return Err(NextDirectionError::TargetOtherCycle { target, cycle });
    }
    Ok(Some(NodeId::from_raw(target.step())))
}

/// 잘못 적은 값에서 **올바른 전체 주소**를 지어 준다.
///
/// `4` · `#4` · `S4` 는 전부 같은 것을 가리키려던 것이다. 무엇이 틀렸는지만 말하고 무엇을
/// 적어야 하는지 말하지 않으면 사람은 한 번 더 틀린다.
fn suggest(raw: &str, cycle: CycleRef) -> String {
    let digits: String = raw.chars().filter(char::is_ascii_digit).collect();
    match digits.parse::<u32>().ok().and_then(|n| StepRef::new(cycle, n)) {
        Some(step) => step.to_string(),
        None => format!("step:{}/S<번호>", cycle.id()),
    }
}

/// 적어 둔 다음 방향이 이 그래프에서 성립하지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum NextDirectionError {
    /// 되돌아가겠다면서 갈 곳을 적지 않았다.
    TargetMissing { cycle: CycleRef },
    /// 되돌아가지 않는 방향인데 갈 곳을 적었다.
    TargetNotAllowed(String),
    /// 갈 곳이 Step 주소로 읽히지 않는다 — bare `4` · 화면 축약 `#4` · `S4` 가 여기로 온다.
    TargetUnreadable {
        value: String,
        source: RefSyntaxError,
        suggestion: String,
    },
    /// 다른 Cycle 의 Step 을 가리킨다.
    TargetOtherCycle { target: StepRef, cycle: CycleRef },
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
            NextDirectionError::TargetMissing { cycle } => write!(
                f,
                "{ACTION_REVISIT} 인데 {NEXT_TARGET} 이(가) 없다 — 어디로 돌아갈지 적어야 한다.\n\
                 꼴: {NEXT_TARGET}: step:{}/S<번호>",
                cycle.id()
            ),
            NextDirectionError::TargetNotAllowed(action) => write!(
                f,
                "{action:?} 에는 {NEXT_TARGET} 을(를) 적을 수 없다 — 돌아갈 자리가 없는 방향이다"
            ),
            NextDirectionError::TargetUnreadable {
                value,
                source,
                suggestion,
            } => write!(
                f,
                "{NEXT_TARGET} 의 {value:?} 는 Step 주소로 읽히지 않는다 — {source}.\n\
                 여기 적을 것: {NEXT_TARGET}: {suggestion}"
            ),
            NextDirectionError::TargetOtherCycle { target, cycle } => write!(
                f,
                "{NEXT_TARGET} 가 {target} 을(를) 가리키는데 그것은 다른 Cycle 의 자리다 — \
                 되돌아감은 이 Cycle 안에서만 성립한다.\n\
                 여기 적을 것: {NEXT_TARGET}: step:{}/S<번호>",
                cycle.id()
            ),
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
    /// 경계를 Step 으로 열려 했다.
    BoundaryIsNotAStep { kind: NodeKind },
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
            WalkError::BoundaryIsNotAStep { kind } => write!(
                f,
                "{kind} 은(는) Step 이 아니라 Cycle 의 경계다 — 여는 것이 아니라 지나가는 자리다"
            ),
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
            | WalkError::BoundaryIsNotAStep { .. }
            | WalkError::UnknownNode(_)
            | WalkError::NothingToRevisit
            | WalkError::ExpectedHypothesis { .. } => None,
        }
    }
}

impl std::error::Error for NextDirectionError {}

/// 저장에서 되살린 값이 **걸어서 만들 수 있는 것이 아닌** 이유.
///
/// 전부 "걷기라면 절대 만들지 않는 꼴"이다. 그래서 이 오류가 났다는 것은 파일이
/// 걷기 밖에서 고쳐졌거나 형식이 어긋났다는 뜻이다.
#[derive(Debug)]
pub enum RestoreError {
    /// 같은 이름이 두 번 실렸다.
    DuplicateNode(NodeId),
    /// 아직 발급되지 않은 이름을 쓰고 있다 — 다음 Node 가 같은 이름을 받게 된다.
    NameBeyondNextId { node: NodeId, next_id: u32 },
    /// Step 이 아닌 것이 Step 으로 실렸다.
    NotAStepKind { node: NodeId, kind: NodeKind },
    /// 부모가 저보다 먼저 나지 않았다 — 없는 Node 이거나, 뒤에 난 Node 다.
    ParentNotEarlier { node: NodeId, parent: NodeId },
    /// 문법이 거절했다 — 이 자리에서 날 수 없는 Node 이거나, 이 Report 로 닫을 수 없다.
    Grammar { node: NodeId, source: GrammarError },
    /// 되돌아감의 출처를 가설이 아닌 Node 가 지녔다.
    RevisitFromOnNonHypothesis { node: NodeId, kind: NodeKind },
    /// 되돌아감의 출처가 저보다 먼저 나지 않았다.
    RevisitFromNotEarlier { node: NodeId, from: NodeId },
    /// 되돌아감의 출처가 아직 열려 있다.
    RevisitFromOpen { node: NodeId, from: NodeId },
    /// 열려 있는 Node 가 Report 를 지녔다.
    ReportOnOpenNode(NodeId),
    /// 닫혔다면서 Report 가 없다.
    ClosedWithoutReport(NodeId),
    /// 닫혔다면서 어느 판에서 닫았는지가 없다.
    ClosedWithoutJourney(NodeId),
    /// 아직 열려 있는데 닫은 판이 적혀 있다.
    JourneyOnOpenNode { node: NodeId, journey: JourneyRef },
    /// 이 Cycle 의 주인이 아닌 존재가 연 Step 이 실려 있다.
    StepOfAnotherExistence {
        node: NodeId,
        owner: ExistenceRef,
        cycle: ExistenceRef,
    },
    /// 서 있는 자리가 아닌데 열려 있다 — 열린 Node 아래로는 아무것도 열 수 없으니
    /// 걷기에 열린 Node 는 서 있는 자리 하나뿐이다.
    OpenNodeNotCurrent {
        node: NodeId,
        current: Option<NodeId>,
    },
    /// 없는 Node 에 서 있다.
    UnknownCurrent(NodeId),
    /// 실린 Report 의 다음 방향이 이 그래프에서 성립하지 않는다.
    NextDirection { node: NodeId, source: Box<WalkError> },
    /// 없는 Node 에서 되돌아왔다고 적혀 있다.
    UnknownPendingRevisit(NodeId),
    /// 되돌아온 상태인데 그 결정이 출처에 적혀 있지 않다 — 밟지 않은 되돌아감이다.
    PendingRevisitNotDeclared {
        pending: NodeId,
        current: Option<NodeId>,
    },
    /// 열려 있는 Cycle 이 Cycle Report 를 지녔다.
    ReportOnOpenCycle,
    /// 닫혔다는 Cycle 에 Cycle Report 가 없다.
    CycleClosedWithoutReport,
    /// 안의 Step Graph 가 끝 경계에 닿지 않았는데 Cycle 이 닫혀 있다.
    CycleClosedTooEarly,
    /// 실린 Cycle Report 가 이 Cycle 안에서 성립하지 않는다.
    CycleReport { source: Box<crate::cycle::CycleError> },
    /// 실린 Step Report 의 참조가 이 Cycle 안에서 성립하지 않는다 — 근거가 딛고 온 길 위에
    /// 없거나, 승인되지 않은 Synthesis 로 success 를 닫아 두었다.
    StepReport {
        step: StepRef,
        source: Box<crate::cycle::CycleError>,
    },

    // ── Cycle Graph 층 ────────────────────────────────────────────────────
    /// Cycle 이 하나도 없다 — 걷기는 언제나 Cycle 하나에서 시작한다.
    NoCycles,
    /// 같은 Cycle 이름이 두 번 실렸다.
    DuplicateCycle(CycleId),
    /// 아직 발급되지 않은 Cycle 이름을 쓰고 있다.
    CycleNameBeyondNextId { cycle: CycleId, next_id: u32 },
    /// 뿌리가 둘이다 — 이 판의 Cycle Graph 는 한 갈래다.
    SecondRoot(CycleId),
    /// 뿌리 Cycle 이 Interview 가 아니다 — 프로젝트의 첫 Cycle 은 Interview 여야 한다.
    RootCycleNotInterview { cycle: CycleId, kind: CycleKind },
    /// 부모가 저보다 먼저 나지 않았다.
    CycleParentNotEarlier { cycle: CycleId, parent: CycleId },
    /// 부모가 자식을 열겠다고 적지 않았다 — 실패한 Cycle 은 자식을 만들지 않는다.
    ParentDidNotOpenAChild {
        cycle: CycleId,
        parent: CycleId,
        declared: Option<String>,
    },
    /// 서 있는 자리가 아닌데 열려 있다 — 한 번에 걷는 Cycle 은 하나다.
    OpenCycleNotCurrent { cycle: CycleId, current: CycleId },
    /// 없는 Cycle 에 서 있다.
    UnknownCurrentCycle(CycleId),
}

/// 자리를 사람이 읽는 꼴로. 아무 데도 서 있지 않은 것도 하나의 자리다.
fn where_at(id: Option<NodeId>) -> String {
    match id {
        Some(id) => id.to_string(),
        None => "시작 경계".to_string(),
    }
}

impl fmt::Display for RestoreError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RestoreError::DuplicateNode(id) => {
                write!(f, "{id} 이(가) 두 번 실렸다 — 이름은 하나의 Node 만 가리킨다")
            }
            RestoreError::NameBeyondNextId { node, next_id } => write!(
                f,
                "{node} 은(는) 아직 발급되지 않은 이름이다 (다음 이름은 #{next_id})"
            ),
            RestoreError::NotAStepKind { node, kind } => {
                write!(f, "{node} 의 {kind} 은(는) Step 이 아니라 지나가는 자리다")
            }
            RestoreError::ParentNotEarlier { node, parent } => write!(
                f,
                "{node} 의 부모 {parent} 이(가) 저보다 먼저 나지 않았다 — 부모는 언제나 앞선다"
            ),
            RestoreError::Grammar { node, source } => write!(f, "{node}: {source}"),
            RestoreError::RevisitFromOnNonHypothesis { node, kind } => write!(
                f,
                "{node} 은(는) {kind} 인데 되돌아감의 출처를 지녔다 — 갈래의 첫 Node 는 가설뿐이다"
            ),
            RestoreError::RevisitFromNotEarlier { node, from } => write!(
                f,
                "{node} 이(가) {from} 에서 났다는데 {from} 이(가) 저보다 먼저 나지 않았다"
            ),
            RestoreError::RevisitFromOpen { node, from } => write!(
                f,
                "{node} 의 출처 {from} 이(가) 아직 열려 있다 — 확정된 결정만 갈래를 낳는다"
            ),
            RestoreError::ReportOnOpenNode(id) => write!(
                f,
                "{id} 은(는) 열려 있는데 Report 를 지녔다 — Report 는 닫으면서 받는다"
            ),
            RestoreError::ClosedWithoutReport(id) => {
                write!(f, "{id} 은(는) 닫혔다는데 Report 가 없다")
            }
            RestoreError::OpenNodeNotCurrent { node, current } => write!(
                f,
                "{node} 이(가) 열려 있는데 서 있는 자리는 {} 다 — 열린 Node 는 서 있는 자리뿐이다",
                where_at(*current)
            ),
            RestoreError::UnknownCurrent(id) => {
                write!(f, "{id} 에 서 있다는데 그런 Node 가 없다")
            }
            RestoreError::NextDirection { node, source } => write!(f, "{node}: {source}"),
            RestoreError::UnknownPendingRevisit(id) => {
                write!(f, "{id} 에서 되돌아왔다는데 그런 Node 가 없다")
            }
            RestoreError::PendingRevisitNotDeclared { pending, current } => write!(
                f,
                "{pending} 에서 {} 로 되돌아왔다는데 {pending} 에는 그 결정이 적혀 있지 않다 \
                 — 되돌아감은 적힌 것을 밟는 것이다",
                where_at(*current)
            ),
            RestoreError::ReportOnOpenCycle => write!(
                f,
                "이 Cycle 은 열려 있는데 Cycle Report 를 지녔다 — Report 는 닫으면서 받는다"
            ),
            RestoreError::CycleClosedWithoutReport => write!(
                f,
                "이 Cycle 은 닫혔다는데 Cycle Report 가 없다 — Report 는 닫힘의 필수 조건이다"
            ),
            RestoreError::CycleClosedTooEarly => write!(
                f,
                "안의 Outcome 이 닫히지 않았는데 Cycle 이 닫혀 있다"
            ),
            RestoreError::ClosedWithoutJourney(id) => write!(
                f,
                "{id} 이(가) 닫혔다는데 어느 Journey 판에서 닫았는지가 없다 — \
                 닫힌 Node 는 그 결정을 만든 판을 지닌다"
            ),
            RestoreError::JourneyOnOpenNode { node, journey } => write!(
                f,
                "{node} 이(가) 아직 열려 있는데 {journey} 에서 닫았다고 적혀 있다"
            ),
            RestoreError::StepOfAnotherExistence { node, owner, cycle } => write!(
                f,
                "{node} 의 주인은 {owner} 인데 이 Cycle 의 주인은 {cycle} 다 — \
                 열린 Cycle 이 있는 동안 존재를 바꾸지 않으므로 한 Cycle 의 Step 은 \
                 모두 같은 주인을 지닌다"
            ),
            RestoreError::CycleReport { source } => write!(f, "Cycle Report: {source}"),
            RestoreError::StepReport { step, source } => {
                write!(f, "{step} 의 Report: {source}")
            }
            RestoreError::NoCycles => write!(f, "Cycle 이 하나도 없다 — 걷기는 Cycle 안에서만 산다"),
            RestoreError::DuplicateCycle(id) => {
                write!(f, "{id} 이(가) 두 번 실렸다 — 이름은 하나의 Cycle 만 가리킨다")
            }
            RestoreError::CycleNameBeyondNextId { cycle, next_id } => write!(
                f,
                "{cycle} 은(는) 아직 발급되지 않은 이름이다 (다음 이름은 {next_id})"
            ),
            RestoreError::SecondRoot(id) => write!(
                f,
                "{id} 이(가) 부모 없이 실렸는데 뿌리는 이미 있다 — 이 판의 Cycle Graph 는 한 갈래다"
            ),
            RestoreError::RootCycleNotInterview { cycle, kind } => write!(
                f,
                "뿌리 {cycle} 이(가) {kind} 다 — 프로젝트의 첫 Cycle 은 interview 여야 한다.\n\
                 사용자의 요청을 곧바로 실험하지 않는다. Experiment 는 승인된 Synthesis 뒤에 \
                 태어난다."
            ),
            RestoreError::CycleParentNotEarlier { cycle, parent } => write!(
                f,
                "{cycle} 의 부모 {parent} 이(가) 저보다 먼저 나지 않았다 — 부모는 언제나 앞선다"
            ),
            RestoreError::ParentDidNotOpenAChild {
                cycle,
                parent,
                declared,
            } => write!(
                f,
                "{cycle} 이(가) {parent} 아래에 났는데 {parent} 이(가) 적어 둔 다음 방향은 {} 다 \
                 — 자식은 그렇게 하겠다고 적은 Cycle 아래에서만 난다",
                match declared {
                    Some(action) => format!("{action:?}"),
                    None => "없다".to_string(),
                }
            ),
            RestoreError::OpenCycleNotCurrent { cycle, current } => write!(
                f,
                "{cycle} 이(가) 열려 있는데 서 있는 자리는 {current} 다 — 한 번에 걷는 Cycle 은 하나다"
            ),
            RestoreError::UnknownCurrentCycle(id) => {
                write!(f, "{id} 에 서 있다는데 그런 Cycle 이 없다")
            }
        }
    }
}

impl std::error::Error for RestoreError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            RestoreError::Grammar { source, .. } => Some(source),
            RestoreError::NextDirection { source, .. } => Some(source.as_ref()),
            RestoreError::CycleReport { source } => Some(source.as_ref()),
            RestoreError::StepReport { source, .. } => Some(source.as_ref()),
            _ => None,
        }
    }
}
