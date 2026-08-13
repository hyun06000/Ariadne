//! 시험이 함께 쓰는 것 — **기대값은 저장소의 진짜 명세에서 만든다.**

use gil::{NodeKind, Report, RuleSet};

pub const SPEC_PATH: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/spec/gil-spec.yaml");

pub fn spec() -> RuleSet {
    RuleSet::from_path(SPEC_PATH).expect("spec/gil-spec.yaml 을 읽을 수 있어야 한다")
}

/// close_requires 를 전부 채운, 명세가 받아들이는 Report.
///
/// 값에 제약이 걸린 칸은 **명세가 허락한 값 중 하나**로 채운다(여기서도 값을 지어내지 않는다).
pub fn full_report(rules: &RuleSet, kind: NodeKind) -> Report {
    let step = rules.rules(kind).expect("선언된 Step Kind 여야 한다");
    step.close_requires
        .iter()
        .map(|field| {
            let value = match step.field_constraints.get(field) {
                Some(constraint) => constraint
                    .allowed_values
                    .first()
                    .expect("값 제약에는 허락된 값이 하나 이상 있어야 한다")
                    .clone(),
                None => format!("<{field}>"),
            };
            (field.clone(), value)
        })
        .collect()
}
