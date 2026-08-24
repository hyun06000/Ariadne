//! GIL Grammar v0.1 이 실제로 강제되는지 본다.
//!
//! **기대값은 코드에 다시 적지 않는다** — 저장소의 진짜 `spec/gil-spec.yaml` 을 읽어,
//! 거기 적힌 변과 칸으로 기대값을 만든다. 명세가 바뀌면 시험도 함께 움직인다.

use std::collections::BTreeSet;

use gil::{CycleKind, GrammarError, Node, NodeKind, Report, RuleSet, Subject};

mod common;
use common::{allowed_here, full_report, spec};

/// 명세에 **적혀 있는** 변 전부를 모은다.
///
/// 한 변은 두 자리에 적힌다(부모의 allowed_children, 자식의 allowed_parents).
/// 둘이 어긋나면 읽는 순간 거절되므로(RuleSet 의 대칭 검사), 여기서는 합집합을 쓴다.
fn declared_edges(rules: &RuleSet) -> BTreeSet<(NodeKind, NodeKind)> {
    let mut edges = BTreeSet::new();
    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        for child in &step.allowed_children {
            edges.insert((kind, *child));
        }
        for parent in &step.allowed_parents {
            edges.insert((*parent, kind));
        }
    }
    edges
}

#[test]
fn spec_yaml_loads_and_declares_the_five_step_kinds() {
    let rules = spec();
    let kinds: Vec<NodeKind> = rules.step_kinds(CycleKind::Experiment).map(|(kind, _)| kind).collect();

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
    assert!(!rules.declares(CycleKind::Experiment, NodeKind::CycleEntry));
    assert!(!rules.declares(CycleKind::Experiment, NodeKind::CycleExit));

    // 모든 선언에 close_requires 가 하나 이상 있다(경계 표식을 뺀 다섯).
    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        assert!(
            !step.close_requires.is_empty(),
            "{kind} 에 close_requires 가 없다"
        );
    }
}

/// 손으로 쓴 Step 조각을 **아는 Cycle Kind 마다** 얹어 온전한 명세를 만든다.
///
/// 아래 시험들이 재는 것은 Step 쪽 규칙이다. 그런데 Step 문법은 이제 Cycle Kind **안에**
/// 살고, 명세는 아는 Cycle Kind 마다 닫는 규칙과 Step 문법이 다 있어야 완결된다. 그래서
/// 같은 조각을 모든 Kind 에 얹는다 — 어느 Kind 에서 잡히든 규칙은 같기 때문이다.
fn with_cycle_rules(step_kinds: &str) -> String {
    // 선언된 Step Kind 마다 **무엇을 하는 자리인지** 한 줄이 필요하다. 시험이 재려는 것은
    // 그것이 아니므로 여기서 채워 준다 — 없으면 모든 fixture 가 같은 이유로 먼저 걸린다.
    let indented: String = step_kinds
        .lines()
        .flat_map(|line| match (line.trim().is_empty(), is_step_key(line)) {
            (true, _) => vec![String::from("\n")],
            (false, true) => vec![
                format!("      {line}\n"),
                format!("        description: {} 를 하는 자리\n", line.trim().trim_end_matches(':')),
            ],
            (false, false) => vec![format!("      {line}\n")],
        })
        .collect();
    let mut yaml = String::from("cycle_kinds:\n");
    for kind in CycleKind::ALL {
        yaml.push_str(&format!(
            "  {kind}:\n    description: {kind} 를 하는 자리\n    \
             close_requires: [verdict]\n    step_kinds:\n{indented}"
        ));
    }
    yaml
}

/// 들여쓰기 없이 `이름:` 하나만 있는 줄 — Step Kind 의 머리다.
fn is_step_key(line: &str) -> bool {
    !line.starts_with(char::is_whitespace) && line.trim_end().ends_with(':')
}

#[test]
fn a_spec_that_disagrees_with_itself_is_refused() {
    // 한 변이 두 자리에 적히므로 한쪽만 고치면 조용히 갈린다. 읽을 때 잡는다.
    let asymmetric = "define:
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
    let err = RuleSet::from_yaml_str(&with_cycle_rules(asymmetric)).expect_err("어긋난 명세는 거절해야 한다");
    let message = err.to_string();
    assert!(
        message.contains("define") && message.contains("hypothesis"),
        "어느 변이 어긋났는지 말해야 한다: {message}"
    );
}

#[test]
fn a_spec_that_cannot_close_a_cycle_it_declares_is_refused() {
    // 아는 Cycle Kind 마다 닫는 규칙이 있어야 한다. 없으면 그 Cycle 은 **닫을 방법 없이**
    // 열리고, 사람은 다 걷고 나서야 알게 된다.
    //
    // 한 Kind 씩 빼 보며 **빠진 그것을 이름으로 말하는지** 잰다.
    for missing in CycleKind::ALL {
        let mut yaml = String::from("cycle_kinds:\n");
        for kind in CycleKind::ALL.into_iter().filter(|kind| *kind != missing) {
            yaml.push_str(&format!(
                "  {kind}:\n    description: {kind} 를 하는 자리\n    \
                 close_requires: [verdict]\n    step_kinds:\n      \
                 define:\n        description: 문제를 정하는 자리\n        \
                 allowed_parents: [cycle_entry]\n        \
                 allowed_children: []\n        close_requires: [problem]\n"
            ));
        }
        let err = RuleSet::from_yaml_str(&yaml)
            .expect_err("닫을 규칙이 없는 Cycle Kind 가 있는 명세가 통과했다");
        let message = err.to_string();
        assert!(
            message.contains(missing.as_str()),
            "어느 Cycle Kind 가 비었는지 말해야 한다: {message}"
        );
        assert!(message.contains("cycle_kinds"), "{message}");
    }
}

#[test]
fn a_constraint_on_a_field_that_is_never_required_is_refused() {
    // 조용히 안 도는 규칙은 없는 규칙보다 나쁘다 — 걸어 둔 사람은 걸렸다고 믿는다.
    let dangling = "outcome:
  allowed_parents: [analysis]
  allowed_children: [cycle_exit]
  close_requires: [verdict]
  field_constraints:
    lesson:
      allowed_values: [a, b]
";
    let err = RuleSet::from_yaml_str(&with_cycle_rules(dangling)).expect_err("허공에 건 제약은 거절해야 한다");
    let message = err.to_string();
    assert!(
        message.contains("lesson") && message.contains("close_requires"),
        "어느 칸이 허공인지 말해야 한다: {message}"
    );
}

#[test]
fn a_constraint_that_constrains_nothing_is_refused() {
    let empty = "define:
  allowed_parents: [cycle_entry]
  allowed_children: []
  close_requires: [problem]
  field_constraints:
    problem: {}
";
    let err = RuleSet::from_yaml_str(&with_cycle_rules(empty)).expect_err("아무것도 안 거는 제약은 거절해야 한다");
    assert!(err.to_string().contains("problem"), "{err}");
}

#[test]
fn a_narrowing_that_points_at_nothing_is_refused() {
    // 가르는 칸이 Report 에 없으면 그 표는 한 번도 안 쓰인다.
    let dangling = "define:
  allowed_parents: [cycle_entry]
  allowed_children: []
  close_requires: [problem]
  field_constraints:
    problem:
      allowed_values: [a, b]
      allowed_values_when:
        verdict:
          success: [a]
";
    let err = RuleSet::from_yaml_str(&with_cycle_rules(dangling)).expect_err("허공을 가르는 표는 거절해야 한다");
    assert!(err.to_string().contains("verdict"), "{err}");
}

#[test]
fn a_narrowing_that_widens_the_allowed_values_is_refused() {
    // 좁히는 표가 본래 허용값에 없는 것을 허락하면 규칙 둘이 서로를 부정한다.
    let widening = "define:
  allowed_parents: [cycle_entry]
  allowed_children: []
  close_requires: [problem, success_condition]
  field_constraints:
    success_condition:
      allowed_values: [yes, no]
    problem:
      allowed_values: [a, b]
      allowed_values_when:
        success_condition:
          yes: [c]
";
    let err = RuleSet::from_yaml_str(&with_cycle_rules(widening)).expect_err("넓히는 표는 거절해야 한다");
    assert!(err.to_string().contains("allowed_values"), "{err}");
}

#[test]
fn every_transition_the_spec_declares_is_accepted() {
    let rules = spec();
    for (parent, child) in declared_edges(&rules) {
        rules
            .validate_open(CycleKind::Experiment, Node::closed(parent), child)
            .unwrap_or_else(|err| panic!("명세가 허락한 {parent} → {child} 가 거절됐다: {err}"));
    }
}

#[test]
fn every_transition_the_spec_does_not_declare_is_refused() {
    let rules = spec();
    let declared = declared_edges(&rules);

    for parent in NodeKind::ALL {
        for child in NodeKind::ALL {
            let result = rules.validate_open(CycleKind::Experiment, Node::closed(parent), child);
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
        .validate_open(CycleKind::Experiment, Node::closed(NodeKind::Define), NodeKind::Verify)
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
    for (parent, step) in rules.step_kinds(CycleKind::Experiment) {
        for child in &step.allowed_children {
            let result = rules.validate_open(CycleKind::Experiment, Node::open(parent), *child);
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
    for (parent, step) in rules.step_kinds(CycleKind::Experiment) {
        for child in &step.allowed_children {
            assert!(
                rules.validate_open(CycleKind::Experiment, Node::closed(parent), *child).is_ok(),
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
            .validate_open(CycleKind::Experiment, Node::cycle_entry(), NodeKind::Define)
            .is_ok()
    );
    // 끝: 닫힌 outcome 뒤에만 온다.
    assert!(
        rules
            .validate_open(CycleKind::Experiment, Node::closed(NodeKind::Outcome), NodeKind::CycleExit)
            .is_ok()
    );
    assert!(
        rules
            .validate_open(CycleKind::Experiment, Node::open(NodeKind::Outcome), NodeKind::CycleExit)
            .is_err()
    );
}

#[test]
fn a_step_closes_when_every_required_field_is_present() {
    let rules = spec();
    for (kind, _) in rules.step_kinds(CycleKind::Experiment) {
        let report = full_report(&rules, CycleKind::Experiment, kind);
        rules
            .validate_close(CycleKind::Experiment, kind, &report)
            .unwrap_or_else(|err| panic!("{kind} 가 다 채운 Report 로 닫히지 않았다: {err}"));
    }
}

#[test]
fn a_step_will_not_close_when_a_required_field_is_missing() {
    let rules = spec();
    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        for dropped in &step.close_requires {
            let mut report = full_report(&rules, CycleKind::Experiment, kind);
            report.remove(dropped);

            let err = rules
                .validate_close(CycleKind::Experiment, kind, &report)
                .expect_err(&format!("{kind} 에서 {dropped} 가 빠졌는데 닫혔다"));

            match &err {
                GrammarError::MissingReportFields { subject, missing } => {
                    assert_eq!(*subject, Subject::Step(kind));
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
        .validate_close(CycleKind::Experiment, NodeKind::Hypothesis, &report)
        .expect_err("guardrail 없이는 닫히지 않는다");

    assert_eq!(
        err,
        GrammarError::MissingReportFields {
            subject: Subject::Step(NodeKind::Hypothesis),
            missing: vec!["guardrail".to_string()],
        }
    );
    assert!(err.to_string().contains("guardrail"), "{err}");
}

#[test]
fn an_empty_report_names_every_field_that_is_missing() {
    let rules = spec();
    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        let err = rules
            .validate_close(CycleKind::Experiment, kind, &Report::new())
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
    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        for field in step.field_constraints.keys() {
            let base = full_report(&rules, CycleKind::Experiment, kind);
            // 다른 칸 때문에 좁혀진 뒤의 허용값을 쓴다.
            for value in allowed_here(&rules, CycleKind::Experiment, kind, field, &base) {
                let report = base.clone().with(field.clone(), value.clone());
                rules.validate_close(CycleKind::Experiment, kind, &report).unwrap_or_else(|err| {
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

    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        for field in step.field_constraints.keys() {
            let base = full_report(&rules, CycleKind::Experiment, kind);
            let allowed = allowed_here(&rules, CycleKind::Experiment, kind, field, &base);
            if allowed.is_empty() {
                continue; // 값을 열거하지 않는 칸이다(예: non_empty 만 거는 칸).
            }
            assert!(!allowed.iter().any(|v| v == outsider));

            let report = base.with(field.clone(), outsider);
            let err = rules
                .validate_close(CycleKind::Experiment, kind, &report)
                .expect_err(&format!("{kind}.{field} 가 아무 값이나 받았다"));

            match &err {
                GrammarError::FieldValueNotAllowed {
                    subject,
                    field: f,
                    value,
                    allowed: reported,
                    ..
                } => {
                    assert_eq!(*subject, Subject::Step(kind));
                    assert_eq!(f, field);
                    assert_eq!(value, outsider);
                    assert_eq!(reported, &allowed, "거절이 지금 올 수 있는 값을 말해야 한다");
                }
                other => panic!("거절 이유가 값 위반이어야 한다: {other:?}"),
            }
            for value in &allowed {
                assert!(err.to_string().contains(value), "{err}");
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

    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        for field in step.field_constraints.keys() {
            let base = full_report(&rules, CycleKind::Experiment, kind);
            for value in allowed_here(&rules, CycleKind::Experiment, kind, field, &base) {
                let shouted = value.to_uppercase();
                if shouted == value {
                    continue; // 대소문자가 없는 값이면 잴 것이 없다.
                }
                let report = base.clone().with(field.clone(), shouted.clone());
                assert!(
                    rules.validate_close(CycleKind::Experiment, kind, &report).is_err(),
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
    let report = full_report(&rules, CycleKind::Experiment, NodeKind::Outcome).with("verdict", "pending");
    let err = rules
        .validate_close(CycleKind::Experiment, NodeKind::Outcome, &report)
        .expect_err("pending 은 verdict 로 쓸 수 없다");
    assert!(matches!(err, GrammarError::FieldValueNotAllowed { .. }), "{err:?}");

    // 판정을 기다리는 자리는 **아직 닫히지 않은 Outcome** 이고,
    // 그 상태에서는 다음으로 넘어갈 수 없다.
    assert!(
        rules
            .validate_open(CycleKind::Experiment, Node::open(NodeKind::Outcome), NodeKind::CycleExit)
            .is_err()
    );
}

#[test]
fn a_field_that_must_not_be_empty_refuses_blank_values() {
    let rules = spec();
    let mut checked = 0;

    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        for (field, constraint) in &step.field_constraints {
            if !constraint.non_empty {
                continue;
            }
            for blank in ["", "   ", "\n"] {
                let report = full_report(&rules, CycleKind::Experiment, kind).with(field.clone(), blank);
                let err = rules
                    .validate_close(CycleKind::Experiment, kind, &report)
                    .expect_err(&format!("{kind}.{field} 가 빈 값으로 닫혔다"));
                assert_eq!(
                    err,
                    GrammarError::EmptyReportField {
                        subject: Subject::Step(kind),
                        field: field.clone()
                    }
                );
                assert!(err.to_string().contains(field), "{err}");
            }
            checked += 1;
        }
    }
    assert!(checked > 0, "non_empty 를 건 칸이 없다 — 이 시험이 눈멀었다");
}

#[test]
fn one_field_can_narrow_what_another_field_may_hold() {
    // 명세가 그렇게 적어 둔 쌍을 전부 훑는다 — 이름을 코드에 적지 않는다.
    let rules = spec();
    let mut checked = 0;

    for (kind, step) in rules.step_kinds(CycleKind::Experiment) {
        for (field, constraint) in &step.field_constraints {
            for (deciding_field, table) in &constraint.allowed_values_when {
                for (deciding_value, narrowed) in table {
                    let base = full_report(&rules, CycleKind::Experiment, kind)
                        .with(deciding_field.clone(), deciding_value.clone());

                    // 좁혀진 값은 통과한다.
                    for value in narrowed {
                        let report = base.clone().with(field.clone(), value.clone());
                        rules.validate_close(CycleKind::Experiment, kind, &report).unwrap_or_else(|err| {
                            panic!("{deciding_field}={deciding_value} 일 때 {field}={value} 가 거절됐다: {err}")
                        });
                    }

                    // 좁혀서 떨어져 나간 값은 거절되고, 왜 좁혀졌는지를 말한다.
                    for value in constraint.allowed_values.iter().filter(|v| !narrowed.contains(v))
                    {
                        let report = base.clone().with(field.clone(), value.clone());
                        let err = rules.validate_close(CycleKind::Experiment, kind, &report).expect_err(&format!(
                            "{deciding_field}={deciding_value} 인데 {field}={value} 가 통과했다"
                        ));
                        match &err {
                            GrammarError::FieldValueNotAllowed { narrowed_by, .. } => {
                                assert_eq!(
                                    narrowed_by.as_ref().map(|(f, v)| (f.as_str(), v.as_str())),
                                    Some((deciding_field.as_str(), deciding_value.as_str())),
                                    "왜 좁혀졌는지를 말해야 한다"
                                );
                            }
                            other => panic!("거절 이유가 값 위반이어야 한다: {other:?}"),
                        }
                        assert!(err.to_string().contains(deciding_field), "{err}");
                        checked += 1;
                    }
                }
            }
        }
    }
    assert!(checked > 0, "좁혀서 떨어지는 값이 하나도 없다 — 이 시험이 눈멀었다");
}

#[test]
fn a_boundary_marker_is_not_a_step_and_cannot_be_closed() {
    let rules = spec();
    for boundary in [NodeKind::CycleEntry, NodeKind::CycleExit] {
        let err = rules
            .validate_close(CycleKind::Experiment, boundary, &Report::new())
            .expect_err("경계 표식은 닫는 대상이 아니다");
        assert_eq!(err, GrammarError::UnknownStepKind(boundary));
    }
}

// ── 두 Cycle Kind 는 서로의 Step 을 열지 못한다 ────────────────────────────

/// 그 Cycle Kind 안에서 선언된 Step Kind 전부.
fn kinds_of(rules: &RuleSet, cycle: CycleKind) -> Vec<NodeKind> {
    rules.step_kinds(cycle).map(|(kind, _)| kind).collect()
}

#[test]
fn each_cycle_kind_declares_its_own_step_grammar() {
    let rules = spec();
    assert_eq!(
        kinds_of(&rules, CycleKind::Interview),
        vec![
            NodeKind::Question,
            NodeKind::Interpretation,
            NodeKind::Synthesis,
            NodeKind::Outcome,
        ],
        "Interview 의 Step 문법이 명세와 다르다"
    );
    assert_eq!(
        kinds_of(&rules, CycleKind::Experiment),
        vec![
            NodeKind::Define,
            NodeKind::Hypothesis,
            NodeKind::Verify,
            NodeKind::Analysis,
            NodeKind::Outcome,
        ],
        "Experiment 의 Step 문법이 명세와 다르다"
    );
}

#[test]
fn neither_cycle_kind_can_open_the_others_steps() {
    // **문법을 섞지 않는다.** Interview 에서 가설을 세우지 않고, Experiment 에서 사람에게
    // 묻지 않는다. 같은 이름의 `outcome` 만이 둘의 것이고, 요구하는 Report 는 서로 다르다.
    let rules = spec();
    let shared = [NodeKind::Outcome];

    for (mine, theirs) in [
        (CycleKind::Interview, CycleKind::Experiment),
        (CycleKind::Experiment, CycleKind::Interview),
    ] {
        for kind in kinds_of(&rules, theirs) {
            if shared.contains(&kind) {
                continue;
            }
            assert!(
                !rules.declares(mine, kind),
                "{mine} 이(가) {theirs} 의 {kind} 를 선언했다"
            );
            // 어느 자리에서 물어도 열리지 않는다 — 부모를 전수로 훑는다.
            for parent in NodeKind::ALL {
                assert!(
                    rules
                        .validate_open(mine, Node::closed(parent), kind)
                        .is_err(),
                    "{mine} 의 {parent} 뒤에서 {theirs} 의 {kind} 가 열렸다"
                );
            }
        }
    }
}

#[test]
fn the_shared_outcome_asks_for_different_reports() {
    // 이름이 같다고 규칙이 같지는 않다. Interview 의 판정은 승인된 Synthesis 를 가리켜야
    // 하고 success 로만 닫힌다.
    let rules = spec();
    let interview = rules
        .rules(CycleKind::Interview, NodeKind::Outcome)
        .expect("Interview 에도 판정이 있다");
    let experiment = rules
        .rules(CycleKind::Experiment, NodeKind::Outcome)
        .expect("Experiment 에도 판정이 있다");

    assert!(
        interview.close_requires.contains(&"synthesis_ref".to_string()),
        "Interview 의 판정이 근거를 가리키지 않는다"
    );
    assert!(
        !experiment.close_requires.contains(&"synthesis_ref".to_string()),
        "Experiment 의 판정이 Synthesis 를 요구한다"
    );
    assert_eq!(
        interview.field_constraints["verdict"].allowed_values,
        vec!["success".to_string()],
        "Interview 는 success 로만 닫힌다"
    );
    assert_eq!(
        experiment.field_constraints["verdict"].allowed_values,
        vec!["success".to_string(), "failure".to_string()],
    );
}

#[test]
fn the_interview_starts_with_a_question_and_the_experiment_with_a_define() {
    let rules = spec();
    let entry = Node::cycle_entry();
    assert_eq!(
        rules.allowed_children_of(CycleKind::Interview, NodeKind::CycleEntry),
        vec![NodeKind::Question]
    );
    assert_eq!(
        rules.allowed_children_of(CycleKind::Experiment, NodeKind::CycleEntry),
        vec![NodeKind::Define]
    );
    assert!(
        rules
            .validate_open(CycleKind::Interview, entry, NodeKind::Define)
            .is_err()
    );
    assert!(
        rules
            .validate_open(CycleKind::Experiment, entry, NodeKind::Question)
            .is_err()
    );
}

// ── Cycle Kind 설명은 문법이 갖는다 ────────────────────────────────────────

#[test]
fn every_cycle_kind_carries_its_own_one_line_description() {
    // 고를 것이 여럿일 때 화면에 나올 말이다. renderer 에 흩어 적으면 Kind 가 늘 때
    // 한쪽이 낡고, 그때 사람은 화면이 왜 옛말을 하는지 모른다(Agent UX Model §4.2).
    let rules = spec();
    for kind in CycleKind::ALL {
        let description = &rules
            .cycle_rules(kind)
            .unwrap_or_else(|| panic!("{kind} 의 규칙이 있다"))
            .description;
        assert!(!description.trim().is_empty(), "{kind} 에 설명이 없다");
    }
    // 그리고 서로 다른 말이어야 한다 — 같으면 고르는 데 도움이 안 된다.
    let said: Vec<&str> = CycleKind::ALL
        .iter()
        .map(|kind| rules.cycle_rules(*kind).unwrap().description.as_str())
        .collect();
    assert_ne!(said[0], said[1], "두 Kind 의 설명이 같다");
}

#[test]
fn a_cycle_kind_without_a_description_is_refused() {
    // 설명 없는 Kind 를 더하면 **읽을 때** 걸린다 — 고를 자리에 가서야 알게 되지 않도록.
    for missing in CycleKind::ALL {
        let mut yaml = String::from("cycle_kinds:\n");
        for kind in CycleKind::ALL {
            let described = match kind == missing {
                true => String::new(),
                false => format!("    description: {kind} 를 하는 자리\n"),
            };
            yaml.push_str(&format!(
                "  {kind}:\n{described}    close_requires: [verdict]\n    step_kinds:\n      \
                 define:\n        allowed_parents: [cycle_entry]\n        \
                 allowed_children: []\n        close_requires: [problem]\n"
            ));
        }
        let err = RuleSet::from_yaml_str(&yaml)
            .expect_err("설명 없는 Cycle Kind 가 있는 명세가 통과했다");
        let message = err.to_string();
        assert!(
            message.contains(missing.as_str()) && message.contains("description"),
            "어느 Kind 에 설명이 없는지 말해야 한다: {message}"
        );
    }
}
