//! 시험이 함께 쓰는 것 — **기대값은 저장소의 진짜 명세에서 만든다.**
//!
//! 여기 있는 것은 여러 시험 파일이 나눠 쓰는 연장이다. 한 파일이 안 쓰는 연장도 있어서
//! 안 쓰임 경고를 끈다 — 없는 연장으로 오해하지 않도록.
#![allow(dead_code)]

use std::path::PathBuf;

use gil::{NodeId, NodeKind, Report, RuleSet, Walk};

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

/// 시험이 파일을 눕히는 빈 자리. 이름이 겹치지 않게 시험마다 다른 `label` 을 준다.
///
/// 들어가기 전에 지운다 — 앞 판이 남긴 것이 이번 판의 답이 되지 않도록.
pub fn scratch(label: &str) -> PathBuf {
    let dir = std::env::temp_dir().join(format!("gil-test-{label}"));
    let _ = std::fs::remove_dir_all(&dir);
    std::fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만들 수 있어야 한다");
    dir
}

/// Report 가 다음 방향을 적는 칸의 이름 — `gil-spec.yaml` 이 부르는 그대로.
pub const ACTION: &str = "next_direction.action";
pub const TARGET: &str = "next_direction.target_node_id";
pub const REASON: &str = "next_direction.reason";

/// 이미 열려 있는 Node 를 명세가 받아들이는 Report 로 닫는다.
pub fn step_close(walk: &mut Walk, kind: NodeKind) {
    let report = full_report(walk.rules(), kind);
    walk.close(report)
        .unwrap_or_else(|err| panic!("{kind} 를 닫지 못했다: {err}"));
}

/// 한 Step 을 온전히 걷는다 — 열고, 명세가 받아들이는 Report 로 닫는다.
pub fn step(walk: &mut Walk, kind: NodeKind) -> NodeId {
    walk.open(kind)
        .unwrap_or_else(|err| panic!("{kind} 를 열지 못했다: {err}"));
    let id = walk.current().expect("연 뒤에는 서 있는 자리가 있다");
    step_close(walk, kind);
    id
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
