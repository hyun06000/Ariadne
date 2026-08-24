//! Cycle Graph — 한 프로젝트가 걸어 온 Cycle 들.
//!
//! Cycle 하나가 [`Walk`](crate::Walk) 를 담듯, 여기서는 Cycle 들을 담는다. 그리고 Step Graph 와
//! **같은 규칙**을 한 층 위에서 반복한다.
//!
//! - 부모는 태어날 때 기록된다. 실행 순서로 되계산하지 않는다.
//! - 계보는 `parent` 만 따라간다.
//! - **성공한 Cycle 만 자식의 부모가 된다.** 실패한 Cycle 은 자식을 만들지 않는다.
//! - 닫힌 Cycle 은 바뀌지 않는다.
//!
//! # 적힌 것을 밟는다
//!
//! 자식을 열지 말지는 여기서 새로 고르지 않는다. 부모가 닫히면서 Cycle Report 에
//! `next_direction.action` 을 **이미 적어 두었고**, [`Cycles::open_child`] 는 그것을 실행한다.
//! 근거와 이동이 떨어지지 않게 하려는 것이고, Step 의 되돌아감이 같은 모양이다.
//!
//! 문법이 `success → open_child` · `failure → revisit` 로 좁히므로, "성공한 Cycle 만 부모가
//! 된다" 와 "적힌 방향이 `open_child` 다" 는 **같은 조건**이다. 그래서 두 번 묻지 않는다.
//!
//! # 아직 없는 것
//!
//! Cycle 수준의 되돌아감(`revisit`)과 그 출처, 실패 Cycle 의 형제 가지, 여러 갈래를 동시에
//! 여는 것. 한 번에 **활성 Cycle 은 하나**다.

use std::fmt;

use crate::cycle::{Cycle, CycleError, CycleKind, CycleState};
use crate::refs::{CycleRef, ExistenceRef};
use crate::node::{NodeKind, NodeStatus};
use crate::report::Report;
use crate::rules::RuleSet;
use crate::walk::RestoreError;

/// 한 Cycle Graph 안에서만 유일한 Cycle 의 이름.
///
/// Step 의 이름([`NodeId`](crate::NodeId))과 다른 계층이라 일부러 다른 타입이고, 화면에서도
/// 다르게 읽힌다 — Step 은 `#5`, Cycle 은 `Cycle 2`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct CycleId(u32);

impl CycleId {
    /// 저장이 파일에 적힌 수를 이름으로 되돌릴 때만 쓴다.
    ///
    /// 이 문으로 만든 이름은 **아직 아무것도 보증하지 않는다** — 실재하는지는
    /// [`Cycles::check_restored`] 가 판정한다.
    pub(crate) fn from_raw(raw: u32) -> Self {
        CycleId(raw)
    }

    /// 저장이 이름을 파일에 적을 때만 쓴다.
    pub(crate) fn raw(self) -> u32 {
        self.0
    }

    /// 이 Cycle 을 가리키는 **typed reference**.
    ///
    /// 이름은 Graph 안에서만 뜻이 있지만, reference 는 Report 와 저장에 적힌다.
    /// 발급된 이름은 1 부터 세므로 언제나 성립한다.
    pub fn to_ref(self) -> CycleRef {
        CycleRef::new(self.0).expect("발급된 Cycle 이름은 1 부터 센다")
    }
}

impl fmt::Display for CycleId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Cycle {}", self.0)
    }
}

/// 다음 Cycle 을 열겠다고 적는 방향.
const OPEN_CHILD: &str = "open_child";

/// 걸어 온 Cycle 들과, 지금 어느 Cycle 에 서 있는가.
#[derive(Debug, Clone)]
pub struct Cycles {
    rules: RuleSet,
    nodes: Vec<Cycle>,
    current: CycleId,
    next_id: u32,
}

impl Cycles {
    /// **첫 Interview Cycle 하나**로 시작한다. 뿌리라 부모가 없다.
    ///
    /// 첫 Cycle 이 Interview 인 것은 선택이 아니다(Cycle Model §5). 사용자의 자연어 요청을
    /// 곧바로 실험하지 않고, 먼저 물어 의도를 문장으로 만들고 승인을 받는다. 그래서
    /// **Kind 를 인자로 받지 않는다** — 받으면 experiment 로 시작한 Graph 가 만들어지고,
    /// 그것은 저장할 수 없는 상태다.
    pub fn start(rules: RuleSet, existence: ExistenceRef) -> Cycles {
        let id = CycleId(1);
        Cycles {
            nodes: vec![Cycle::start(
                rules.clone(),
                id,
                CycleKind::Interview,
                existence,
                None,
            )],
            current: id,
            next_id: 2,
            rules,
        }
    }

    /// 지금 서 있는 Cycle.
    pub fn current(&self) -> &Cycle {
        self.node(self.current)
            .expect("current 는 언제나 실재하는 Cycle 을 가리킨다")
    }

    /// 지금 서 있는 Cycle — 고치기 위해.
    pub fn current_mut(&mut self) -> &mut Cycle {
        let current = self.current;
        self.nodes
            .iter_mut()
            .find(|cycle| cycle.id() == current)
            .expect("current 는 언제나 실재하는 Cycle 을 가리킨다")
    }

    /// 지금 서 있는 Cycle 의 이름.
    pub fn current_id(&self) -> CycleId {
        self.current
    }

    /// 만든 순서대로 전부.
    pub fn nodes(&self) -> &[Cycle] {
        &self.nodes
    }

    /// 이름으로 하나를 찾는다.
    pub fn node(&self, id: CycleId) -> Option<&Cycle> {
        self.nodes.iter().find(|cycle| cycle.id() == id)
    }

    /// 이 Cycle 까지의 **구조적 계보**를 뿌리부터 차례로 본다.
    ///
    /// `parent` 사슬만 따라간다 — 만든 순서도, 형제 가지도 아니다. 읽기만 하므로 아무것도
    /// 바뀌지 않는다.
    pub fn lineage(&self, target: CycleId) -> Result<Vec<&Cycle>, CyclesError> {
        let mut path = Vec::new();
        let mut cursor = Some(target);

        while let Some(id) = cursor {
            let cycle = self.node(id).ok_or(CyclesError::UnknownCycle(id))?;
            path.push(cycle);
            cursor = cycle.parent();

            // 부모는 언제나 자신보다 먼저 난 Cycle 이라 사슬은 반드시 끝난다.
            assert!(
                path.len() <= self.nodes.len(),
                "parent 사슬이 Cycle 수보다 길다 — 이 Cycle Graph 에 순환이 있다"
            );
        }

        path.reverse();
        Ok(path)
    }

    /// 이 걷기가 따르는 Grammar.
    pub fn rules(&self) -> &RuleSet {
        &self.rules
    }

    /// 지금 자식 Cycle 을 열 수 있는가 — 그리고 왜 아닌가.
    ///
    /// 판정은 [`Cycles::open_child`] 와 **같은 자리**에서 난다. 안내가 실행과 갈리지 않게.
    pub fn why_not_open_child(&self) -> Option<OpenChildError> {
        let parent = self.current();
        if !parent.is_closed() {
            return Some(OpenChildError::CurrentStillOpen(parent.id()));
        }
        match parent.declared_action() {
            Some(OPEN_CHILD) => None,
            Some(other) => Some(OpenChildError::NotTheDeclaredDirection {
                parent: parent.id(),
                declared: other.to_string(),
            }),
            // 닫힌 Cycle 은 Report 를 지닌다(그것이 닫힘의 조건이다). 그래도 파일이
            // 두 번째 통로라 여기 닿을 수 있다 — 그때는 방향이 없다고 말한다.
            None => Some(OpenChildError::NoDirection(parent.id())),
        }
    }

    /// 지금 Cycle 이 **적어 둔** 다음 Cycle 을 연다.
    ///
    /// 새 Cycle 은 빈 Step Graph 로 시작한다 — 부모의 Step 은 **한 개도 복사하지 않는다.**
    /// 이어받는 것은 부모의 Cycle Report 이고, 그것은 복제하지 않고 `parent` 를 따라 읽는다.
    pub fn open_child(
        &mut self,
        kind: CycleKind,
        existence: ExistenceRef,
    ) -> Result<CycleId, CyclesError> {
        if let Some(why) = self.why_not_open_child() {
            return Err(CyclesError::OpenChild(why));
        }

        let parent = self.current;
        let id = CycleId(self.next_id);
        self.next_id += 1;
        self.nodes.push(Cycle::start(
            self.rules.clone(),
            id,
            kind,
            existence,
            Some(parent),
        ));
        self.current = id;
        Ok(id)
    }

    /// 저장이 읽어 온 값으로 다시 세운다.
    pub(crate) fn restore(rules: RuleSet, state: CyclesState) -> Result<Cycles, RestoreError> {
        let mut nodes = Vec::with_capacity(state.nodes.len());
        for cycle in state.nodes {
            nodes.push(Cycle::restore(rules.clone(), cycle)?);
        }
        let cycles = Cycles {
            rules,
            nodes,
            current: state.current,
            next_id: state.next_id,
        };
        cycles.check_restored()?;
        Ok(cycles)
    }

    /// 되살아난 값이 **걸어서 만들 수 있는 것**인지 판정한다.
    ///
    /// Cycle 하나하나의 불변식은 [`Cycle::restore`] 가 이미 쟀다. 여기서 재는 것은
    /// **Graph 의 불변식**뿐이다.
    fn check_restored(&self) -> Result<(), RestoreError> {
        if self.nodes.is_empty() {
            return Err(RestoreError::NoCycles);
        }

        let mut seen: Vec<CycleId> = Vec::with_capacity(self.nodes.len());
        for cycle in &self.nodes {
            let id = cycle.id();
            if seen.contains(&id) {
                return Err(RestoreError::DuplicateCycle(id));
            }
            if id.raw() >= self.next_id {
                return Err(RestoreError::CycleNameBeyondNextId {
                    cycle: id,
                    next_id: self.next_id,
                });
            }

            match cycle.parent() {
                // 뿌리는 하나뿐이다. 둘이면 이 Graph 는 한 갈래가 아니다.
                None => {
                    if !seen.is_empty() {
                        return Err(RestoreError::SecondRoot(id));
                    }
                    // 그리고 뿌리는 **Interview** 다(Cycle Model §5). 사용자의 요청을 곧바로
                    // 실험한 Graph 는 걸어서 만들 수 없다 — `gil start` 가 여는 것은 Interview
                    // 하나뿐이고, Experiment 는 승인된 Synthesis 뒤에만 태어난다.
                    if cycle.kind() != CycleKind::Interview {
                        return Err(RestoreError::RootCycleNotInterview {
                            cycle: id,
                            kind: cycle.kind(),
                        });
                    }
                }
                Some(parent) => {
                    // 부모는 **먼저 난 Cycle** 이어야 한다 — 이 한 줄이 순환을 막는다.
                    if !seen.contains(&parent) {
                        return Err(RestoreError::CycleParentNotEarlier { cycle: id, parent });
                    }
                    let parent = self.node(parent).expect("방금 앞에서 본 Cycle 이다");
                    // 그리고 **성공한 Cycle 만** 부모가 된다.
                    if parent.declared_action() != Some(OPEN_CHILD) {
                        return Err(RestoreError::ParentDidNotOpenAChild {
                            cycle: id,
                            parent: parent.id(),
                            declared: parent.declared_action().map(str::to_string),
                        });
                    }
                }
            }

            // 열린 Cycle 은 서 있는 자리 하나뿐이다.
            if !cycle.is_closed() && id != self.current {
                return Err(RestoreError::OpenCycleNotCurrent {
                    cycle: id,
                    current: self.current,
                });
            }

            seen.push(id);
        }

        if self.node(self.current).is_none() {
            return Err(RestoreError::UnknownCurrentCycle(self.current));
        }
        Ok(())
    }

    /// 저장이 적어 갈 값들.
    pub(crate) fn next_name(&self) -> u32 {
        self.next_id
    }
}

/// 저장에서 되살려 온 Cycle Graph 의 값들.
pub(crate) struct CyclesState {
    pub next_id: u32,
    pub current: CycleId,
    pub nodes: Vec<CycleState>,
}

/// Cycle Graph 가 거절한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CyclesError {
    /// 이 Graph 에 그런 이름의 Cycle 이 없다.
    UnknownCycle(CycleId),
    /// 자식을 열 수 없다.
    OpenChild(OpenChildError),
    /// 지금 서 있는 Cycle 이 거절했다.
    Cycle(CycleError),
}

/// 자식 Cycle 을 열 수 없는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OpenChildError {
    /// 지금 Cycle 이 아직 열려 있다 — 활성 Cycle 은 하나뿐이다.
    CurrentStillOpen(CycleId),
    /// 적어 둔 방향이 자식을 여는 것이 아니다.
    NotTheDeclaredDirection { parent: CycleId, declared: String },
    /// 닫혔는데 다음 방향이 적혀 있지 않다.
    NoDirection(CycleId),
}

impl From<CycleError> for CyclesError {
    fn from(err: CycleError) -> Self {
        CyclesError::Cycle(err)
    }
}

impl From<OpenChildError> for CyclesError {
    fn from(err: OpenChildError) -> Self {
        CyclesError::OpenChild(err)
    }
}

impl fmt::Display for CyclesError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CyclesError::UnknownCycle(id) => {
                write!(f, "{id} 은(는) 이 Cycle Graph 에 없다")
            }
            CyclesError::OpenChild(err) => write!(f, "{err}"),
            CyclesError::Cycle(err) => write!(f, "{err}"),
        }
    }
}

impl fmt::Display for OpenChildError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OpenChildError::CurrentStillOpen(id) => write!(
                f,
                "{id} 이(가) 아직 열려 있다 — 한 번에 걷는 Cycle 은 하나다.\n\
                 먼저 이 Cycle 을 Cycle Report 로 닫아라: `gil cycle close`"
            ),
            OpenChildError::NotTheDeclaredDirection { parent, declared } => write!(
                f,
                "{parent} 이(가) 적어 둔 다음 방향은 {declared:?} 라 자식을 여는 것이 아니다.\n\
                 실패한 Cycle 은 자식을 만들지 않는다 — 되돌아가 형제 가지를 내는 것은 \
                 아직 짓지 않았다."
            ),
            OpenChildError::NoDirection(id) => write!(
                f,
                "{id} 에 다음 방향이 적혀 있지 않다 — 밟을 것이 없다"
            ),
        }
    }
}

impl std::error::Error for CyclesError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            CyclesError::OpenChild(err) => Some(err),
            CyclesError::Cycle(err) => Some(err),
            CyclesError::UnknownCycle(_) => None,
        }
    }
}

impl std::error::Error for OpenChildError {}

/// 지금 Cycle 안에서 다음에 할 수 있는 Step 들 — 편의를 위해 한 층 위로 올린다.
impl Cycles {
    pub fn openable_here(&self) -> Vec<NodeKind> {
        self.current().openable_here()
    }

    /// 이 Cycle 이 부모에게서 이어받은 Cycle Report.
    ///
    /// **복제하지 않는다.** `parent` 를 따라가 원본을 읽을 뿐이고, 부모가 없으면 없다.
    pub fn inherited_report(&self, id: CycleId) -> Option<&Report> {
        self.node(self.node(id)?.parent()?)?.report()
    }

    /// 지금 Cycle 이 닫혔고 그 안이 끝났는가 — 닫을 수 있는가.
    pub fn can_close(&self) -> bool {
        self.current().can_close()
    }

    /// 지금 서 있는 Cycle 의 상태.
    pub fn status(&self) -> NodeStatus {
        self.current().status()
    }
}
