//! GIL Grammar v0.1 — 읽고, 검증하고, 한 걸음씩 걷는 최소 구현.
//!
//! 이 크레이트가 하는 일은 셋뿐이다.
//!
//! 1. `gil-spec.yaml` 을 읽는다.
//! 2. 그 규칙으로 Node 의 **여는 전이**와 **닫는 조건**을 판정한다.
//! 3. 그 판정 위에서 **한 Cycle 안의 Step 을 메모리에서 걷는다**([`Walk`]) —
//!    Node 마다 이름([`NodeId`])이 붙고, 부모는 **태어날 때 기록**된다.
//!
//! 규칙은 코드에 있지 않다 — 전부 `gil-spec.yaml` 에 있다. 여기 있는 것은 그 파일을
//! 읽는 절차와, 읽은 값을 그대로 적용하는 판정뿐이다.
//!
//! 아직 없는 것(다음 Step 의 몫): git · Artifact · Knowledge 상속 · Lineage ·
//! Chain/Cycle 상태 머신 · Existence · 되돌아가기 · 저장.
//!
//! ```
//! use gil::{Node, NodeKind, Report, RuleSet};
//!
//! let rules = RuleSet::from_path(concat!(
//!     env!("CARGO_MANIFEST_DIR"),
//!     "/spec/gil-spec.yaml"
//! ))
//! .unwrap();
//!
//! // Cycle 의 시작에서는 define 만 열린다.
//! assert!(rules.validate_open(Node::cycle_entry(), NodeKind::Define).is_ok());
//! assert!(rules.validate_open(Node::cycle_entry(), NodeKind::Verify).is_err());
//!
//! // 닫히지 않은 부모 아래로는 아무것도 열 수 없다.
//! assert!(
//!     rules
//!         .validate_open(Node::open(NodeKind::Define), NodeKind::Hypothesis)
//!         .is_err()
//! );
//!
//! // 닫으려면 그 종류가 요구하는 칸이 다 있어야 한다.
//! let report = Report::new().with("problem", "…").with("success_condition", "…");
//! assert!(rules.validate_close(NodeKind::Define, &report).is_ok());
//!
//! // 그 위에서 한 걸음을 걷는다 — 열고, 적고, 닫고, 다음을 연다.
//! let mut walk = gil::Walk::start(rules);
//! walk.open(NodeKind::Define).unwrap();
//! let define = walk.current().unwrap();
//! walk.close(report).unwrap();
//! assert_eq!(walk.current(), Some(define)); // 닫아도 그 자리에 서 있다
//!
//! walk.open(NodeKind::Hypothesis).unwrap();
//! let hypothesis = walk.node(walk.current().unwrap()).unwrap();
//! assert_eq!(hypothesis.parent, Some(define)); // 부모는 태어날 때 적힌다
//! assert_eq!(walk.history().count(), 1);
//! ```

mod node;
mod report;
mod rules;
mod validate;
mod walk;

pub use node::{Node, NodeKind, NodeStatus};
pub use report::Report;
pub use rules::{FieldConstraint, RuleSet, SpecError, StepRules};
pub use validate::GrammarError;
pub use walk::{NodeId, StepNode, Walk, WalkError};
