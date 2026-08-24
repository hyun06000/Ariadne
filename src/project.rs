//! Project — **세계와 자기 자신이 한 파일에 함께 눕는 자리.**
//!
//! format 2 까지 저장의 뿌리는 Cycle Graph 하나였다. format 3 에서 그것은 뿌리의 **한 칸**이
//! 되고, 그 옆에 지속적 Existence 들과 「지금 누가 행동하는가」가 선다.
//!
//! ```text
//! Project
//! ├─ cycles                 World Graph        — 여기는 어떤 곳인가
//! ├─ existences             지속적 행동 주체들  — 나는 누구인가
//! ├─ existence_states       그들의 State 객체
//! └─ current_existence_ref  지금 행동하는 존재
//! ```
//!
//! 두 축을 한 파일에 두는 것은 **원자성 때문이다**(Existence Model §4). Node 를 닫으면서
//! Journey 가 함께 확정되어야 하는데, 저장이 둘로 갈리면 그 둘을 한 번에 눕힐 수 없다.
//! 이 레포의 저장은 이미 임시 파일에 쓰고 제자리로 옮기는 꼴이라, 한 파일이면 원자성이
//! 공짜로 따라온다.
//!
//! # `gil start` 가 한 번에 만드는 것
//!
//! ```text
//! Existence X1
//! Existence State ES0        (빈 객체 · 실재해야 한다)
//! Journey revision X1@J0     (ES0 을 가리키고 나머지 head 는 null)
//! current_existence_ref      existence:X1
//! Cycle C1                   interview · Open · X1 이 소유
//! ```
//!
//! 어느 하나만 저장된 중간 상태를 허용하지 않는다. 사용자 호칭·Relation·프로젝트 목표는
//! 여기서 받지 않는다 — 그것은 설정값이 아니라 **최초 Interview 안에서 형성되는 것**이다.

use std::collections::BTreeMap;

use crate::cycle::{Cycle, CycleError, CycleKind};
use crate::cycles::{CycleId, Cycles, CyclesError};
use crate::existence::{Existence, ExistenceState};
use crate::node::NodeKind;
use crate::refs::{CycleRef, ExistenceRef, JourneyRef, StateRef, StepRef, WillRef};
use crate::report::Report;
use crate::rules::RuleSet;
use crate::will::{ActionContract, Will};

/// 최초 Existence 의 이름.
const FIRST_EXISTENCE: u32 = 1;
/// 최초 Existence State 의 이름. 초기 State 만 0 을 쓴다.
const FIRST_STATE: u32 = 0;
/// 처음 발급될 Will 의 이름. `W0` 은 없다.
const FIRST_WILL: u32 = 1;

/// 한 프로젝트의 상태 전부.
#[derive(Debug, Clone)]
pub struct Project {
    cycles: Cycles,
    existences: BTreeMap<u32, Existence>,
    existence_states: BTreeMap<u32, ExistenceState>,
    current_existence: ExistenceRef,
    /// **프로젝트 전체의** Will 이름 발급기(high-water mark).
    ///
    /// Existence 별이 아니다 — 한 Journey 안에 살더라도 다른 Existence 의 Will 과 이름을
    /// 나눠 쓰지 않는다(Node Model §2.1). 그래서 Journey 가 아니라 뿌리가 발급한다.
    next_will_id: u32,
}

impl Project {
    /// 프로젝트를 연다 — 최초 Existence 와 그가 소유한 최초 Interview Cycle 을 함께.
    ///
    /// 첫 Cycle 이 Interview 인 것은 [`Cycles::start`] 가 정한다. 여기서 더하는 것은
    /// **누가 그것을 여는가**다.
    pub fn start(rules: RuleSet) -> Project {
        let existence = ExistenceRef::new(FIRST_EXISTENCE).expect("최초 Existence 는 X1 이다");
        let state = StateRef::new(FIRST_STATE).expect("초기 State 는 ES0 이다");

        Project {
            cycles: Cycles::start(rules, existence),
            existences: BTreeMap::from([(
                FIRST_EXISTENCE,
                Existence::start(existence, state),
            )]),
            existence_states: BTreeMap::from([(FIRST_STATE, ExistenceState)]),
            current_existence: existence,
            next_will_id: FIRST_WILL,
        }
    }

    /// 다음에 발급될 Will 의 이름 값.
    pub fn next_will_id(&self) -> u32 {
        self.next_will_id
    }

    /// 지금 행동하는 존재가 하려는 행동. 없으면 **GIL 은 지어내지 않는다.**
    pub fn active_will(&self) -> Option<&Will> {
        self.current_existence().active_will()
    }

    fn existence_mut(&mut self, id: ExistenceRef) -> Option<&mut Existence> {
        self.existences.get_mut(&id.number())
    }

    /// World Graph. 읽기만 한다.
    pub fn cycles(&self) -> &Cycles {
        &self.cycles
    }

    /// World Graph — 고치기 위해.
    pub fn cycles_mut(&mut self) -> &mut Cycles {
        &mut self.cycles
    }

    /// 지금 행동하는 존재.
    pub fn current_existence_ref(&self) -> ExistenceRef {
        self.current_existence
    }

    /// 지금 행동하는 존재의 Journey.
    ///
    /// 복원 검사를 통과한 상태에서는 언제나 있다 — `current_existence_ref` 가 실재하는지는
    /// 파일을 세울 때 이미 쟀다.
    pub fn current_existence(&self) -> &Existence {
        self.existence(self.current_existence)
            .expect("current_existence_ref 는 언제나 실재하는 Existence 를 가리킨다")
    }

    /// 이름으로 하나를 찾는다.
    pub fn existence(&self, id: ExistenceRef) -> Option<&Existence> {
        self.existences.get(&id.number())
    }

    /// 만든 순서대로 전부.
    pub fn existences(&self) -> impl Iterator<Item = &Existence> {
        self.existences.values()
    }

    /// 그 이름의 State 가 실재하는가.
    pub fn has_state(&self, state: StateRef) -> bool {
        self.existence_states.contains_key(&state.number())
    }

    /// 이름순으로 전부.
    pub fn existence_states(&self) -> impl Iterator<Item = (StateRef, ExistenceState)> + '_ {
        self.existence_states.iter().map(|(number, state)| {
            (
                StateRef::new(*number).expect("발급된 State 이름은 reference 가 된다"),
                *state,
            )
        })
    }

    /// 지금 Cycle 이 적어 둔 다음 Cycle 을 연다 — **지금 행동하는 존재의 이름으로.**
    ///
    /// Node 를 연 Existence 와 닫는 Existence 는 같아야 하므로(Node Model §13-6), 여는
    /// 순간의 Current 를 그 Cycle 에 새긴다.
    pub fn open_child_cycle(&mut self, kind: CycleKind) -> Result<CycleId, CyclesError> {
        let existence = self.current_existence;
        self.cycles.open_child(kind, existence)
    }

    /// 저장이 읽어 온 값으로 다시 세운다.
    pub(crate) fn restore(
        cycles: Cycles,
        existences: BTreeMap<u32, Existence>,
        existence_states: BTreeMap<u32, ExistenceState>,
        current_existence: ExistenceRef,
        next_will_id: u32,
    ) -> Result<Project, ProjectError> {
        let project = Project {
            cycles,
            existences,
            existence_states,
            current_existence,
            next_will_id,
        };
        project.check_restored()?;
        Ok(project)
    }

    /// 되살아난 값이 **`gil start` 로 만들 수 있는 것**인지 판정한다.
    ///
    /// Cycle Graph 안쪽의 불변식은 [`Cycles`] 가 이미 쟀다. 여기서 재는 것은 **두 축이
    /// 서로 맞물리는가**뿐이다 — 존재와 그 판, 그리고 열린 Cycle 의 주인.
    fn check_restored(&self) -> Result<(), ProjectError> {
        // ① 지금 행동한다는 그 존재가 실재하는가.
        let current = self
            .existence(self.current_existence)
            .ok_or(ProjectError::UnknownCurrentExistence(self.current_existence))?;

        for existence in self.existences.values() {
            let id = existence.id();
            // ② 서 있다는 그 판이 실재하는가. 그리고 제 존재의 판인가.
            let journey = existence.current_journey();
            if journey.existence() != id {
                return Err(ProjectError::JourneyOfAnotherExistence {
                    existence: id,
                    journey,
                });
            }
            let Some(revision) = existence.current_revision() else {
                return Err(ProjectError::UnknownCurrentJourney {
                    existence: id,
                    journey,
                });
            };
            // ③ 그 판이 가리키는 State 가 실재하는가. **비어 있을 수 없는 자리다.**
            let state = revision.existence_state();
            if !self.has_state(state) {
                return Err(ProjectError::UnknownExistenceState {
                    existence: id,
                    state,
                });
            }
        }

        // ④ 열린 Cycle 은 **지금 행동하는 존재**의 것이어야 한다.
        //
        // Node 를 연 Existence 와 닫는 Existence 는 같아야 하고, 열린 Node 가 있는 동안
        // 전환을 막는다. 그러므로 파일에서 이 둘이 갈렸다면 걸어서 만들 수 없는 상태다.
        for cycle in self.cycles.nodes() {
            if !cycle.is_closed() && cycle.existence() != current.id() {
                return Err(ProjectError::OpenCycleOfAnotherExistence {
                    cycle: cycle.id(),
                    owner: cycle.existence(),
                    current: current.id(),
                });
            }
        }

        self.check_restored_wills()?;
        self.check_restored_provenance()?;
        Ok(())
    }

    /// Will 들이 **걸어서 만들 수 있는 꼴**인가.
    ///
    /// 여기서 재는 것에 시각은 하나도 없다. 이름의 발급 순서, `done_wills` 의 append 순서와
    /// reference 만으로 잰다 — 시각을 저장하지 않기로 했으므로 그것을 근거로 삼는 검사를
    /// 만들지 않는다.
    fn check_restored_wills(&self) -> Result<(), ProjectError> {
        if self.next_will_id < FIRST_WILL {
            return Err(ProjectError::WillAllocatorTooSmall {
                next_will_id: self.next_will_id,
                used: FIRST_WILL,
            });
        }

        let mut seen: Vec<WillRef> = Vec::new();
        let mut actives: Vec<WillRef> = Vec::new();

        for existence in self.existences.values() {
            let owner = existence.id();
            let journey = existence.journey();

            // ① 이름은 프로젝트 전체에서 유일하고, 발급기보다 앞서 있어야 한다.
            //    ② 그리고 같은 이름이 register 와 Done 목록에 동시에 있을 수 없다.
            let mut last_done: Option<WillRef> = None;
            for will in journey.done_wills().iter().chain(journey.active_will()) {
                let id = will.id();
                if seen.contains(&id) {
                    return Err(ProjectError::DuplicateWill(id));
                }
                if id.number() >= self.next_will_id {
                    return Err(ProjectError::WillAllocatorTooSmall {
                        next_will_id: self.next_will_id,
                        used: id.number(),
                    });
                }
                seen.push(id);
                // ③ Will 은 그 Journey 를 가진 존재의 것이다.
                if will.existence() != owner {
                    return Err(ProjectError::WillOfAnotherExistence {
                        will: id,
                        owner: will.existence(),
                        journey: owner,
                    });
                }
            }

            // ④ Done 목록은 append-only 다. 한 존재는 한 번에 하나씩만 걸고 끝내므로
            //    끝낸 순서는 곧 발급 순서다 — 이름이 오름차순이 아니면 순서가 위조됐다.
            for will in journey.done_wills() {
                if let Some(previous) = last_done
                    && previous.number() >= will.id().number()
                {
                    return Err(ProjectError::DoneWillsOutOfOrder {
                        existence: owner,
                        previous,
                        found: will.id(),
                    });
                }
                last_done = Some(will.id());
            }

            if let Some(active) = journey.active_will() {
                actives.push(active.id());
            }

            self.check_restored_revisions(existence)?;
        }

        // ⑤ 하려는 행동은 프로젝트 전체에서 하나다 — 열린 Node 가 있는 동안 존재를
        //    바꿀 수 없으므로 둘이 동시에 걸린 상태는 걸어서 만들 수 없다.
        if actives.len() > 1 {
            return Err(ProjectError::TwoActiveWills(actives));
        }

        // ⑥ 걸린 행동은 **지금 행동하는 존재**의 것이고, ⑦ 지금 열려 있는 가장 깊은
        //    실행형 자리를 향해야 한다. 그리고 그 둘은 함께 있거나 함께 없어야 한다.
        let active = self.current_existence().active_will();
        let open_step = self.deepest_open_action_step();
        match (active, open_step) {
            (None, None) => {}
            (Some(will), None) => {
                return Err(ProjectError::ActiveWillWithoutOpenStep {
                    will: will.id(),
                    target: will.target(),
                });
            }
            (None, Some(step)) => return Err(ProjectError::OpenStepWithoutActiveWill(step)),
            (Some(will), Some(step)) => {
                if will.target() != step {
                    return Err(ProjectError::ActiveWillTargetsElsewhere {
                        will: will.id(),
                        target: will.target(),
                        open: step,
                    });
                }
            }
        }
        // 다른 존재가 행동을 걸어 둔 채 지금 행동하는 것이 바뀐 상태도 없다.
        if let Some(other) = actives
            .iter()
            .find(|id| active.is_none_or(|will| will.id() != **id))
        {
            return Err(ProjectError::ActiveWillOfAnotherExistence {
                will: *other,
                current: self.current_existence,
            });
        }
        Ok(())
    }

    /// 판들의 `will_head_ref` 가 Done 목록과 맞물리는가.
    fn check_restored_revisions(&self, existence: &Existence) -> Result<(), ProjectError> {
        let owner = existence.id();
        let journey = existence.journey();
        let index_of = |head: WillRef| {
            journey
                .done_wills()
                .iter()
                .position(|will| will.id() == head)
        };

        // 판 번호가 오르면 Will 머리도 뒤로 가지 않는다. 앞선 판이 나중의 Done 을
        // 가리키면 그 판은 제 시점보다 뒤를 본 것이다 — 시각 없이 append 순서로 잰다.
        let mut floor: Option<usize> = None;
        for (number, revision) in journey.revisions() {
            let Some(head) = revision.will_head() else {
                continue;
            };
            let Some(at) = index_of(head) else {
                return Err(ProjectError::UnknownWillHead {
                    existence: owner,
                    revision: JourneyRef::new(owner, number),
                    head,
                });
            };
            if floor.is_some_and(|previous| at < previous) {
                return Err(ProjectError::WillHeadWentBackwards {
                    existence: owner,
                    revision: JourneyRef::new(owner, number),
                    head,
                });
            }
            floor = Some(at);
        }

        // 그리고 지금 서 있는 판의 머리는 **지금까지 마지막 Done** 이다.
        let current = existence
            .current_revision()
            .expect("서 있는 판이 실재하는지는 앞에서 이미 쟀다");
        let last = journey.last_done_will().map(|will| will.id());
        if current.will_head() != last {
            return Err(ProjectError::CurrentWillHeadIsNotTheLast {
                existence: owner,
                head: current.will_head(),
                last,
            });
        }
        Ok(())
    }

    /// 닫힌 Node 의 provenance 가 실재하는 판을 가리키고, 그 판이 그 행동을 확정했는가.
    fn check_restored_provenance(&self) -> Result<(), ProjectError> {
        for cycle in self.cycles.nodes() {
            if let Some(journey) = cycle.journey() {
                self.must_have_revision(journey, cycle.existence())?;
            }
            if cycle.is_closed() && cycle.journey().is_none() {
                return Err(ProjectError::ClosedCycleWithoutJourney(cycle.id().to_ref()));
            }
            if !cycle.is_closed() && cycle.journey().is_some() {
                return Err(ProjectError::JourneyOnOpenCycle(cycle.id().to_ref()));
            }

            for node in cycle.steps().nodes() {
                let Some(journey) = node.journey else {
                    continue; // 열린 자리다 — 걷기가 이미 짝을 쟀다.
                };
                let step = cycle.step_ref(node.id);
                self.must_have_revision(journey, node.existence)?;

                // **닫힌 실행형 Node 의 판은 그 Node 의 행동을 확정한 판이다.**
                // 통합 Close 가 새 판의 머리를 방금 끝낸 Will 로 두므로, 그 둘은 같다.
                let existence = self
                    .existence(node.existence)
                    .expect("방금 실재를 확인했다");
                let head = existence
                    .journey()
                    .revision(journey.revision())
                    .and_then(|revision| revision.will_head());
                let done = existence
                    .journey()
                    .done_wills()
                    .iter()
                    .find(|will| will.target() == step)
                    .map(|will| will.id());
                if head.is_none() || head != done {
                    return Err(ProjectError::JourneyDoesNotHoldItsWill {
                        step,
                        journey,
                        head,
                        expected: done,
                    });
                }
            }
        }
        Ok(())
    }

    fn must_have_revision(
        &self,
        journey: JourneyRef,
        owner: ExistenceRef,
    ) -> Result<(), ProjectError> {
        if journey.existence() != owner {
            return Err(ProjectError::ProvenanceOfAnotherExistence { journey, owner });
        }
        match self
            .existence(owner)
            .and_then(|existence| existence.journey().revision(journey.revision()))
        {
            Some(_) => Ok(()),
            None => Err(ProjectError::UnknownProvenanceJourney(journey)),
        }
    }

    /// 지금 실제 행동을 수행하는 **가장 깊은 실행형 Open Node.**
    ///
    /// 한 번에 열린 Cycle 은 하나이고 그 안에 열린 Step 도 하나다. 컨테이너가 열려 있다는
    /// 이유만으로 가상의 자리를 만들지 않는다(Will Model §5).
    fn deepest_open_action_step(&self) -> Option<StepRef> {
        let cycle = self.cycles.current();
        if cycle.is_closed() {
            return None;
        }
        cycle.step_now_open().map(|at| cycle.step_ref(at))
    }

    /// 저장이 적어 갈 값들.
    pub(crate) fn parts(
        &self,
    ) -> (
        &Cycles,
        &BTreeMap<u32, Existence>,
        &BTreeMap<u32, ExistenceState>,
        ExistenceRef,
    ) {
        (
            &self.cycles,
            &self.existences,
            &self.existence_states,
            self.current_existence,
        )
    }
}

/// 지금 Cycle 안에서 다음에 할 수 있는 것들 — 편의를 위해 한 층 위로 올린다.
impl Project {
    pub fn current_cycle(&self) -> &Cycle {
        self.cycles.current()
    }
}

/// 방금 연 실행형 자리와 그와 함께 걸린 행동.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Opened {
    pub step: StepRef,
    pub kind: NodeKind,
    pub will: WillRef,
}

/// 방금 닫은 실행형 자리 — 그 행동이 끝났고, 그것을 확정한 판이 하나 늘었다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Closed {
    pub step: StepRef,
    pub kind: NodeKind,
    pub will: WillRef,
    pub journey: JourneyRef,
}

/// 방금 닫은 Cycle — **판은 늘지 않는다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ClosedCycle {
    pub cycle: CycleRef,
    pub kind: CycleKind,
    pub journey: JourneyRef,
}

/// **한 번에 눕는 것들.** 세계와 존재가 한 파일에 함께 사는 까닭이 여기 있다.
///
/// 실행형 Node 의 Open 과 Close 는 두 축을 동시에 움직인다 — Step 이 나고 Will 이 걸리고,
/// Step 이 닫히고 Will 이 끝나고 판이 하나 는다. 어느 하나만 저장된 중간 상태를 허용하지
/// 않으므로(Existence Model §4), 이 문들은 **통째로 복제해 두고 전부 성공했을 때만
/// 갈아 끼운다.** 중간에 어디서 실패하든 복제본을 버리면 그만이라, 되돌리는 코드를
/// 따로 짜지 않는다 — 되돌리는 코드는 언젠가 한 줄을 빠뜨린다.
impl Project {
    /// 실행형 Step 하나와 그것을 target 으로 한 Active Will 을 **함께** 연다.
    ///
    /// 계약 세 칸은 Agent 가 적는다. GIL 은 Node Kind 만 보고 그 내용을 지어내지 않는다
    /// (Will Model §7) — `question` 이라는 이름은 *무엇을* 물을지 모른다.
    pub fn open_action_step(
        &mut self,
        kind: NodeKind,
        contract: ActionContract,
    ) -> Result<Opened, ActionError> {
        let mut next = self.clone();
        let owner = next.current_existence;

        // ② 하려는 행동은 하나다. 걸린 것이 있으면 새로 열지 않는다.
        if let Some(active) = next.current_existence().active_will() {
            return Err(ActionError::WillAlreadyActive {
                will: active.id(),
                target: active.target(),
            });
        }

        // ③④ 문법 판정이 먼저다 — 거절되면 이름도 Will 도 나지 않는다.
        let cycle = next.cycles.current_mut();
        cycle.open_step(kind)?;
        let opened = cycle.steps().current().expect("방금 열었다");
        let target = cycle.step_ref(opened);

        // ⑤ 이름을 발급하고 ⑦ 그 자리에 못 박는다.
        let id = WillRef::new(next.next_will_id).expect("next_will_id 는 언제나 1 이상이다");
        next.next_will_id += 1;
        let will = contract.into_will(id, owner, target);
        next.existence_mut(owner)
            .expect("current_existence_ref 는 실재한다")
            .journey_mut()
            .set_active_will(will);

        // ⑧⑨⑩ 여기까지 왔으면 전부 성공이다.
        *self = next;
        Ok(Opened {
            step: target,
            kind,
            will: id,
        })
    }

    /// 실행형 Step 을 닫으며 **그 행동을 끝내고 판을 하나 올린다.**
    ///
    /// Will 의 `done` 은 행동을 수행했다는 뜻이지 가설이 성공했다는 뜻이 아니다
    /// (Will Model §6) — 실패를 관측하고 닫는 Verify 도 제 행동은 끝낸 것이다.
    pub fn close_action_step(&mut self, report: Report) -> Result<Closed, ActionError> {
        let mut next = self.clone();
        let owner = next.current_existence;

        let cycle = next.cycles.current();
        let Some(at) = cycle.step_now_open() else {
            return Err(ActionError::NothingOpen);
        };
        let node = cycle.steps().node(at).expect("방금 자리를 받아 왔다");
        let (kind, target) = (node.kind, cycle.step_ref(at));

        // ① 연 존재와 닫는 존재는 같아야 한다(Node Model §2).
        if node.existence != owner {
            return Err(ActionError::NotTheOwner {
                target,
                owner: node.existence,
                current: owner,
            });
        }

        // ②③④ 걸린 행동이 있고, 그것이 **이 자리의** 행동인가.
        let existence = next.existence(owner).expect("current_existence_ref 는 실재한다");
        let Some(active) = existence.active_will() else {
            return Err(ActionError::NoActiveWill { target });
        };
        if active.existence() != owner {
            return Err(ActionError::WillOfAnotherExistence {
                will: active.id(),
                owner: active.existence(),
                current: owner,
            });
        }
        if active.target() != target {
            return Err(ActionError::WillTargetsElsewhere {
                will: active.id(),
                target: active.target(),
                here: target,
            });
        }

        // ⑧ 판의 번호를 먼저 정한다 — Node 에 적을 값이라 Report 검증보다 앞선다.
        //    아직 아무것도 바꾸지 않았다.
        let number = existence.journey().next_revision();
        let journey = JourneyRef::new(owner, number);

        // ⑤⑫ Report 를 재고 Node 를 닫는다. 거절되면 복제본째 버린다.
        next.cycles.current_mut().close_step_into(report, journey)?;

        // ⑥⑦ 같은 객체를 Done 목록 끝으로 **옮긴다** — 베끼지 않는다.
        let existence = next.existence_mut(owner).expect("방금 읽은 존재다");
        let base = existence
            .current_revision()
            .expect("서 있는 판은 언제나 실재한다")
            .clone();
        let will = existence
            .journey_mut()
            .complete_active_will()
            .expect("방금 걸려 있는 것을 봤다");

        // ⑨ 이전 머리들을 그대로 물려받고 Will 머리만 옮긴다.
        let pushed = existence.journey_mut().push_revision(base.with_will_head(will));
        debug_assert_eq!(pushed, number, "판 번호를 먼저 정한 값과 실제가 갈렸다");
        // ⑩ 그리고 그 판으로 옮겨 선다.
        existence.stand_at(journey);

        *self = next;
        Ok(Closed {
            step: target,
            kind,
            will,
            journey,
        })
    }

    /// 컨테이너인 Cycle 을 닫는다 — **Will 도 판도 만들지 않는다.**
    ///
    /// Cycle 은 내부 Graph 를 담는 그릇이라 장기 Active Will 을 점유하지 않는다
    /// (Will Model §5). 그래서 닫힐 때 확정할 새 Journey 내용이 없고, 지금 서 있는 판을
    /// 그대로 provenance 로 적는다(Existence Model §4).
    pub fn close_cycle(&mut self, report: Report) -> Result<ClosedCycle, ActionError> {
        let mut next = self.clone();
        let owner = next.current_existence;
        let cycle = next.cycles.current();
        let (id, kind) = (cycle.id().to_ref(), cycle.kind());

        if cycle.existence() != owner {
            return Err(ActionError::CycleNotOwned {
                cycle: id,
                owner: cycle.existence(),
                current: owner,
            });
        }
        // 안에 열린 자리가 있으면 닫지 않는다. `at_exit` 도 이것을 막지만, 여기서
        // 이유를 따로 말한다 — 사람이 할 일이 다르기 때문이다(그 자리를 먼저 닫아라).
        if let Some(at) = cycle.step_now_open() {
            return Err(ActionError::InnerStepStillOpen {
                cycle: id,
                step: cycle.step_ref(at),
            });
        }
        if let Some(active) = next.current_existence().active_will() {
            return Err(ActionError::WillStillActive {
                will: active.id(),
                target: active.target(),
            });
        }

        let journey = next.current_existence().current_journey();
        next.cycles.current_mut().close_into(report, journey)?;

        *self = next;
        Ok(ClosedCycle {
            cycle: id,
            kind,
            journey,
        })
    }
}

/// 통합 transaction 이 거절한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ActionError {
    /// 닫을 실행형 자리가 없다.
    NothingOpen,
    /// 이미 걸린 행동이 있다 — 하려는 행동은 하나다.
    WillAlreadyActive { will: WillRef, target: StepRef },
    /// 열린 자리는 있는데 걸린 행동이 없다.
    NoActiveWill { target: StepRef },
    /// 걸린 행동이 다른 자리를 향한다.
    WillTargetsElsewhere {
        will: WillRef,
        target: StepRef,
        here: StepRef,
    },
    /// 걸린 행동의 주인이 지금 행동하는 존재가 아니다.
    WillOfAnotherExistence {
        will: WillRef,
        owner: ExistenceRef,
        current: ExistenceRef,
    },
    /// 이 자리를 연 존재가 지금 행동하는 존재가 아니다.
    NotTheOwner {
        target: StepRef,
        owner: ExistenceRef,
        current: ExistenceRef,
    },
    /// 이 Cycle 을 연 존재가 지금 행동하는 존재가 아니다.
    CycleNotOwned {
        cycle: CycleRef,
        owner: ExistenceRef,
        current: ExistenceRef,
    },
    /// Cycle 안에 아직 열린 자리가 있다.
    InnerStepStillOpen { cycle: CycleRef, step: StepRef },
    /// Cycle 을 닫으려는데 아직 걸린 행동이 있다.
    WillStillActive { will: WillRef, target: StepRef },
    /// 세계 쪽이 거절했다 — 문법·전이·Report.
    Cycle(CycleError),
}

impl From<CycleError> for ActionError {
    fn from(err: CycleError) -> Self {
        ActionError::Cycle(err)
    }
}

impl std::fmt::Display for ActionError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ActionError::NothingOpen => write!(f, "지금 열려 있는 실행형 자리가 없다"),
            ActionError::WillAlreadyActive { will, target } => write!(
                f,
                "{will} 이(가) 이미 {target} 에 걸려 있다 — 지금 하려는 행동은 하나다.\n\
                 그 자리를 먼저 닫아라"
            ),
            ActionError::NoActiveWill { target } => write!(
                f,
                "{target} 이(가) 열려 있는데 걸린 행동이 없다 — 실행형 자리는 Will 과 함께 \
                 열린다. 이 파일은 걸어서 만든 것이 아니다"
            ),
            ActionError::WillTargetsElsewhere { will, target, here } => write!(
                f,
                "{will} 은(는) {target} 을(를) 향하는데 지금 닫으려는 자리는 {here} 다"
            ),
            ActionError::WillOfAnotherExistence {
                will,
                owner,
                current,
            } => write!(
                f,
                "{will} 의 주인은 {owner} 이고 지금 행동하는 것은 {current} 다"
            ),
            ActionError::NotTheOwner {
                target,
                owner,
                current,
            } => write!(
                f,
                "{target} 을(를) 연 것은 {owner} 이고 지금 행동하는 것은 {current} 다 — \
                 하나의 Node 를 시작한 존재와 끝내는 존재는 같아야 한다"
            ),
            ActionError::CycleNotOwned {
                cycle,
                owner,
                current,
            } => write!(
                f,
                "{cycle} 을(를) 연 것은 {owner} 이고 지금 행동하는 것은 {current} 다"
            ),
            ActionError::InnerStepStillOpen { cycle, step } => write!(
                f,
                "{cycle} 안의 {step} 이(가) 아직 열려 있다 — 안이 끝나야 그릇이 닫힌다"
            ),
            ActionError::WillStillActive { will, target } => write!(
                f,
                "{will} 이(가) {target} 에 아직 걸려 있다 — 컨테이너를 닫기 전에 \
                 그 행동을 끝낸다"
            ),
            ActionError::Cycle(err) => write!(f, "{err}"),
        }
    }
}

impl std::error::Error for ActionError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            ActionError::Cycle(err) => Some(err),
            _ => None,
        }
    }
}

/// 두 축이 서로 맞물리지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ProjectError {
    /// 지금 행동한다는 존재가 이 프로젝트에 없다.
    UnknownCurrentExistence(ExistenceRef),
    /// 서 있다는 판이 그 Journey 에 없다.
    UnknownCurrentJourney {
        existence: ExistenceRef,
        journey: crate::refs::JourneyRef,
    },
    /// 다른 Existence 의 판을 제 것이라 한다.
    JourneyOfAnotherExistence {
        existence: ExistenceRef,
        journey: crate::refs::JourneyRef,
    },
    /// 그 판이 가리키는 State 가 없다.
    UnknownExistenceState {
        existence: ExistenceRef,
        state: StateRef,
    },
    /// 열린 Cycle 의 주인이 지금 행동하는 존재가 아니다.
    OpenCycleOfAnotherExistence {
        cycle: CycleId,
        owner: ExistenceRef,
        current: ExistenceRef,
    },

    // ── Will ──────────────────────────────────────────────────────────────
    /// 발급기가 이미 쓰인 이름보다 뒤에 있다 — 다음 Will 이 남의 이름을 받게 된다.
    WillAllocatorTooSmall { next_will_id: u32, used: u32 },
    /// 같은 Will 이름이 두 번 실렸다.
    DuplicateWill(WillRef),
    /// Will 의 주인이 그 Journey 를 가진 존재가 아니다.
    WillOfAnotherExistence {
        will: WillRef,
        owner: ExistenceRef,
        journey: ExistenceRef,
    },
    /// Done 목록의 순서가 발급 순서와 어긋난다.
    DoneWillsOutOfOrder {
        existence: ExistenceRef,
        previous: WillRef,
        found: WillRef,
    },
    /// 하려는 행동이 둘 이상 걸려 있다.
    TwoActiveWills(Vec<WillRef>),
    /// 걸린 행동은 있는데 열린 실행형 자리가 없다.
    ActiveWillWithoutOpenStep { will: WillRef, target: StepRef },
    /// 열린 실행형 자리는 있는데 걸린 행동이 없다.
    OpenStepWithoutActiveWill(StepRef),
    /// 걸린 행동이 지금 열린 자리가 아닌 곳을 향한다.
    ActiveWillTargetsElsewhere {
        will: WillRef,
        target: StepRef,
        open: StepRef,
    },
    /// 지금 행동하지 않는 존재가 행동을 걸어 두고 있다.
    ActiveWillOfAnotherExistence {
        will: WillRef,
        current: ExistenceRef,
    },
    /// 판이 실재하지 않는 Done Will 을 머리로 가리킨다.
    UnknownWillHead {
        existence: ExistenceRef,
        revision: JourneyRef,
        head: WillRef,
    },
    /// 앞선 판이 나중의 Done Will 을 가리킨다 — 제 시점보다 뒤를 봤다.
    WillHeadWentBackwards {
        existence: ExistenceRef,
        revision: JourneyRef,
        head: WillRef,
    },
    /// 지금 서 있는 판의 머리가 마지막 Done Will 이 아니다.
    CurrentWillHeadIsNotTheLast {
        existence: ExistenceRef,
        head: Option<WillRef>,
        last: Option<WillRef>,
    },

    // ── Node provenance ───────────────────────────────────────────────────
    /// 닫힌 Cycle 에 닫은 판이 없다.
    ClosedCycleWithoutJourney(CycleRef),
    /// 아직 열린 Cycle 에 닫은 판이 적혀 있다.
    JourneyOnOpenCycle(CycleRef),
    /// provenance 가 다른 존재의 판을 가리킨다.
    ProvenanceOfAnotherExistence {
        journey: JourneyRef,
        owner: ExistenceRef,
    },
    /// provenance 가 실재하지 않는 판을 가리킨다.
    UnknownProvenanceJourney(JourneyRef),
    /// 닫힌 자리의 판이 그 자리의 Done Will 을 확정한 판이 아니다.
    JourneyDoesNotHoldItsWill {
        step: StepRef,
        journey: JourneyRef,
        head: Option<WillRef>,
        expected: Option<WillRef>,
    },
}

/// 없는 것도 사람이 읽는 꼴로.
fn or_none(will: Option<WillRef>) -> String {
    match will {
        Some(will) => will.to_string(),
        None => "없음".to_string(),
    }
}

impl std::fmt::Display for ProjectError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ProjectError::UnknownCurrentExistence(id) => {
                write!(f, "{id} 은(는) 이 프로젝트에 없다 — 지금 누가 행동하는지 알 수 없다")
            }
            ProjectError::UnknownCurrentJourney { existence, journey } => write!(
                f,
                "{existence} 이(가) {journey} 에 서 있다는데 그 판이 없다"
            ),
            ProjectError::JourneyOfAnotherExistence { existence, journey } => write!(
                f,
                "{existence} 이(가) {journey} 를 제 판이라 한다 — Journey 는 제 존재의 것이다"
            ),
            ProjectError::UnknownExistenceState { existence, state } => write!(
                f,
                "{existence} 의 판이 {state} 를 가리키는데 그런 State 가 없다 — \
                 Existence 가 있는데 State 가 없는 상태는 없다"
            ),
            ProjectError::OpenCycleOfAnotherExistence {
                cycle,
                owner,
                current,
            } => write!(
                f,
                "{cycle} 이(가) 열려 있는데 그 주인은 {owner} 이고 지금 행동하는 것은 \
                 {current} 다 — 열린 Node 가 있는 동안 존재를 바꾸지 않는다"
            ),

            ProjectError::WillAllocatorTooSmall { next_will_id, used } => write!(
                f,
                "next_will_id 가 {next_will_id} 인데 W{used} 가 이미 쓰였다 — \
                 다음 Will 이 남의 이름을 받게 된다"
            ),
            ProjectError::DuplicateWill(will) => write!(
                f,
                "{will} 이(가) 두 번 실렸다 — Will 이름은 프로젝트 전체에서 유일하다"
            ),
            ProjectError::WillOfAnotherExistence {
                will,
                owner,
                journey,
            } => write!(
                f,
                "{will} 의 주인은 {owner} 인데 {journey} 의 Journey 에 실려 있다 — \
                 Will 은 제 존재의 Journey 에 산다"
            ),
            ProjectError::DoneWillsOutOfOrder {
                existence,
                previous,
                found,
            } => write!(
                f,
                "{existence} 의 done_wills 에서 {previous} 다음에 {found} 이(가) 온다 — \
                 한 존재는 한 번에 하나씩 걸고 끝내므로 끝낸 순서는 발급 순서다"
            ),
            ProjectError::TwoActiveWills(wills) => write!(
                f,
                "하려는 행동이 둘 이상 걸려 있다 ({}) — 현재 Will 은 하나다",
                wills
                    .iter()
                    .map(WillRef::to_string)
                    .collect::<Vec<_>>()
                    .join(", ")
            ),
            ProjectError::ActiveWillWithoutOpenStep { will, target } => write!(
                f,
                "{will} 이(가) {target} 에 걸려 있는데 그 자리가 열려 있지 않다 — \
                 실행형 Node 와 Active Will 은 함께 열리고 함께 끝난다"
            ),
            ProjectError::OpenStepWithoutActiveWill(step) => write!(
                f,
                "{step} 이(가) 열려 있는데 걸린 행동이 없다 — 무엇을 하려고 연 자리인지 \
                 파일이 말하지 못한다"
            ),
            ProjectError::ActiveWillTargetsElsewhere { will, target, open } => write!(
                f,
                "{will} 은(는) {target} 을(를) 향하는데 지금 열려 있는 자리는 {open} 다 — \
                 Current Will 은 가장 깊은 실행형 Open Node 하나에 대응한다"
            ),
            ProjectError::ActiveWillOfAnotherExistence { will, current } => write!(
                f,
                "{will} 이(가) 걸려 있는데 그 주인은 지금 행동하는 {current} 가 아니다 — \
                 열린 Node 가 있는 동안 존재를 바꾸지 않는다"
            ),
            ProjectError::UnknownWillHead {
                existence,
                revision,
                head,
            } => write!(
                f,
                "{existence} 의 {revision} 이(가) {head} 를 머리로 가리키는데 그런 \
                 Done Will 이 없다"
            ),
            ProjectError::WillHeadWentBackwards {
                existence,
                revision,
                head,
            } => write!(
                f,
                "{existence} 의 {revision} 이(가) {head} 를 가리키는데 그것은 뒤 판이 \
                 가리키는 것보다 나중에 끝난 행동이다 — 판은 제 시점보다 뒤를 보지 않는다"
            ),
            ProjectError::CurrentWillHeadIsNotTheLast {
                existence,
                head,
                last,
            } => write!(
                f,
                "{existence} 이(가) 서 있는 판의 머리는 {} 인데 마지막으로 끝낸 행동은 \
                 {} 다",
                or_none(*head),
                or_none(*last)
            ),

            ProjectError::ClosedCycleWithoutJourney(cycle) => write!(
                f,
                "{cycle} 이(가) 닫혔다는데 어느 판에서 닫았는지가 없다"
            ),
            ProjectError::JourneyOnOpenCycle(cycle) => write!(
                f,
                "{cycle} 이(가) 아직 열려 있는데 닫은 판이 적혀 있다"
            ),
            ProjectError::ProvenanceOfAnotherExistence { journey, owner } => write!(
                f,
                "{owner} 이(가) 연 Node 가 {journey} 에서 닫혔다고 적혀 있다 — \
                 닫은 판은 그 Node 를 연 존재의 판이다"
            ),
            ProjectError::UnknownProvenanceJourney(journey) => {
                write!(f, "{journey} 라는 판이 없다")
            }
            ProjectError::JourneyDoesNotHoldItsWill {
                step,
                journey,
                head,
                expected,
            } => write!(
                f,
                "{step} 이(가) {journey} 에서 닫혔다는데 그 판의 머리는 {} 이고 이 자리의 \
                 행동은 {} 다 — 실행형 Close 는 방금 끝낸 행동을 그 판의 머리로 둔다",
                or_none(*head),
                or_none(*expected)
            ),
        }
    }
}

impl std::error::Error for ProjectError {}
