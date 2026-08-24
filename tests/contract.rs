//! Close 계약 — **닫기 전에 무엇을 적을 수 있는지 알려 준다.**
//!
//! 여기서 재는 것은 셋이다.
//!
//! 1. **설명의 진실 원천은 문법이다** — 빠지면 명세를 읽지 않는다.
//! 2. **실행 가능한 값만 허용값으로 보인다** — 아직 없는 값은 따로 선다.
//! 3. **같은 계약을 세 자리가 함께 본다** — Receipt·help·거절이 갈리지 않게.
//!
//! 이 시험들이 있는 까닭은 실사용 M2C 보고다: Agent 가 `next_direction.action` 의 허용값을
//! **오류를 통해서만** 알아냈다. 무엇을 적을 수 있는지 몰라 일부러 한 번 틀린 것이다.

use gil::{CloseContract, CycleKind, NodeKind, RuleSet};

mod common;
use common::spec;

/// 그 Cycle Kind 의 Step 계약. 없으면 시험이 멈춘다.
fn step(cycle: CycleKind, kind: NodeKind) -> CloseContract {
    CloseContract::of_step(&spec(), cycle, kind, format!("{cycle}.{kind}"))
        .unwrap_or_else(|| panic!("{cycle} 안에 {kind} 규칙이 없다"))
}

fn cycle_of(kind: CycleKind) -> CloseContract {
    CloseContract::of_cycle(&spec(), kind, kind.to_string()).expect("Cycle 규칙이 있다")
}

/// 그 칸의 계약.
fn field<'a>(contract: &'a CloseContract, name: &str) -> &'a gil::FieldContract {
    contract
        .fields()
        .iter()
        .find(|field| field.name == name)
        .unwrap_or_else(|| panic!("{name} 이(가) 계약에 없다"))
}

// ── ① 설명의 진실 원천은 문법이다 ─────────────────────────────────────────

#[test]
fn every_runnable_value_the_spec_declares_says_what_it_moves() {
    // renderer 에 값별 설명을 하드코딩하지 않으려면, 문법이 하나도 빠짐없이 갖고 있어야 한다.
    let rules = spec();
    for (cycle, declared) in rules.cycle_kinds() {
        for (field, constraint) in &declared.field_constraints {
            for value in constraint.every_value() {
                assert!(
                    !constraint.meaning_of(value).trim().is_empty(),
                    "{cycle} cycle 의 {field}={value} 가 무엇을 움직이는지 문법이 말하지 않는다"
                );
            }
        }
        for (kind, step) in rules.step_kinds(cycle) {
            for (field, constraint) in &step.field_constraints {
                for value in constraint.every_value() {
                    assert!(
                        !constraint.meaning_of(value).trim().is_empty(),
                        "{cycle}.{kind} 의 {field}={value} 가 무엇을 움직이는지 \
                         문법이 말하지 않는다"
                    );
                }
            }
        }
    }
}

/// 그 조각을 담은, 그 밖은 온전한 명세.
fn spec_with(field_constraints: &str) -> String {
    format!(
        "cycle_kinds:\n  \
         interview:\n    description: 묻는 자리\n    \
         close_requires: [verdict, next_direction.action]\n    \
         field_constraints:\n{field_constraints}    \
         step_kinds:\n      \
         question:\n        description: 묻는다\n        allowed_parents: [cycle_entry]\n        \
         allowed_children: []\n        close_requires: [response]\n  \
         experiment:\n    description: 실험하는 자리\n    close_requires: [verdict]\n    \
         step_kinds:\n      \
         define:\n        description: 정하는 자리\n        allowed_parents: [cycle_entry]\n        \
         allowed_children: []\n        close_requires: [problem]\n"
    )
}

#[test]
fn an_allowed_value_without_a_description_is_refused_at_load() {
    // 설명 없는 값은 화면에 raw enum 으로만 나오고, 읽는 쪽은 그것을 오류로 알아낸다.
    let err = RuleSet::from_yaml_str(&spec_with(
        "      verdict:\n        allowed_values: [success, failure]\n        \
         value_descriptions:\n          success: 성공 조건이 충족되었다\n",
    ))
    .expect_err("설명 없는 허용값이 통과했다");
    let message = err.to_string();
    assert!(message.contains("failure"), "어느 값인지 말해야 한다: {message}");
    assert!(message.contains("value_descriptions"), "{message}");
}

#[test]
fn a_conditional_only_value_without_a_description_is_refused_at_load() {
    // 조건부로만 허용되는 값도 화면에 나온다 — 그것도 스스로를 설명해야 한다.
    let err = RuleSet::from_yaml_str(&spec_with(
        "      verdict:\n        allowed_values: [success, failure]\n        \
         value_descriptions:\n          success: 충족되었다\n          failure: 충족되지 않았다\n      \
         next_direction.action:\n        allowed_values_when:\n          \
         verdict:\n            success: [open_child]\n",
    ))
    .expect_err("조건부 값의 설명이 없는데 통과했다");
    let message = err.to_string();
    assert!(message.contains("open_child"), "{message}");
}

#[test]
fn an_empty_description_is_refused_at_load() {
    let err = RuleSet::from_yaml_str(&spec_with(
        "      verdict:\n        allowed_values: [success]\n        \
         value_descriptions:\n          success: \"   \"\n",
    ))
    .expect_err("빈 설명이 통과했다");
    assert!(err.to_string().contains("success"), "{err}");
}

#[test]
fn a_description_for_a_value_that_cannot_occur_is_refused_at_load() {
    // 아무 값도 가리키지 않는 설명은 한 번도 화면에 안 나온다 — 적은 사람은 나온다고 믿는다.
    let err = RuleSet::from_yaml_str(&spec_with(
        "      verdict:\n        allowed_values: [success]\n        \
         value_descriptions:\n          success: 충족되었다\n          maybe: 어중간하다\n",
    ))
    .expect_err("허공을 가리키는 설명이 통과했다");
    assert!(err.to_string().contains("maybe"), "{err}");
}

#[test]
fn a_not_yet_value_must_not_also_be_described_as_runnable() {
    // 아직인 까닭은 not_yet 하나가 갖는다. 둘로 나뉘면 한쪽이 낡는다.
    let err = RuleSet::from_yaml_str(&spec_with(
        "      verdict:\n        allowed_values: [success]\n        \
         value_descriptions:\n          success: 충족되었다\n          later: 나중 값\n        \
         not_yet:\n          later: 아직 짓지 않았다\n",
    ))
    .expect_err("아직인 값이 실행 가능한 값처럼 설명됐다");
    assert!(err.to_string().contains("later"), "{err}");
}

#[test]
fn a_step_kind_without_a_description_is_refused_at_load() {
    // 열 곳이 여럿일 때 보여 줄 말이 없으면 사람은 이름만 보고 고른다.
    let yaml = "cycle_kinds:\n  \
                interview:\n    description: 묻는 자리\n    close_requires: [verdict]\n    \
                step_kinds:\n      \
                question:\n        allowed_parents: [cycle_entry]\n        \
                allowed_children: []\n        close_requires: [response]\n  \
                experiment:\n    description: 실험하는 자리\n    close_requires: [verdict]\n    \
                step_kinds:\n      \
                define:\n        description: 정하는 자리\n        allowed_parents: [cycle_entry]\n        \
                allowed_children: []\n        close_requires: [problem]\n";
    let err = RuleSet::from_yaml_str(yaml).expect_err("설명 없는 Step Kind 가 통과했다");
    let message = err.to_string();
    assert!(message.contains("question") && message.contains("description"), "{message}");
}

// ── ② 실행 가능한 값만 허용값으로 보인다 ──────────────────────────────────

#[test]
fn only_runnable_values_are_offered_and_not_yet_stands_apart() {
    // Interview Cycle 의 next_direction.action 은 open_child 하나뿐이고,
    // close_chain 은 명세에 있지만 아직 밟을 수 없다.
    let contract = cycle_of(CycleKind::Interview);
    let action = field(&contract, "next_direction.action");

    let offered: Vec<&str> = action.values.iter().map(|v| v.value.as_str()).collect();
    assert_eq!(offered, ["open_child"], "실행할 수 없는 값이 섞였다");
    assert_eq!(
        action.not_yet,
        vec![("close_chain".to_string(), "Chain 을 아직 짓지 않았다".to_string())]
    );

    let shown = contract.constraints("  ");
    let (offered_part, not_yet_part) = shown
        .split_once("아직 없음")
        .expect("아직인 값은 따로 선다");
    assert!(
        !offered_part.contains("close_chain"),
        "아직인 값이 허용값에 섞였다:\n{shown}"
    );
    assert!(not_yet_part.contains("close_chain") && not_yet_part.contains("아직 짓지 않았다"));
}

#[test]
fn a_free_text_field_shows_only_its_name() {
    // 열거할 값이 없는 칸에 줄을 더 쓰면 정작 골라야 하는 칸이 안 읽힌다.
    let contract = step(CycleKind::Experiment, NodeKind::Define);
    for name in ["problem", "success_condition"] {
        assert!(field(&contract, name).is_free_text(), "{name} 이 자유 서술이 아니다");
    }
    let shown = contract.constraints("  ");
    assert_eq!(shown, "  problem\n  success_condition\n", "{shown}");
}

// ── ③ 계층이 분명해야 한다 ────────────────────────────────────────────────

#[test]
fn the_outcome_close_cycle_says_it_moves_inside_this_cycle() {
    // Outcome 의 close_cycle 은 **Step Graph 를 끝내고 Cycle 경계로** 옮기는 것이다.
    let contract = step(CycleKind::Experiment, NodeKind::Outcome);
    let action = field(&contract, "next_direction.action");
    let meaning = action
        .branches
        .iter()
        .flat_map(|branch| &branch.values)
        .find(|choice| choice.value == "close_cycle")
        .expect("close_cycle 이 갈래에 있다")
        .meaning
        .clone();

    assert!(meaning.contains("Step"), "어느 계층인지 안 밝힌다: {meaning}");
    assert!(
        meaning.contains("Cycle Report"),
        "어디로 옮겨 서는지 안 말한다: {meaning}"
    );
    assert!(
        !meaning.contains("다음 Cycle"),
        "Cycle Report 의 open_child 와 같은 말을 한다: {meaning}"
    );
}

#[test]
fn the_cycle_report_open_child_says_it_opens_the_next_cycle() {
    // Cycle Report 의 open_child 는 **닫힌 Cycle 을 부모로 다음 Cycle 을** 여는 것이다.
    for kind in CycleKind::ALL {
        let contract = cycle_of(kind);
        let action = field(&contract, "next_direction.action");
        let meaning = action
            .values
            .iter()
            .chain(action.branches.iter().flat_map(|branch| &branch.values))
            .find(|choice| choice.value == "open_child")
            .unwrap_or_else(|| panic!("{kind} Cycle 에 open_child 가 없다"))
            .meaning
            .clone();

        assert!(meaning.contains("Cycle 계층"), "{kind}: {meaning}");
        assert!(meaning.contains("다음 Cycle"), "{kind}: {meaning}");
    }
}

#[test]
fn the_two_layers_of_revisit_name_different_targets() {
    // 같은 낱말이 계층에 따라 다른 것을 가리킨다 — 그 차이가 글에 있어야 한다.
    let step_revisit = {
        let contract = step(CycleKind::Experiment, NodeKind::Outcome);
        field(&contract, "next_direction.action")
            .branches
            .iter()
            .flat_map(|branch| &branch.values)
            .find(|choice| choice.value == "revisit")
            .expect("Step 계층의 revisit")
            .meaning
            .clone()
    };
    let cycle_revisit = {
        let contract = cycle_of(CycleKind::Experiment);
        let action = field(&contract, "next_direction.action");
        action
            .values
            .iter()
            .chain(action.branches.iter().flat_map(|branch| &branch.values))
            .find(|choice| choice.value == "revisit")
            .expect("Cycle 계층의 revisit")
            .meaning
            .clone()
    };

    assert!(step_revisit.contains("step:"), "Step 대상을 안 밝힌다: {step_revisit}");
    assert!(cycle_revisit.contains("cycle:"), "Cycle 대상을 안 밝힌다: {cycle_revisit}");
    assert_ne!(step_revisit, cycle_revisit, "두 계층이 같은 말을 한다");
}

// ── ④ 조건부 허용값 ───────────────────────────────────────────────────────

#[test]
fn a_conditional_field_is_projected_branch_by_branch() {
    let contract = step(CycleKind::Experiment, NodeKind::Outcome);
    let action = field(&contract, "next_direction.action");

    assert!(
        action.values.is_empty(),
        "갈래가 있는데 평평한 목록까지 실었다 — 같은 설명이 두 번 나온다"
    );
    let shape: Vec<(String, Vec<String>)> = action
        .branches
        .iter()
        .map(|branch| {
            (
                format!("{}={}", branch.deciding, branch.when),
                branch.values.iter().map(|v| v.value.clone()).collect(),
            )
        })
        .collect();
    assert_eq!(
        shape,
        vec![
            ("verdict=success".to_string(), vec!["close_cycle".to_string()]),
            (
                "verdict=failure".to_string(),
                vec!["revisit".to_string(), "close_cycle".to_string()]
            ),
        ],
        "가르는 칸이 적어 둔 차례를 따르지 않는다"
    );

    let shown = action_block(&contract);
    assert!(shown.contains("verdict가 success이면"), "{shown}");
    assert!(shown.contains("verdict가 failure이면"), "{shown}");
}

#[test]
fn a_meaning_is_not_repeated_inside_one_field() {
    // close_cycle 은 두 갈래에 모두 나온다. 그때마다 설명을 되풀이하면 갈래의 차이가 안 읽힌다.
    let contract = step(CycleKind::Experiment, NodeKind::Outcome);
    let shown = action_block(&contract);
    let meaning = "이 Cycle 의 Step Graph 를 끝내고";
    assert_eq!(
        shown.matches(meaning).count(),
        1,
        "같은 설명이 두 번 나왔다:\n{shown}"
    );
    assert_eq!(shown.matches("close_cycle").count(), 2, "값 자체는 두 갈래에 다 나온다");
}

/// `next_direction.action` 절만 잘라 본다.
fn action_block(contract: &CloseContract) -> String {
    let shown = contract.constraints("  ");
    let start = shown
        .find("  next_direction.action\n")
        .expect("그 칸이 있다");
    let tail = &shown[start..];
    match tail[1..].find("\n\n") {
        Some(end) => tail[..end + 1].to_string(),
        None => tail.to_string(),
    }
}

// ── ⑤ 골격은 dotted canonical ─────────────────────────────────────────────

#[test]
fn the_skeleton_names_its_fields_the_dotted_way() {
    let contract = step(CycleKind::Experiment, NodeKind::Outcome);
    let shown = contract.skeleton(|_| None);

    assert!(shown.contains("next_direction.action: …"), "{shown}");
    assert!(shown.contains("next_direction.reason: …"), "{shown}");
    assert!(!shown.contains("next_direction:\n"), "접힌 꼴을 내보였다:\n{shown}");
    assert_eq!(
        contract.field_names(),
        ["verdict", "lesson", "next_direction.action", "next_direction.reason"]
    );
}

#[test]
fn a_field_whose_address_is_already_decided_is_filled_in() {
    // Cycle Report 의 outcome_ref 는 가리켜야 하는 주소가 이미 정해져 있다.
    let contract = cycle_of(CycleKind::Experiment);
    let shown = contract.skeleton(|field| match field {
        "outcome_ref" => Some("step:C2/S5".to_string()),
        _ => None,
    });
    assert!(shown.contains("outcome_ref: step:C2/S5"), "{shown}");
    assert!(shown.contains("verdict: …"), "{shown}");
}
