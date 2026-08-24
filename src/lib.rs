//! GIL Grammar v0.1 — 읽고, 검증하고, 한 걸음씩 걷는 최소 구현.
//!
//! 이 크레이트가 하는 일은 셋뿐이다.
//!
//! 1. `gil-spec.yaml` 을 읽는다.
//! 2. 그 규칙으로 Node 의 **여는 전이**와 **닫는 조건**을 판정한다.
//! 3. 그 판정 위에서 **한 Cycle 안의 Step 을 걷는다**([`Walk`]) — Node 마다 이름([`NodeId`])이
//!    붙고, 부모는 **태어날 때 기록**되며, 적어 둔 되돌아감을 밟아 갈래를 낸다.
//! 4. 그 걷기를 **Cycle 하나가 소유한다**([`Cycle`]) — 안의 Outcome 이 닫혀도 Cycle 은 아직
//!    열려 있고, **Cycle Report 를 써야 닫힌다**. 닫힘의 진실원은 Cycle 하나뿐이다.
//! 5. 성공한 Cycle 이 **적어 둔 방향을 밟아 다음 Cycle 을 연다**([`Cycles`]) — 부모의 Step 은
//!    한 개도 복사하지 않고, 이어받는 것은 `parent` 를 따라 읽는 Cycle Report 다.
//! 6. 그것을 **디스크에 눕히고 다시 세운다**([`save`]·[`load`]) — Agent 의 한 턴은 한
//!    프로세스라, 저장이 없으면 연 것을 다음 턴에 닫지 못한다.
//! 7. 그리고 그 기록을 **거리에 따른 해상도로 읽는다**([`story`]·[`context`]) — 사람은 지금을
//!    이해하려 읽고([`story`]), 아무 대화도 물려받지 않은 새 세션은 이어 걸으려 읽는다
//!    ([`context`]: 지나온 Cycle 은 Cycle Report 까지, 지금 Cycle 은 Step Report 까지).
//!
//! 규칙은 코드에 있지 않다 — 전부 `gil-spec.yaml` 에 있다. 여기 있는 것은 그 파일을
//! 읽는 절차와, 읽은 값을 그대로 적용하는 판정뿐이다.
//!
//! 8. 그리고 그 전부를 **한 프로젝트가 소유한다**([`Project`]) — World Graph 옆에 지속적
//!    [`Existence`] 와 「지금 누가 행동하는가」가 함께 눕는다. `gil start` 는 최초 존재와
//!    그가 소유한 **최초 Interview Cycle** 을 한 번의 원자적 저장으로 만든다.
//!
//! 규칙은 코드에 있지 않다 — 전부 `gil-spec.yaml` 에 있다. 여기 있는 것은 그 파일을
//! 읽는 절차와, 읽은 값을 그대로 적용하는 판정뿐이다.
//!
//! 9. 그리고 **지금 무엇을 하려는지**가 세계와 함께 눕는다([`Will`]) — 실행형 Step 은
//!    행동 계약과 함께 열리고([`Project::open_action_step`]), 닫힐 때 그 행동이 끝나며
//!    Journey 판이 하나 늘고 Node 가 그 판을 provenance 로 지닌다
//!    ([`Project::close_action_step`]). 컨테이너인 Cycle 은 Will 도 판도 만들지 않는다.
//!
//! 아직 없는 것(다음 Step 의 몫): Existence 전환 · Participant 와 Relation ·
//! Knowledge·Memory 의 내용 · Artifact snapshot · Cycle 수준의 되돌아감 · Chain.
//!
//! ```
//! use gil::{CycleKind, Node, NodeKind, Project, Report, RuleSet};
//!
//! let rules = RuleSet::from_path(concat!(
//!     env!("CARGO_MANIFEST_DIR"),
//!     "/spec/gil-spec.yaml"
//! ))
//! .unwrap();
//!
//! // 같은 자리에서도 **Cycle Kind 가 문법을 가른다.**
//! let entry = Node::cycle_entry();
//! assert!(rules.validate_open(CycleKind::Interview, entry, NodeKind::Question).is_ok());
//! assert!(rules.validate_open(CycleKind::Interview, entry, NodeKind::Define).is_err());
//! assert!(rules.validate_open(CycleKind::Experiment, entry, NodeKind::Define).is_ok());
//! assert!(rules.validate_open(CycleKind::Experiment, entry, NodeKind::Question).is_err());
//!
//! // 닫히지 않은 부모 아래로는 아무것도 열 수 없다.
//! assert!(
//!     rules
//!         .validate_open(
//!             CycleKind::Experiment,
//!             Node::open(NodeKind::Define),
//!             NodeKind::Hypothesis,
//!         )
//!         .is_err()
//! );
//!
//! // 닫으려면 그 종류가 요구하는 칸이 다 있어야 한다.
//! let report = Report::new().with("problem", "…").with("success_condition", "…");
//! assert!(
//!     rules
//!         .validate_close(CycleKind::Experiment, NodeKind::Define, &report)
//!         .is_ok()
//! );
//!
//! // 프로젝트는 **최초 Interview Cycle** 하나로 시작한다.
//! let mut project = Project::start(rules);
//! let first = project.cycles().current();
//! assert_eq!(first.kind(), CycleKind::Interview);
//! assert_eq!(first.existence(), project.current_existence_ref());
//! assert_eq!(project.cycles().openable_here(), vec![NodeKind::Question]);
//!
//! // 그 존재는 빈 초기 판 하나를 지닌다 — State 만은 비울 수 없다.
//! let journey = project.current_existence().current_journey();
//! assert_eq!(journey.to_string(), "journey:X1@J0");
//! let revision = project.current_existence().current_revision().unwrap();
//! assert_eq!(revision.existence_state().to_string(), "state:ES0");
//! assert!(revision.knowledge_head().is_none());
//! assert!(project.active_will().is_none(), "GIL 은 하려는 일을 지어내지 않는다");
//!
//! // 실행형 Step 은 **무엇을 하려는지 적어야** 열린다.
//! use gil::ActionContract;
//! let opened = project
//!     .open_action_step(
//!         NodeKind::Question,
//!         ActionContract::new("의도를 확인한다", "선택지와 함께 묻는다", "원문 응답을 얻는다"),
//!     )
//!     .unwrap();
//! assert_eq!(project.active_will().unwrap().target(), opened.step);
//! ```

mod context;
mod contract;
mod cycle;
mod cycles;
mod existence;
mod node;
mod project;
mod refs;
mod report;
mod rules;
mod store;
mod story;
mod validate;
mod walk;
mod will;

pub use cycle::{BasisRefError, Cycle, CycleError, CycleKind, OutcomeRefError, SynthesisRefError};
pub use context::{context, next_moves};
pub use contract::{Branch, CloseContract, FieldContract, ValueChoice};
pub use cycles::{CycleId, Cycles, CyclesError, OpenChildError};
pub use existence::{Existence, ExistenceState, Journey, Revision};
pub use node::{Node, NodeKind, NodeStatus};
pub use project::{ActionError, Closed, ClosedCycle, Opened, Project, ProjectError};
pub use refs::{
    ChainRef, CycleRef, ExistenceRef, JourneyRef, KnowledgeRef, MemoryRef, ParticipantRef,
    RefSyntaxError, RelationRef, SnapshotRef, StateRef, StepRef, WillRef,
};
pub use report::{Report, ReportSyntaxError};
pub use rules::{BUILTIN_SPEC, CycleRules, FieldConstraint, RuleSet, SpecError, StepRules};
pub use story::story;
pub use store::{FORMAT, LEGACY_WALK_PATH, STATE_PATH, StoreError, load, save};
pub use validate::{GrammarError, Subject};
pub use walk::{NextDirectionError, NodeId, RestoreError, StepNode, Walk, WalkError};
pub use will::{ActionContract, ContractError, DONE_WHEN, NEXT_ACTION, OBJECTIVE, Will};
