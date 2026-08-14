//! 시험이 함께 쓰는 것 — **기대값은 저장소의 진짜 명세에서 만든다.**

use gil::{NodeKind, Report, RuleSet};

pub const SPEC_PATH: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/spec/gil-spec.yaml");

pub fn spec() -> RuleSet {
    RuleSet::from_path(SPEC_PATH).expect("spec/gil-spec.yaml 을 읽을 수 있어야 한다")
}

/// close_requires 를 전부 채운, 명세가 받아들이는 Report.
///
/// 값에 제약이 걸린 칸은 **명세가 허락한 값 중 하나**로 채운다(여기서도 값을 지어내지 않는다).
/// 다른 칸에 따라 허용값이 좁아지는 칸은 **좁혀진 뒤에** 다시 고른다.
pub fn full_report(rules: &RuleSet, kind: NodeKind) -> Report {
    let step = rules.rules(kind).expect("선언된 Step Kind 여야 한다");

    // ① 먼저 각 칸을 제 허용값(또는 자리표시자)으로 채운다.
    let mut report: Report = step
        .close_requires
        .iter()
        .map(|field| {
            let value = match step.field_constraints.get(field) {
                Some(constraint) => constraint
                    .allowed_values
                    .first()
                    .cloned()
                    .unwrap_or_else(|| format!("<{field}>")),
                None => format!("<{field}>"),
            };
            (field.clone(), value)
        })
        .collect();

    // ② 다른 칸이 값을 좁히는 칸은, 그 값을 보고 다시 고른다.
    for (field, constraint) in &step.field_constraints {
        if constraint.allowed_values_when.is_empty() {
            continue;
        }
        let (allowed, _) = constraint.allowed_here(|other| report.get(other));
        if let Some(value) = allowed.first() {
            report.insert(field.clone(), value.clone());
        }
    }

    report
}

/// 지금 이 Report 에서 그 칸이 가질 수 있는 값 — 좁혀진 뒤의 것.
pub fn allowed_here(rules: &RuleSet, kind: NodeKind, field: &str, report: &Report) -> Vec<String> {
    let step = rules.rules(kind).expect("선언된 Step Kind 여야 한다");
    let constraint = step
        .field_constraints
        .get(field)
        .expect("값 제약이 걸린 칸이어야 한다");
    let (allowed, _) = constraint.allowed_here(|other| report.get(other));
    allowed.to_vec()
}
