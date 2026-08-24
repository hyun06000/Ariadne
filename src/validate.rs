//! Grammar 검증 — 두 가지만 판정한다.
//!
//! 1. **열 수 있는가**: 부모의 종류·상태를 보고 이 자식을 열 수 있는지.
//! 2. **닫을 수 있는가**: 그 종류가 요구하는 Report 칸이 다 있는지.
//!
//! 판정의 근거는 전부 `gil-spec.yaml` 이다. 여기 있는 것은 그 값을 읽는 절차뿐이다.
//!
//! 닫는 판정은 **계층을 가리지 않는다.** Step 을 닫든 Cycle 을 닫든 묻는 것이 같아서
//! 한 함수([`check_report`])가 답한다 — 무엇을 닫으려는지는 [`Subject`] 가 말한다.

use std::collections::BTreeMap;
use std::fmt;

use crate::cycle::CycleKind;
use crate::node::{Node, NodeKind};
use crate::report::Report;
use crate::rules::{FieldConstraint, RuleSet};

/// 무엇을 닫으려다 거절됐는가.
///
/// 거절의 이유는 계층마다 같지만, **누가 거절당했는지**는 달라야 한다 —
/// 아니면 사람이 어느 층의 Report 를 고쳐야 하는지 모른다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Subject {
    Step(NodeKind),
    Cycle(CycleKind),
}

impl fmt::Display for Subject {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Subject::Step(kind) => write!(f, "{kind}"),
            Subject::Cycle(kind) => write!(f, "{kind} Cycle"),
        }
    }
}

impl RuleSet {
    /// 그 Cycle 안에서, 부모 아래에 이 종류의 자식을 열 수 있는가.
    ///
    /// **Cycle Kind 를 함께 묻는다.** Interview 에서 `define` 을, Experiment 에서 `question` 을
    /// 열 수 없다는 것은 부모·자식 관계가 아니라 **어느 Cycle 의 문법인가**가 정한다.
    pub fn validate_open(
        &self,
        cycle: CycleKind,
        parent: Node,
        child: NodeKind,
    ) -> Result<(), GrammarError> {
        // 닫히지 않은 Node 를 기반으로 다음 Node 를 열 수 없다.
        // 경계 표식은 여닫는 대상이 아니라 자리를 가리키는 이름이라 이 검사를 받지 않는다.
        if !parent.kind.is_boundary() && !parent.is_closed() {
            return Err(GrammarError::ParentNotClosed {
                parent: parent.kind,
                child,
            });
        }

        let parent_says = self
            .rules(cycle, parent.kind)
            .map(|rules| rules.allowed_children.contains(&child));
        let child_says = self
            .rules(cycle, child)
            .map(|rules| rules.allowed_parents.contains(&parent.kind));

        // 선언된 쪽은 전부 허락해야 하고, 적어도 한쪽은 이 변을 실제로 적어 뒀어야 한다.
        // 양쪽 다 선언이 없으면 이 변을 허락한 자리가 명세에 없다는 뜻이다.
        let allowed = match (parent_says, child_says) {
            (None, None) => false,
            (parent_says, child_says) => {
                parent_says.unwrap_or(true) && child_says.unwrap_or(true)
            }
        };

        if allowed {
            Ok(())
        } else {
            Err(GrammarError::TransitionNotAllowed {
                parent: parent.kind,
                child,
                allowed_children: self.allowed_children_of(cycle, parent.kind),
            })
        }
    }

    /// 그 Cycle 안에서 이 종류의 Step 을 이 Report 로 닫을 수 있는가.
    pub fn validate_close(
        &self,
        cycle: CycleKind,
        kind: NodeKind,
        report: &Report,
    ) -> Result<(), GrammarError> {
        let Some(rules) = self.rules(cycle, kind) else {
            return Err(GrammarError::UnknownStepKind(kind));
        };
        check_report(
            Subject::Step(kind),
            &rules.close_requires,
            &rules.field_constraints,
            report,
        )
    }

    /// 이 종류의 Cycle 을 이 Cycle Report 로 닫을 수 있는가.
    pub fn validate_cycle_close(
        &self,
        kind: CycleKind,
        report: &Report,
    ) -> Result<(), GrammarError> {
        let Some(rules) = self.cycle_rules(kind) else {
            return Err(GrammarError::UnknownCycleKind(kind));
        };
        check_report(
            Subject::Cycle(kind),
            &rules.close_requires,
            &rules.field_constraints,
            report,
        )
    }
}

/// 이 Report 로 닫을 수 있는가 — 계층을 가리지 않는 판정.
fn check_report(
    subject: Subject,
    close_requires: &[String],
    field_constraints: &BTreeMap<String, FieldConstraint>,
    report: &Report,
) -> Result<(), GrammarError> {
    let missing: Vec<String> = close_requires
        .iter()
        .filter(|field| !report.has(field))
        .cloned()
        .collect();

    if !missing.is_empty() {
        return Err(GrammarError::MissingReportFields { subject, missing });
    }

    // 칸이 있다는 것과 그 칸의 값이 명세가 허락한 것이라는 것은 다르다.
    for (field, constraint) in field_constraints {
        let Some(value) = report.get(field) else {
            continue; // close_requires 에 있으면 위에서 이미 걸렀다.
        };

        if constraint.non_empty && value.trim().is_empty() {
            return Err(GrammarError::EmptyReportField {
                subject,
                field: field.clone(),
            });
        }

        // 명세가 정의했지만 아직 짓지 않은 값이라면 **왜 아직인지**를 말한다.
        // 그냥 "쓸 수 없다" 고만 하면 명세를 읽은 사람은 제 눈을 의심하게 된다.
        if let Some(why) = constraint.not_yet.get(value) {
            let (allowed, _) = constraint.allowed_here(|other| report.get(other));
            return Err(GrammarError::FieldValueNotYetBuilt {
                subject,
                field: field.clone(),
                value: value.to_string(),
                why: why.clone(),
                allowed: allowed.to_vec(),
            });
        }

        let (allowed, narrowed_by) = constraint.allowed_here(|other| report.get(other));
        if allowed.is_empty() {
            continue; // 값을 열거하지 않는 칸이다.
        }
        if !allowed.iter().any(|candidate| candidate == value) {
            return Err(GrammarError::FieldValueNotAllowed {
                subject,
                field: field.clone(),
                value: value.to_string(),
                allowed: allowed.to_vec(),
                narrowed_by: narrowed_by.map(|(f, v)| (f.to_string(), v.to_string())),
            });
        }
    }

    Ok(())
}

/// Grammar 가 거절한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GrammarError {
    /// 명세의 `step_kinds` 에 없는 종류다(경계 표식은 Step 이 아니다).
    UnknownStepKind(NodeKind),
    /// 명세의 `cycle_kinds` 에 없는 종류다.
    UnknownCycleKind(CycleKind),
    /// 부모가 아직 닫히지 않았다.
    ParentNotClosed { parent: NodeKind, child: NodeKind },
    /// 명세가 허락하지 않은 전이다.
    TransitionNotAllowed {
        parent: NodeKind,
        child: NodeKind,
        allowed_children: Vec<NodeKind>,
    },
    /// 닫는 데 필요한 Report 칸이 빠졌다.
    MissingReportFields {
        subject: Subject,
        missing: Vec<String>,
    },
    /// 비어 있으면 안 되는 칸이 비었다.
    EmptyReportField { subject: Subject, field: String },
    /// 명세가 정의했지만 아직 짓지 않은 값이다.
    FieldValueNotYetBuilt {
        subject: Subject,
        field: String,
        value: String,
        why: String,
        allowed: Vec<String>,
    },
    /// 칸은 있는데 그 값이 명세가 허락한 것이 아니다.
    FieldValueNotAllowed {
        subject: Subject,
        field: String,
        value: String,
        allowed: Vec<String>,
        /// 허용값이 다른 칸 때문에 좁혀졌다면 그 (칸, 값).
        narrowed_by: Option<(String, String)>,
    },
}

impl fmt::Display for GrammarError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            GrammarError::UnknownStepKind(kind) => {
                write!(f, "{kind} 은(는) 명세의 step_kinds 에 없다 — Step 이 아니다")
            }
            GrammarError::UnknownCycleKind(kind) => {
                write!(f, "{kind} 은(는) 명세의 cycle_kinds 에 없다 — 닫는 규칙이 없다")
            }
            GrammarError::ParentNotClosed { parent, child } => write!(
                f,
                "{parent} 이(가) 아직 열려 있어 {child} 을(를) 열 수 없다 \
                 — 먼저 {parent} 을(를) 닫아라",
            ),
            GrammarError::TransitionNotAllowed {
                parent,
                child,
                allowed_children,
            } => {
                write!(f, "{parent} 뒤에 {child} 을(를) 열 수 없다 — ")?;
                if allowed_children.is_empty() {
                    write!(f, "{parent} 뒤에 열 수 있는 것이 명세에 없다")
                } else {
                    let names: Vec<&str> =
                        allowed_children.iter().map(|kind| kind.as_str()).collect();
                    write!(f, "여기서 열 수 있는 것: {}", names.join(", "))
                }
            }
            GrammarError::MissingReportFields { subject, missing } => write!(
                f,
                "{subject} 을(를) 닫으려면 Report 에 다음 칸이 있어야 한다 (빠진 것: {})",
                missing.join(", ")
            ),
            GrammarError::EmptyReportField { subject, field } => write!(
                f,
                "{subject} 의 {field} 는 비워 둘 수 없다 — 나중에 이유를 되짚을 수 있어야 한다"
            ),
            GrammarError::FieldValueNotYetBuilt {
                subject,
                field,
                value,
                why,
                allowed,
            } => write!(
                f,
                "{subject} 의 {field} 에 {value:?} 는 **아직** 쓸 수 없다 — {why}.\n\
                 명세에는 있지만 지금 밟을 수 있는 수가 아니다. 지금 쓸 수 있는 값: {}",
                allowed.join(", ")
            ),
            GrammarError::FieldValueNotAllowed {
                subject,
                field,
                value,
                allowed,
                narrowed_by,
            } => {
                write!(
                    f,
                    "{subject} 의 {field} 에 {value:?} 는 쓸 수 없다 — 여기 올 수 있는 값: {}",
                    allowed.join(", ")
                )?;
                match narrowed_by {
                    Some((deciding_field, deciding_value)) => {
                        write!(f, " ({deciding_field} 가 {deciding_value:?} 이기 때문이다)")
                    }
                    None => Ok(()),
                }
            }
        }
    }
}

impl std::error::Error for GrammarError {}
