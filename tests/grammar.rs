//! GIL Grammar v0.1 이 실제로 강제되는지 본다.
//!
//! **기대값은 코드에 다시 적지 않는다** — 저장소의 진짜 `spec/gil-spec.yaml` 을 읽어,
//! 거기 적힌 변과 칸으로 기대값을 만든다. 명세가 바뀌면 시험도 함께 움직인다.

use std::collections::BTreeSet;

use gil::{GrammarError, Node, NodeKind, Report, RuleSet};

const SPEC_PATH: &str = concat!(env!("CARGO_MANIFEST_DIR"), "/spec/gil-spec.yaml");

fn spec() -> RuleSet {
    RuleSet::from_path(SPEC_PATH).expect("spec/gil-spec.yaml 을 읽을 수 있어야 한다")
}

/// 명세에 **적혀 있는** 변 전부를 모은다.
///
/// 한 변은 두 자리에 적힌다(부모의 allowed_children, 자식의 allowed_parents).
/// 둘이 어긋나면 읽는 순간 거절되므로(RuleSet 의 대칭 검사), 여기서는 합집합을 쓴다.
fn declared_edges(rules: &RuleSet) -> BTreeSet<(NodeKind, NodeKind)> {
    let mut edges = BTreeSet::new();
    for (kind, step) in rules.step_kinds() {
        for child in &step.allowed_children {
            edges.insert((kind, *child));
        }
        for parent in &step.allowed_parents {
            edges.insert((*parent, kind));
        }
    }
    edges
}

/// close_requires 를 전부 채운, 명세가 받아들이는 Report.
///
/// 값에 제약이 걸린 칸은 **명세가 허락한 값 중 하나**로 채운다(여기서도 값을 지어내지 않는다).
fn full_report(rules: &RuleSet, kind: NodeKind) -> Report {
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

#[test]
fn spec_yaml_loads_and_declares_the_five_step_kinds() {
    let rules = spec();
    let kinds: Vec<NodeKind> = rules.step_kinds().map(|(kind, _)| kind).collect();

    assert_eq!(
        kinds,
        vec![
            NodeKind::Define,
            NodeKind::Hypothesis,
            NodeKind::Verify,
            NodeKind::Analysis,
            NodeKind::Outcome,
        ],
        "v0.1 은 다섯 Step Kind 를 선언한다"
    );

    // 경계 표식은 Step Kind 가 아니다 — 제 규칙을 갖지 않는다.
    assert!(!rules.declares(NodeKind::CycleEntry));
    assert!(!rules.declares(NodeKind::CycleExit));

    // 모든 선언에 close_requires 가 하나 이상 있다(경계 표식을 뺀 다섯).
    for (kind, step) in rules.step_kinds() {
        assert!(
            !step.close_requires.is_empty(),
            "{kind} 에 close_requires 가 없다"
        );
    }
}

#[test]
fn a_spec_that_disagrees_with_itself_is_refused() {
    // 한 변이 두 자리에 적히므로 한쪽만 고치면 조용히 갈린다. 읽을 때 잡는다.
    let asymmetric = "
step_kinds:
  define:
    allowed_parents: [cycle_entry]
    allowed_children: [hypothesis]
    close_requires: [problem]
  hypothesis:
    allowed_parents: []
    allowed_children: [verify]
    close_requires: [hypothesis]
  verify:
    allowed_parents: [hypothesis]
    allowed_children: []
    close_requires: [result]
";
    let err = RuleSet::from_yaml_str(asymmetric).expect_err("어긋난 명세는 거절해야 한다");
    let message = err.to_string();
    assert!(
        message.contains("define") && message.contains("hypothesis"),
        "어느 변이 어긋났는지 말해야 한다: {message}"
    );
}

#[test]
fn a_constraint_on_a_field_that_is_never_required_is_refused() {
    // 조용히 안 도는 규칙은 없는 규칙보다 나쁘다 — 걸어 둔 사람은 걸렸다고 믿는다.
    let dangling = "
step_kinds:
  outcome:
    allowed_parents: [analysis]
    allowed_children: [cycle_exit]
    close_requires: [verdict]
    field_constraints:
      lesson:
        allowed_values: [a, b]
";
    let err = RuleSet::from_yaml_str(dangling).expect_err("허공에 건 제약은 거절해야 한다");
    let message = err.to_string();
    assert!(
        message.contains("lesson") && message.contains("close_requires"),
        "어느 칸이 허공인지 말해야 한다: {message}"
    );
}

#[test]
fn every_transition_the_spec_declares_is_accepted() {
    let rules = spec();
    for (parent, child) in declared_edges(&rules) {
        rules
            .validate_open(Node::closed(parent), child)
            .unwrap_or_else(|err| panic!("명세가 허락한 {parent} → {child} 가 거절됐다: {err}"));
    }
}

#[test]
fn every_transition_the_spec_does_not_declare_is_refused() {
    let rules = spec();
    let declared = declared_edges(&rules);

    for parent in NodeKind::ALL {
        for child in NodeKind::ALL {
            let result = rules.validate_open(Node::closed(parent), child);
            if declared.contains(&(parent, child)) {
                assert!(result.is_ok(), "{parent} → {child} 는 허락돼야 한다");
            } else {
                assert!(
                    matches!(result, Err(GrammarError::TransitionNotAllowed { .. })),
                    "{parent} → {child} 는 명세에 없는데 통과했다"
                );
            }
        }
    }
}

#[test]
fn define_cannot_skip_straight_to_verify() {
    let rules = spec();
    let err = rules
        .validate_open(Node::closed(NodeKind::Define), NodeKind::Verify)
        .expect_err("define → verify 는 허락되지 않는다");

    match &err {
        GrammarError::TransitionNotAllowed {
            parent,
            child,
            allowed_children,
        } => {
            assert_eq!(*parent, NodeKind::Define);
            assert_eq!(*child, NodeKind::Verify);
            assert_eq!(allowed_children, &vec![NodeKind::Hypothesis]);
        }
        other => panic!("거절 이유가 전이 위반이어야 한다: {other:?}"),
    }
    // 거절이 막다른 길이 아니라 갈 곳을 말한다.
    assert!(err.to_string().contains("hypothesis"), "{err}");
}

#[test]
fn an_open_parent_blocks_every_child_the_spec_allows() {
    let rules = spec();
    for (parent, step) in rules.step_kinds() {
        for child in &step.allowed_children {
            let result = rules.validate_open(Node::open(parent), *child);
            assert!(
                matches!(result, Err(GrammarError::ParentNotClosed { .. })),
                "{parent} 가 열려 있는데 {child} 가 열렸다"
            );
        }
    }
}

#[test]
fn a_closed_parent_allows_the_children_the_spec_names() {
    let rules = spec();
    for (parent, step) in rules.step_kinds() {
        for child in &step.allowed_children {
            assert!(
                rules.validate_open(Node::closed(parent), *child).is_ok(),
                "닫힌 {parent} 아래 {child} 를 열 수 있어야 한다"
            );
        }
    }
}

#[test]
fn the_cycle_boundary_opens_the_first_step_and_takes_the_last() {
    let rules = spec();
    // 시작: 경계 표식은 여닫는 대상이 아니므로 상태 검사를 받지 않는다.
    assert!(
        rules
            .validate_open(Node::cycle_entry(), NodeKind::Define)
            .is_ok()
    );
    // 끝: 닫힌 outcome 뒤에만 온다.
    assert!(
        rules
            .validate_open(Node::closed(NodeKind::Outcome), NodeKind::CycleExit)
            .is_ok()
    );
    assert!(
        rules
            .validate_open(Node::open(NodeKind::Outcome), NodeKind::CycleExit)
            .is_err()
    );
}

#[test]
fn a_step_closes_when_every_required_field_is_present() {
    let rules = spec();
    for (kind, _) in rules.step_kinds() {
        let report = full_report(&rules, kind);
        rules
            .validate_close(kind, &report)
            .unwrap_or_else(|err| panic!("{kind} 가 다 채운 Report 로 닫히지 않았다: {err}"));
    }
}

#[test]
fn a_step_will_not_close_when_a_required_field_is_missing() {
    let rules = spec();
    for (kind, step) in rules.step_kinds() {
        for dropped in &step.close_requires {
            let mut report = full_report(&rules, kind);
            report.remove(dropped);

            let err = rules
                .validate_close(kind, &report)
                .expect_err(&format!("{kind} 에서 {dropped} 가 빠졌는데 닫혔다"));

            match &err {
                GrammarError::MissingReportFields { kind: k, missing } => {
                    assert_eq!(*k, kind);
                    assert_eq!(missing, &vec![dropped.clone()], "빠진 칸만 정확히 세야 한다");
                }
                other => panic!("거절 이유가 칸 누락이어야 한다: {other:?}"),
            }
            // 무엇이 빠졌는지 사람이 읽을 수 있어야 한다.
            assert!(err.to_string().contains(dropped), "{err}");
        }
    }
}

#[test]
fn hypothesis_without_a_guardrail_is_named_in_the_error() {
    let rules = spec();
    let report = Report::new()
        .with("hypothesis", "…")
        .with("rationale", "…");

    let err = rules
        .validate_close(NodeKind::Hypothesis, &report)
        .expect_err("guardrail 없이는 닫히지 않는다");

    assert_eq!(
        err,
        GrammarError::MissingReportFields {
            kind: NodeKind::Hypothesis,
            missing: vec!["guardrail".to_string()],
        }
    );
    assert!(err.to_string().contains("guardrail"), "{err}");
}

#[test]
fn an_empty_report_names_every_field_that_is_missing() {
    let rules = spec();
    for (kind, step) in rules.step_kinds() {
        let err = rules
            .validate_close(kind, &Report::new())
            .expect_err(&format!("{kind} 가 빈 Report 로 닫혔다"));

        match err {
            GrammarError::MissingReportFields { missing, .. } => {
                assert_eq!(
                    missing, step.close_requires,
                    "{kind}: 빠진 칸 전부를 말해야 한다"
                );
            }
            other => panic!("거절 이유가 칸 누락이어야 한다: {other:?}"),
        }
    }
}

#[test]
fn every_value_the_spec_allows_is_accepted() {
    let rules = spec();
    let mut checked = 0;
    for (kind, step) in rules.step_kinds() {
        for (field, constraint) in &step.field_constraints {
            for value in &constraint.allowed_values {
                let mut report = full_report(&rules, kind);
                report.insert(field.clone(), value.clone());
                rules.validate_close(kind, &report).unwrap_or_else(|err| {
                    panic!("{kind}.{field} = {value:?} 는 명세가 허락한 값인데 거절됐다: {err}")
                });
                checked += 1;
            }
        }
    }
    assert!(checked > 0, "명세에 값 제약이 하나도 없다 — 이 시험이 눈멀었다");
}

#[test]
fn a_value_the_spec_does_not_allow_is_refused() {
    let rules = spec();
    let outsider = "__명세에_없는_값__";
    let mut checked = 0;

    for (kind, step) in rules.step_kinds() {
        for (field, constraint) in &step.field_constraints {
            assert!(!constraint.allowed_values.iter().any(|v| v == outsider));

            let mut report = full_report(&rules, kind);
            report.insert(field.clone(), outsider);

            let err = rules
                .validate_close(kind, &report)
                .expect_err(&format!("{kind}.{field} 가 아무 값이나 받았다"));

            assert_eq!(
                err,
                GrammarError::FieldValueNotAllowed {
                    kind,
                    field: field.clone(),
                    value: outsider.to_string(),
                    allowed: constraint.allowed_values.clone(),
                }
            );
            // 거절이 갈 곳을 말한다.
            for allowed in &constraint.allowed_values {
                assert!(err.to_string().contains(allowed), "{err}");
            }
            checked += 1;
        }
    }
    assert!(checked > 0, "명세에 값 제약이 하나도 없다 — 이 시험이 눈멀었다");
}

#[test]
fn allowed_values_are_case_sensitive() {
    // 입력 편의성보다 문법의 명확성과 결정성을 앞에 둔다 — 값은 정본 하나뿐이다.
    let rules = spec();
    let mut checked = 0;

    for (kind, step) in rules.step_kinds() {
        for (field, constraint) in &step.field_constraints {
            for value in &constraint.allowed_values {
                let shouted = value.to_uppercase();
                if shouted == *value {
                    continue; // 대소문자가 없는 값이면 잴 것이 없다.
                }
                let report = full_report(&rules, kind).with(field.clone(), shouted.clone());
                assert!(
                    rules.validate_close(kind, &report).is_err(),
                    "{kind}.{field} 가 {shouted:?} 를 받았다 — 값은 대소문자를 구분한다"
                );
                checked += 1;
            }
        }
    }
    assert!(checked > 0, "대소문자를 잴 값이 하나도 없었다 — 이 시험이 눈멀었다");
}

#[test]
fn pending_is_not_a_verdict_it_is_an_outcome_still_open() {
    let rules = spec();

    // pending 은 verdict 의 값이 아니다.
    let report = full_report(&rules, NodeKind::Outcome).with("verdict", "pending");
    let err = rules
        .validate_close(NodeKind::Outcome, &report)
        .expect_err("pending 은 verdict 로 쓸 수 없다");
    assert!(matches!(err, GrammarError::FieldValueNotAllowed { .. }), "{err:?}");

    // 판정을 기다리는 자리는 **아직 닫히지 않은 Outcome** 이고,
    // 그 상태에서는 다음으로 넘어갈 수 없다.
    assert!(
        rules
            .validate_open(Node::open(NodeKind::Outcome), NodeKind::CycleExit)
            .is_err()
    );
}

#[test]
fn a_boundary_marker_is_not_a_step_and_cannot_be_closed() {
    let rules = spec();
    for boundary in [NodeKind::CycleEntry, NodeKind::CycleExit] {
        let err = rules
            .validate_close(boundary, &Report::new())
            .expect_err("경계 표식은 닫는 대상이 아니다");
        assert_eq!(err, GrammarError::UnknownStepKind(boundary));
    }
}
