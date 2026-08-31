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
//! # 되돌아감은 두 걸음이다
//!
//! 실패한 Cycle 이 **어디로 되돌아갈지**는 Cycle Report 에 적히고, 그 값이 이 Graph 에서
//! 성립하는지 [`Cycles::check_next_direction`] 이 판정한다. 그 뒤는 Step 의 되돌아감과
//! 같은 두 단계다.
//!
//! ```text
//! gil revisit     current 를 대상 조상으로 옮기고 pending 에 실패 Cycle 을 적는다
//! gil open <종류>  그 pending 을 새 Cycle 의 revisit_from 으로 소비한다
//! ```
//!
//! 새 Cycle 이 받는 것은 셋이고 **출처가 각자 다르다.**
//!
//! ```text
//! parent        = 되돌아간 대상    누구의 사고와 세계를 이어받았는가
//! entry         = 그 대상의 Exit   어느 세계에서 출발하는가
//! revisit_from  = 버린 실패 Cycle  어느 결정이 이 갈래를 낳았는가 — 계보의 변이 아니다
//! ```
//!
//! **세계는 여기서 만지지 않는다.** Cycle Graph 는 파일을 볼 수 없고, 어느 Snapshot 으로
//! 되돌릴지만 typed 값으로 돌려준다. 그 세계를 실제로 투영하는 것은 트랜잭션의 몫이다.
//!
//! # 아직 없는 것
//!
//! 여러 갈래를 동시에 여는 것. 한 번에 **활성 Cycle 은 하나**다.

use std::fmt;

use crate::cycle::{Cycle, CycleError, CycleKind, CycleState};
use crate::refs::{CycleRef, ExistenceRef, JourneyRef, RefSyntaxError, SnapshotRef};
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

/// typed reference 를 Graph 안의 이름으로 — **전역인 것을 지역으로 되돌린다.**
///
/// 두 값은 같은 수를 담지만 사는 자리가 다르다. reference 는 Report 와 화면의 것이고,
/// 이름은 이 Graph 안에서만 뜻이 있다. 발급된 이름은 1 부터 세므로 이 변환은 언제나 성립한다.
impl From<CycleRef> for CycleId {
    fn from(id: CycleRef) -> CycleId {
        CycleId(id.number())
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
    /// **되돌아왔고 아직 새 Cycle 을 열지 않은 상태** — 방금 버린 실패 Cycle.
    ///
    /// 두 명령 사이에만 사는 전이 상태다. 영구 객체의 schema 가 아니라서 저장 형식의
    /// 번호를 올리지 않고, 값이 없으면 파일에 칸을 쓰지도 않는다(Storage Model §3.1).
    ///
    /// `revisit_from` 과 **같은 뜻이 아니다.** 이것은 「아직 소비되지 않은 결정」이고,
    /// `revisit_from` 은 그 결정이 새 Cycle 에 남긴 **불변의 자국**이다. 하나가 다른 하나로
    /// 옮겨 가며 이 자리는 비워진다.
    pending_revisit: Option<CycleId>,
}

impl Cycles {
    /// **첫 Interview Cycle 하나**로 시작한다. 뿌리라 부모가 없다.
    ///
    /// 첫 Cycle 이 Interview 인 것은 선택이 아니다(Cycle Model §5). 사용자의 자연어 요청을
    /// 곧바로 실험하지 않고, 먼저 물어 의도를 문장으로 만들고 승인을 받는다. 그래서
    /// **Kind 를 인자로 받지 않는다** — 받으면 experiment 로 시작한 Graph 가 만들어지고,
    /// 그것은 저장할 수 없는 상태다.
    /// 뿌리 Cycle 의 Entry 는 **`gil start` 가 관측한 최초 세계**다(Artifact Model §4).
    /// 그것 말고 뿌리가 출발할 세계는 없다.
    pub fn start(rules: RuleSet, existence: ExistenceRef, entry: SnapshotRef) -> Cycles {
        let id = CycleId(1);
        Cycles {
            nodes: vec![Cycle::start(
                rules.clone(),
                id,
                CycleKind::Interview,
                existence,
                None,
                entry,
            )],
            current: id,
            next_id: 2,
            pending_revisit: None,
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
        // **되돌아온 자리에서 여는 Cycle 은 평범한 자식이 아니다.** 그냥 열면 어느 실패가
        // 이 갈래를 낳았는지가 사라진다. 그래서 이 자리는 [`Cycles::open_after_revisit`]
        // 이 맡고, 여기서는 「이 문이 아니다」라고만 말한다.
        if self.pending_revisit.is_some() {
            return Some(OpenChildError::RevisitPending);
        }
        let parent = self.current();
        if !parent.is_closed() {
            return Some(OpenChildError::CurrentStillOpen(parent.id()));
        }
        if is_branch_point(parent) {
            return None;
        }
        match parent.declared_action() {
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
        // **자식의 Entry 는 부모의 Exit 이다** — 그 전이가 떠난 세계가 곧 이 Cycle 이 도착한
        // 세계다(Artifact Model §7.1). 고르지 않고 읽는다.
        let entry = self
            .current()
            .exit_snapshot()
            .ok_or(CyclesError::OpenChild(OpenChildError::NoExitWorld(parent)))?;

        let id = CycleId(self.next_id);
        self.next_id += 1;
        self.nodes.push(Cycle::start(
            self.rules.clone(),
            id,
            kind,
            existence,
            Some(parent),
            entry,
        ));
        self.current = id;
        Ok(id)
    }

    /// 지금 서 있는 Cycle 을 이 Cycle Report 로 닫는다 — **닫는 문은 여기 하나다.**
    ///
    /// [`Cycle::close_into`] 를 직접 부르지 않는 까닭은 하나다: Cycle 하나는 제 이웃을
    /// 모르므로 `next_direction.target_cycle_ref` 가 이 Graph 에서 성립하는지 답할 수 없다.
    /// 그 판정을 부르는 쪽의 규율에 맡기면 언젠가 한 자리가 빠뜨린다.
    pub(crate) fn close_current(
        &mut self,
        report: Report,
        journey: JourneyRef,
    ) -> Result<(), CycleCloseError> {
        // pending 을 지나쳐 Graph 를 바꾸지 않는다. 지금 서 있는 자리는 이미 닫힌
        // 대상 조상이므로 여기 닿는 일은 없어야 하지만, 파일이 두 번째 통로다.
        if let Some(from) = self.pending_revisit {
            return Err(CycleCloseError::RevisitPending {
                from: from.to_ref(),
                target: self.current.to_ref(),
            });
        }
        self.check_next_direction(self.current, &report)
            .map(|_| ())
            .map_err(CycleCloseError::NextDirection)?;
        self.current_mut()
            .close_into(report, journey)
            .map_err(CycleCloseError::Cycle)
    }

    /// 적어 둔 다음 방향이 **이 Cycle Graph 에서 구조적으로 가능한가.**
    ///
    /// 문법은 어떤 칸이 있어야 하고 어떤 값이 올 수 있는지까지만 안다(`gil-spec.yaml`).
    /// 대상이 실재하는지·닫혔는지·걸어온 길 위인지는 **Graph 만 답할 수 있고**, 그래서 이
    /// 판정은 [`Cycle`] 이 아니라 여기 산다.
    ///
    /// 닫을 때와 저장에서 되살릴 때가 **같은 이 함수**를 쓴다. 파일은 두 번째 통로라,
    /// 두 자리가 각자 재면 손으로 고친 판이 닫기가 막았을 대상을 들고 들어온다.
    ///
    /// 고른 대상이 **옳은가**는 보지 않는다 — 그건 계보를 읽은 Agent 의 판단이다.
    pub(crate) fn check_next_direction(
        &self,
        source: CycleId,
        report: &Report,
    ) -> Result<Option<CycleId>, CycleTargetError> {
        let Some(target) = declared_revisit_target(report)? else {
            return Ok(None); // 되돌아가는 방향이 아니다 — 볼 자리가 없다.
        };
        let id = CycleId::from_raw(target.number());

        // ① 자기 자신인가 — 조상 검사보다 **먼저** 묻는다. 사람이 한 일이 다르기 때문이다
        //    (지금 닫는 그 Cycle 의 주소를 적었다).
        if id == source {
            return Err(CycleTargetError::TargetIsItself(target));
        }

        // ② 이 Graph 에 있는 Cycle 인가
        let node = self
            .node(id)
            .ok_or(CycleTargetError::UnknownTarget(target))?;

        // ③ 닫혀 있는가 — 되돌아갈 곳은 확정된 자리여야 한다(Time Model §7)
        if !node.is_closed() {
            return Err(CycleTargetError::TargetIsOpen(target));
        }

        // ④ 걸어온 길 위인가 — **`parent` 사슬만 따라간다.**
        //
        //    계보를 여기서 다시 세지 않고 [`Cycles::lineage`] 를 그대로 쓴다. 그래야
        //    「무엇이 조상인가」의 답이 프로젝트 안에 하나뿐이고, 훗날 `revisit_from` 을
        //    두 번째 부모로 읽는 변경이 이 검사도 함께 무너뜨려 시험에 걸린다.
        //    ID 의 크기나 저장 배열의 순서로 선후를 추정하지 않는다.
        let lineage = self
            .lineage(source)
            .expect("닫는 자리와 그 조상은 언제나 이 Graph 에 실재한다");
        if !lineage.iter().any(|cycle| cycle.id() == id) {
            return Err(CycleTargetError::TargetNotAnAncestor(target));
        }

        // ⑤ 거기서 새 Cycle 이 날 수 있는가 — 되돌아간 자리는 **유효한 분기점**이어야 한다.
        //    `open_child` 가 묻는 것과 같은 물음이라 같은 답을 쓴다.
        if !is_branch_point(node) {
            return Err(CycleTargetError::TargetCannotBranch {
                target,
                declared: node.declared_action().map(str::to_string),
            });
        }

        Ok(Some(id))
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
            pending_revisit: state.pending_revisit,
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

        // **두 번째 훑기.** 적힌 다음 방향은 닫을 때와 **같은 함수**로 다시 잰다.
        //
        // 첫 훑기가 부모 사슬이 앞을 향한다는 것을 이미 세웠으므로, 여기서 비로소 계보를
        // 물을 수 있다. 순서를 합치면 아직 검사되지 않은 부모를 딛고 계보를 걷게 된다.
        for cycle in &self.nodes {
            let Some(report) = cycle.report() else {
                continue; // 열린 Cycle 은 아직 방향을 적지 않았다.
            };
            self.check_next_direction(cycle.id(), report).map_err(|source| {
                RestoreError::CycleNextDirection {
                    cycle: cycle.id(),
                    source,
                }
            })?;
        }

        self.check_provenance()?;
        self.check_pending()
    }

    /// 갈래의 출처가 **걸어서 만들 수 있는 것**인가.
    ///
    /// `revisit_from` 은 되돌아감을 밟은 결과다. 그러므로 그 자리에 그 결정이 있어야 하고,
    /// 이 Cycle 의 구조적 부모가 바로 그 결정이 가리킨 대상이어야 하며, 출발한 세계도 그
    /// 대상의 Exit 이어야 한다. 셋 중 하나라도 어긋나면 그 파일은 걷기가 만든 것이 아니다.
    ///
    /// **저장 배열의 순서나 이름의 크기로 뜻을 추정하지 않는다.** ID 의 선후는 「이름은
    /// append-only 로 발급된다」는 불변식을 재는 데만 쓴다.
    fn check_provenance(&self) -> Result<(), RestoreError> {
        for cycle in &self.nodes {
            let Some(from) = cycle.revisit_from() else {
                continue; // 평범하게 이어 난 Cycle 이다.
            };
            let id = cycle.id();

            // ① 출처는 저보다 먼저 난 Cycle 이다 — 이름 발급 불변식.
            let source = self
                .node(from)
                .ok_or(RestoreError::UnknownCycleRevisitFrom { cycle: id, from })?;
            if from >= id {
                return Err(RestoreError::CycleRevisitFromNotEarlier { cycle: id, from });
            }

            // ② 출처는 자기 자신도, 제 부모도 아니다 — **실패한 Cycle 은 부모가 되지 않는다.**
            if cycle.parent() == Some(from) {
                return Err(RestoreError::CycleRevisitFromIsTheParent { cycle: id, from });
            }

            // ③ 그 자리에 그 결정이 적혀 있고, 그 결정이 가리킨 것이 이 Cycle 의 부모다.
            //    닫힘·failure·Experiment·대상의 실재와 계보는 전부 그 검사가 함께 본다
            //    (M4-B). 같은 것을 여기서 다시 세지 않는다.
            let declared = source
                .report()
                .and_then(|report| self.check_next_direction(from, report).ok())
                .flatten();
            if declared.is_none() || declared != cycle.parent() {
                return Err(RestoreError::CycleRevisitFromNotDeclared {
                    cycle: id,
                    from,
                    parent: cycle.parent(),
                    declared,
                });
            }

            // ④ 그리고 출발한 세계는 그 대상의 Exit 이다 — 버린 갈래의 세계가 아니다.
            let target = self.node(declared.expect("방금 있음을 봤다")).expect("계보 위에 있다");
            if target.exit_snapshot() != Some(cycle.entry_snapshot()) {
                return Err(RestoreError::CycleRevisitEntryIsNotTheTargetExit {
                    cycle: id,
                    entry: cycle.entry_snapshot(),
                    target: target.id(),
                });
            }
        }
        Ok(())
    }

    /// 되돌아온 상태가 **걸어서 만들 수 있는 것**인가.
    ///
    /// pending 은 「적힌 것을 밟은」 결과다. 그러므로 그 자리에 그 결정이 있어야 하고,
    /// 지금 서 있는 자리가 바로 그 결정이 가리킨 대상이어야 한다. 둘 중 하나라도 어긋나면
    /// 그 파일은 걷기가 만든 것이 아니다 — Step 의 `pending_revisit` 과 같은 규율이다.
    ///
    /// 나머지는 **다시 묻지 않는다.** 대상이 실재하고 닫혔고 계보 위이며 분기점이라는 것은
    /// 바로 앞의 훑기가 이미 봤고, 열린 Cycle 이 없다는 것은 「열린 Cycle 은 current 뿐」과
    /// 「current 는 닫힌 대상」이 함께 보증한다. 같은 것을 두 자리에서 물으면 한쪽이 낡는다.
    fn check_pending(&self) -> Result<(), RestoreError> {
        let Some(pending) = self.pending_revisit else {
            return Ok(());
        };
        let from = self
            .node(pending)
            .ok_or(RestoreError::UnknownPendingCycleRevisit(pending))?;
        let declared = from
            .report()
            .and_then(|report| self.check_next_direction(pending, report).ok())
            .flatten();
        match declared == Some(self.current) {
            true => Ok(()),
            false => Err(RestoreError::PendingCycleRevisitNotDeclared {
                pending,
                current: self.current,
                declared,
            }),
        }
    }

    /// **적어 둔 되돌아감을 밟는다 — 논리적 이동 하나.**
    ///
    /// 어디로 갈지 여기서 고르지 않는다. 실패한 Cycle 을 닫을 때 Report 에 이미 적혔고,
    /// 그것이 이 Graph 에서 성립하는지도 그때 판정됐다(M4-B). 그래서 *왜 그리로 갔는가* 와
    /// 실제 이동이 떨어지지 않는다 — Step 의 되돌아감이 같은 모양이다.
    ///
    /// **Graph 는 한 글자도 바뀌지 않는다.** Cycle 도 Report 도 이름 발급기도 그대로고,
    /// 바뀌는 것은 서 있는 자리와 pending 둘뿐이다. 새 Cycle 도, 새 Snapshot 도, Will 도,
    /// Journey 판도 만들지 않는다 — 컨테이너 사이의 이동은 그 어느 것도 아니다.
    ///
    /// 돌려주는 것은 **어느 세계로 되돌려야 하는가**까지 담은 typed 값이다. 파일을 만지는
    /// 일은 이 계층이 할 수 없고, 화면에 무엇을 적을지도 여기서 정하지 않는다.
    pub(crate) fn revisit(&mut self) -> Result<CycleRevisit, CycleRevisitError> {
        if let Some(from) = self.pending_revisit {
            return Err(CycleRevisitError::AlreadyPending {
                from: from.to_ref(),
                target: self.current.to_ref(),
            });
        }

        let from = self.current;
        let here = self.current();
        if !here.is_closed() {
            return Err(CycleRevisitError::StillOpen(from.to_ref()));
        }
        // 닫힌 Cycle 은 Report 를 지닌다(그것이 닫힘의 조건이다). 파일이 두 번째 통로라
        // 여기 닿을 수 있고, 그때는 밟을 것이 적혀 있지 않다고 말한다.
        let Some(report) = here.report() else {
            return Err(CycleRevisitError::NoDirection(from.to_ref()));
        };

        // **M4-B 가 검증한 그 한 경로를 그대로 쓴다.** 다시 파싱하지도, 구조 판정을
        // 복제하지도 않는다 — 두 자리에 적으면 닫을 때 막은 것을 밟을 때 통과시킨다.
        let Some(target) = self.check_next_direction(from, report)? else {
            return Err(CycleRevisitError::NotTheDeclaredDirection {
                from: from.to_ref(),
                declared: here.declared_action().map(str::to_string),
            });
        };

        let world = self
            .node(target)
            .expect("검사가 대상의 실재를 이미 봤다")
            .exit_snapshot()
            .ok_or(CycleRevisitError::TargetHasNoExitWorld(target.to_ref()))?;

        self.current = target;
        self.pending_revisit = Some(from);
        Ok(CycleRevisit {
            from: from.to_ref(),
            target: target.to_ref(),
            target_world: world,
        })
    }

    /// 되돌아왔고 아직 소비되지 않은 결정. 없으면 일반 상태다.
    pub fn pending_revisit(&self) -> Option<CycleId> {
        self.pending_revisit
    }

    /// 지금 되돌아감을 밟을 수 있는가 — **안내가 실행과 갈리지 않게.**
    ///
    /// 규칙을 여기서 다시 쓰지 않고 **밟아 보고 되돌리는 방식으로** 답한다. 판정은 언제나
    /// [`Cycles::revisit`] 한 곳에서만 난다 — 두 자리에 적으면 안내를 믿은 Agent 가 한 번
    /// 실패하고서야 옳은 수를 안다(`openable_here` 와 같은 규율이다).
    ///
    /// **세계는 보지 않는다.** dirty 여부는 파일을 읽어야 알 수 있고 Graph 는 그것을 모른다 —
    /// 그 판정은 트랜잭션이 한 번 더 한다.
    ///
    /// 공개하는 까닭은 하나다: 닫기 receipt 와 status 가 **다음 수를 안내**하려면 이것을
    /// 물어야 한다. 시험 편의가 아니라 화면의 계약이다.
    pub fn can_revisit(&self) -> bool {
        self.clone().revisit().is_ok()
    }

    /// **되돌아온 자리에서 새 갈래를 연다 — pending 을 소비하는 하나의 전이.**
    ///
    /// [`Cycles::open_child`] 와 이름을 나누는 까닭은 여는 것이 다르기 때문이다. 평범한
    /// 자식은 부모가 적어 둔 `open_child` 를 밟지만, 이 갈래는 **버린 실패에서 갈라져**
    /// 난다. 그 사실이 새 Cycle 에 `revisit_from` 으로 남고, 그것을 남기지 않으면 어느
    /// 결정이 이 갈래를 낳았는지 실행 순서로 되짚어야 한다.
    ///
    /// ```text
    /// N.parent       = 되돌아간 대상 T       (= 지금 서 있는 자리)
    /// N.revisit_from = 버린 실패 Cycle F     (pending 이 들고 있던 것)
    /// N.entry        = T.exit_snapshot_ref
    /// pending        = None                 ← 여기서 비워진다
    /// ```
    ///
    /// **한 전이다.** 이름 발급·Cycle 생성·서 있는 자리 이동·pending 소비가 전부 여기서
    /// 함께 일어나고, 어느 하나만 일어난 중간 상태를 만들지 않는다. 거절하면 이름 발급기도
    /// 움직이지 않는다.
    pub(crate) fn open_after_revisit(
        &mut self,
        kind: CycleKind,
        existence: ExistenceRef,
    ) -> Result<CycleId, OpenAfterRevisitError> {
        let from = self
            .pending_revisit
            .ok_or(OpenAfterRevisitError::NothingPending)?;
        let target = self.current;

        // **닫을 때 본 것을 다시 본다.** 파일이 두 번째 통로이므로, 여기 닿는 값이 그때
        // 그 값이라고 가정하지 않는다 — 판정은 M4-B 의 그 함수 하나가 한다.
        let declared = self
            .node(from)
            .and_then(Cycle::report)
            .map(|report| self.check_next_direction(from, report))
            .transpose()
            .map_err(OpenAfterRevisitError::NextDirection)?
            .flatten();
        if declared != Some(target) {
            return Err(OpenAfterRevisitError::NotWhereItSaid {
                from: from.to_ref(),
                here: target.to_ref(),
                declared: declared.map(CycleId::to_ref),
            });
        }

        // 되돌아간 자리는 **자식을 가질 수 있는 분기점**이어야 한다 — `open_child` 와 같은
        // 물음이라 같은 답을 쓴다. 실패한 F 를 부모로 삼는 길은 여기에 없다.
        let here = self.current();
        if !is_branch_point(here) {
            return Err(OpenAfterRevisitError::TargetCannotBranch {
                target: target.to_ref(),
                declared: here.declared_action().map(str::to_string),
            });
        }
        // **Entry 는 저장된 Exit 을 읽는다.** 지금 폴더를 다시 관측해 지어내지 않는다 —
        // 그러면 사람이 그 사이에 건드린 것이 새 Cycle 의 출발 세계가 된다.
        let entry = here
            .exit_snapshot()
            .ok_or(OpenAfterRevisitError::TargetHasNoExitWorld(target.to_ref()))?;

        let id = CycleId(self.next_id);
        self.next_id += 1;
        let mut born = Cycle::start(
            self.rules.clone(),
            id,
            kind,
            existence,
            Some(target),
            entry,
        );
        born.born_from_revisit(from);
        self.nodes.push(born);
        self.current = id;
        self.pending_revisit = None; // 결정이 소비됐다.
        Ok(id)
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
    pub pending_revisit: Option<CycleId>,
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

/// Cycle 을 닫을 수 없는 이유 — **두 계층이 각자 하나씩.**
///
/// 다음 방향은 Graph 가 판정하고 그 밖의 것은 Cycle 자신이 판정한다. 한 덩어리로 뭉치면
/// 부르는 쪽이 「이 Graph 의 문제인가, 이 Cycle 의 문제인가」를 다시 물어야 한다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CycleCloseError {
    /// 적어 둔 다음 방향이 이 Cycle Graph 에서 성립하지 않는다.
    NextDirection(CycleTargetError),
    /// 지금 서 있는 Cycle 이 거절했다.
    Cycle(CycleError),
    /// 되돌아왔고 아직 새 Cycle 을 열지 않았다.
    RevisitPending { from: CycleRef, target: CycleRef },
}

impl fmt::Display for CycleCloseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CycleCloseError::NextDirection(err) => write!(f, "{err}"),
            CycleCloseError::Cycle(err) => write!(f, "{err}"),
            CycleCloseError::RevisitPending { from, target } => write!(f, "{}", pending_says(*from, *target)),
        }
    }
}

impl std::error::Error for CycleCloseError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            CycleCloseError::NextDirection(err) => Some(err),
            CycleCloseError::Cycle(err) => Some(err),
            CycleCloseError::RevisitPending { .. } => None,
        }
    }
}

/// 되돌아온 자리에서 막힐 때 하는 **같은 말** — 두 오류가 이 한 자리를 쓴다.
///
/// 여기서 내미는 수는 **실제로 밟을 수 있는 것**이다. 되돌아온 자리에서 할 일은 하나뿐이고,
/// 그것을 말하지 않으면 사람은 무엇이 막혔는지만 알고 무엇을 해야 하는지는 모른다.
fn pending_says(from: CycleRef, target: CycleRef) -> String {
    format!(
        "{from} 에서 {target} 로 이미 되돌아온 자리다.\n\
         지금 할 일: 이 자리 아래에 새 Cycle 을 연다 — \
         `gil open interview` · `gil open experiment`"
    )
}

/// 적어 둔 Cycle 계층의 되돌아감을 밟을 수 없는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CycleRevisitError {
    /// 지금 서 있는 Cycle 이 아직 열려 있다 — 되돌아감은 닫힌 자리에서만 시작한다.
    StillOpen(CycleRef),
    /// 닫혔는데 Report 가 없다 — 밟을 결정이 적혀 있지 않다.
    NoDirection(CycleRef),
    /// 적어 둔 방향이 되돌아감이 아니다(성공한 Cycle 이 여기로 온다).
    NotTheDeclaredDirection {
        from: CycleRef,
        declared: Option<String>,
    },
    /// 적어 둔 갈 곳이 이 Graph 에서 성립하지 않는다.
    NextDirection(CycleTargetError),
    /// 이미 되돌아와 있다 — 소비되지 않은 결정이 하나 걸려 있다.
    AlreadyPending { from: CycleRef, target: CycleRef },
    /// 대상이 닫혔는데 확정한 세계가 없다 — 되돌아갈 자리가 없다.
    TargetHasNoExitWorld(CycleRef),
}

impl From<CycleTargetError> for CycleRevisitError {
    fn from(err: CycleTargetError) -> Self {
        CycleRevisitError::NextDirection(err)
    }
}

impl fmt::Display for CycleRevisitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CycleRevisitError::StillOpen(id) => write!(
                f,
                "{id} 이(가) 아직 열려 있다 — 되돌아감은 닫힌 판정에서만 시작한다.\n\
                 먼저 이 Cycle 을 Cycle Report 로 닫는다: `gil close`"
            ),
            CycleRevisitError::NoDirection(id) => {
                write!(f, "{id} 에 다음 방향이 적혀 있지 않다 — 밟을 것이 없다")
            }
            CycleRevisitError::NotTheDeclaredDirection { from, declared } => write!(
                f,
                "{from} 이(가) 적어 둔 다음 방향은 {} 라 되돌아감이 아니다",
                match declared {
                    Some(action) => format!("{action:?}"),
                    None => "없다".to_string(),
                }
            ),
            CycleRevisitError::NextDirection(err) => write!(f, "{err}"),
            CycleRevisitError::AlreadyPending { from, target } => {
                write!(f, "{}", pending_says(*from, *target))
            }
            CycleRevisitError::TargetHasNoExitWorld(id) => write!(
                f,
                "{id} 이(가) 닫혔는데 확정한 Artifact 세계가 없다 — 되돌아갈 자리가 없다"
            ),
        }
    }
}

impl std::error::Error for CycleRevisitError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            CycleRevisitError::NextDirection(err) => Some(err),
            _ => None,
        }
    }
}

/// **되돌아감이 무엇을 했는가** — 화면용 글이 아니라 typed 값이다.
///
/// 어디서 갈라졌고, 어디에 섰고, 어느 세계로 되돌려야 하는가. 이 셋이 있어야 트랜잭션이
/// 세계를 투영할 수 있고, 훗날 receipt 도 이 값에서 읽는다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct CycleRevisit {
    /// 방금 버린 실패 Cycle. 다음 `gil open` 이 `revisit_from` 으로 소비한다.
    pub from: CycleRef,
    /// 되돌아와 선 자리 — 구조적 조상.
    pub target: CycleRef,
    /// 그 자리가 확정했던 세계. 작업 폴더를 여기로 되돌린다.
    pub target_world: SnapshotRef,
}

/// 되돌아온 자리에서 새 갈래를 열 수 없는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum OpenAfterRevisitError {
    /// 되돌아온 적이 없다 — 소비할 결정이 없다.
    NothingPending,
    /// 적어 둔 갈 곳이 이 Graph 에서 성립하지 않는다.
    NextDirection(CycleTargetError),
    /// 서 있는 자리가 그 결정이 가리킨 대상이 아니다.
    NotWhereItSaid {
        from: CycleRef,
        here: CycleRef,
        declared: Option<CycleRef>,
    },
    /// 되돌아간 자리에서는 새 Cycle 이 날 수 없다.
    TargetCannotBranch {
        target: CycleRef,
        declared: Option<String>,
    },
    /// 되돌아간 자리가 확정한 세계가 없다 — 새 Cycle 이 출발할 자리가 없다.
    TargetHasNoExitWorld(CycleRef),
}

impl fmt::Display for OpenAfterRevisitError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            OpenAfterRevisitError::NothingPending => {
                write!(f, "되돌아온 적이 없다 — 소비할 결정이 없다")
            }
            OpenAfterRevisitError::NextDirection(err) => write!(f, "{err}"),
            OpenAfterRevisitError::NotWhereItSaid {
                from,
                here,
                declared,
            } => write!(
                f,
                "{from} 에서 되돌아왔다는데 서 있는 자리는 {here} 이고, {from} 이(가) 적어 둔 \
                 되돌아갈 곳은 {} 다 — 밟지 않은 되돌아감이다",
                match declared {
                    Some(target) => target.to_string(),
                    None => "없다".to_string(),
                }
            ),
            OpenAfterRevisitError::TargetCannotBranch { target, declared } => write!(
                f,
                "{target} 아래에서는 새 Cycle 이 날 수 없다 — 적어 둔 다음 방향이 {} 다",
                match declared {
                    Some(action) => format!("{action:?}"),
                    None => "없다".to_string(),
                }
            ),
            OpenAfterRevisitError::TargetHasNoExitWorld(id) => write!(
                f,
                "{id} 이(가) 닫혔는데 확정한 Artifact 세계가 없다 — \
                 새 Cycle 이 출발할 자리가 없다"
            ),
        }
    }
}

impl std::error::Error for OpenAfterRevisitError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            OpenAfterRevisitError::NextDirection(err) => Some(err),
            _ => None,
        }
    }
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
    /// 닫혔는데 확정한 세계가 없다 — 자식이 출발할 자리가 없다.
    NoExitWorld(CycleId),
    /// 되돌아온 자리다 — 평범한 자식이 아니라 갈래로 열린다.
    RevisitPending,
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
                 실패한 Cycle 은 자식을 만들지 않는다 — 먼저 적어 둔 조상으로 되돌아간다: \
                 `gil revisit`"
            ),
            OpenChildError::NoDirection(id) => write!(
                f,
                "{id} 에 다음 방향이 적혀 있지 않다 — 밟을 것이 없다"
            ),
            OpenChildError::NoExitWorld(id) => write!(
                f,
                "{id} 이(가) 닫혔는데 확정한 Artifact 세계가 없다 — \
                 자식 Cycle 이 출발할 자리가 없다"
            ),
            OpenChildError::RevisitPending => write!(
                f,
                "되돌아온 자리라 평범한 자식이 아니라 **갈래**로 열린다 — 같은 명령이 그것을 한다"
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

// ── 다음 방향 — 읽는 자리도 재는 자리도 하나다 ─────────────────────────────

/// 이 Cycle 아래에 **새 Cycle 이 날 수 있는가.**
///
/// `open_child` 로 자식을 여는 자리와 revisit 이 되돌아가는 자리는 **같은 것을 묻는다.**
/// 두 자리에서 각자 재면 「열 수 있다」와 「되돌아갈 수 있다」가 언젠가 갈리고, 그러면
/// 안내를 믿은 Agent 가 되돌아가서야 열 수 없음을 안다.
fn is_branch_point(cycle: &Cycle) -> bool {
    cycle.is_closed() && cycle.declared_action() == Some(OPEN_CHILD)
}

/// Cycle Report 가 다음 방향을 적을 때 쓰는 칸 이름.
const NEXT_ACTION: &str = "next_direction.action";
const NEXT_TARGET: &str = "next_direction.target_cycle_ref";
const ACTION_REVISIT: &str = "revisit";

/// 이 Cycle Report 가 **되돌아가겠다고 적었다면** 그 갈 곳의 주소.
///
/// `Ok(None)` 은 되돌아가는 방향이 아니라는 뜻이다 — 다음 방향을 아예 안 적는 Report 도,
/// `open_child` 라고 적은 Report 도 여기로 온다.
///
/// `target_cycle_ref` 는 `action` 에 따른 **조건부 칸**이라 문법의 무조건 필수 목록에 넣을
/// 수 없다(Cycle Model §11). 그래서 요구와 금지를 여기서 판정한다.
///
/// ```text
/// action == revisit  → 필수
/// action != revisit  → 금지
/// ```
///
/// **Cycle Report 에서 다음 방향을 읽는 자리는 여기 하나뿐이다.**
fn declared_revisit_target(report: &Report) -> Result<Option<CycleRef>, CycleTargetError> {
    let Some(action) = report.get(NEXT_ACTION) else {
        return Ok(None); // 다음 방향을 적지 않는 Report 다.
    };
    let target = report.get(NEXT_TARGET);

    if action != ACTION_REVISIT {
        // 되돌아가지 않는 방향에는 갈 곳이 없어야 한다. 적혀 있으면 그 값을 조용히 버리지
        // 않는다 — 버리면 사람은 자기가 적은 대상이 지켜졌다고 믿는다.
        return match target {
            Some(_) => Err(CycleTargetError::TargetNotAllowed(action.to_string())),
            None => Ok(None),
        };
    }

    let Some(raw) = target else {
        return Err(CycleTargetError::TargetMissing);
    };
    raw.parse()
        .map(Some)
        .map_err(|source| CycleTargetError::TargetUnreadable {
            value: raw.to_string(),
            source,
            suggestion: suggest(raw),
        })
}

/// 잘못 적은 값에서 **올바른 전체 주소**를 지어 준다.
///
/// `2` · `#2` · `C2` 는 전부 같은 것을 가리키려던 것이다. 다만 **다른 종류의 주소**를 적은
/// 것이라면 수를 뽑아 고쳐 주지 않는다 — `step:C1/S2` 에서 뽑은 수는 그 사람이 가리키려던
/// Cycle 이 아니고, 그럴듯한 오답은 아무 말도 안 한 것보다 나쁘다.
fn suggest(raw: &str) -> String {
    const SHAPE: &str = "cycle:C<번호>";
    if raw.contains(':') {
        return SHAPE.to_string();
    }
    let digits: String = raw.chars().filter(char::is_ascii_digit).collect();
    match digits.parse::<u32>().ok().and_then(CycleRef::new) {
        Some(cycle) => cycle.to_string(),
        None => SHAPE.to_string(),
    }
}

/// 적어 둔 Cycle 계층의 다음 방향이 이 Graph 에서 성립하지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CycleTargetError {
    /// 되돌아가겠다면서 갈 곳을 적지 않았다.
    TargetMissing,
    /// 되돌아가지 않는 방향인데 갈 곳을 적었다.
    TargetNotAllowed(String),
    /// 갈 곳이 Cycle 주소로 읽히지 않는다 — bare `2` · 화면 축약 `#2` · `C2` · 그리고
    /// **다른 종류의 주소**(`step:C1/S2` · `snapshot:A1`)가 전부 여기로 온다.
    TargetUnreadable {
        value: String,
        source: RefSyntaxError,
        suggestion: String,
    },
    /// 이 Cycle Graph 에 없는 이름이다.
    UnknownTarget(CycleRef),
    /// 아직 열려 있는 Cycle 로는 되돌아갈 수 없다.
    TargetIsOpen(CycleRef),
    /// 지금 닫는 그 Cycle 을 가리켰다.
    TargetIsItself(CycleRef),
    /// 걸어온 길 위가 아니다 — 형제·자손·무관한 Cycle 로는 되돌아갈 수 없다.
    TargetNotAnAncestor(CycleRef),
    /// 거기서는 새 Cycle 을 열 수 없다 — 되돌아가도 갈래를 낼 수 없는 자리다.
    TargetCannotBranch {
        target: CycleRef,
        declared: Option<String>,
    },
}

impl fmt::Display for CycleTargetError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            CycleTargetError::TargetMissing => write!(
                f,
                "{ACTION_REVISIT} 인데 {NEXT_TARGET} 이(가) 없다 — 어디로 돌아갈지 적어야 한다.\n\
                 여기 적을 것: {NEXT_TARGET}: cycle:C<번호>"
            ),
            CycleTargetError::TargetNotAllowed(action) => write!(
                f,
                "{action:?} 에는 {NEXT_TARGET} 을(를) 적을 수 없다 — 돌아갈 자리가 없는 방향이다"
            ),
            CycleTargetError::TargetUnreadable {
                value,
                source,
                suggestion,
            } => write!(
                f,
                "{NEXT_TARGET} 의 {value:?} 는 Cycle 주소로 읽히지 않는다 — {source}.\n\
                 여기 적을 것: {NEXT_TARGET}: {suggestion}"
            ),
            CycleTargetError::UnknownTarget(target) => write!(
                f,
                "{NEXT_TARGET} 가 가리키는 {target} 은(는) 이 Cycle Graph 에 없다"
            ),
            CycleTargetError::TargetIsOpen(target) => write!(
                f,
                "{target} 은(는) 아직 열려 있다 — 확정된 Cycle 로만 되돌아갈 수 있다"
            ),
            CycleTargetError::TargetIsItself(target) => write!(
                f,
                "{target} 은(는) 지금 닫는 그 Cycle 이다 — 자기 자신으로는 되돌아갈 수 없다.\n\
                 되돌아갈 곳은 이 Cycle 의 조상이다"
            ),
            CycleTargetError::TargetNotAnAncestor(target) => write!(
                f,
                "{target} 은(는) 이 Cycle 의 조상이 아니다 — 걸어온 길 위의 Cycle 로만 되돌아간다"
            ),
            CycleTargetError::TargetCannotBranch { target, declared } => write!(
                f,
                "{target} 아래에서는 새 Cycle 이 날 수 없다 — 적어 둔 다음 방향이 {} 다.\n\
                 되돌아갈 곳은 자식을 열겠다고 적은 Cycle 이어야 한다",
                match declared {
                    Some(action) => format!("{action:?}"),
                    None => "없다".to_string(),
                }
            ),
        }
    }
}

impl std::error::Error for CycleTargetError {}

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
