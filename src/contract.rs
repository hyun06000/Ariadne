//! Close 계약 — **이 자리를 닫으려면 무엇을 적어야 하는가.**
//!
//! 세 자리가 같은 것을 말해야 한다.
//!
//! ```text
//! gil open  Receipt   닫기 전에 계약을 미리 알려 준다
//! gil close --help    지금 자리의 계약만 읽기 전용으로 보여 준다
//! gil close 의 거절   빠진 값과 고치는 법을 말한다
//! ```
//!
//! 셋이 각자 문자열을 지으면 반드시 갈린다 — 하나만 고쳐 두고 다른 둘은 옛말을 한다.
//! 그래서 **문법에서 읽은 것 하나**를 세 자리가 함께 쓴다. 이 모듈이 그 하나다.
//!
//! # 왜 값의 뜻까지 싣는가
//!
//! 실사용 dogfood 에서 Agent 는 `next_direction.action` 의 허용값을 **오류를 통해서만**
//! 알아냈다 — 무엇을 적을 수 있는지 몰라 일부러 한 번 틀린 것이다. `close_cycle` 이라는
//! 글자만 보여 주는 것으로는 부족하다: 그것이 **어느 계층에서 무엇을 움직이는지** 알아야
//! 고를 수 있다.
//!
//! ```text
//! Outcome.next_direction.action  = close_cycle   Step Graph 를 끝내고 Cycle 경계로
//! CycleReport.next_direction.action = open_child 닫힌 Cycle 을 부모로 다음 Cycle 을
//! ```
//!
//! 둘은 반대되는 명령이 아니라 **계층이 다른, 차례로 쓰는 방향**이다. 그 말은 renderer 가
//! 아니라 `gil-spec.yaml` 이 갖는다.

use std::collections::BTreeMap;
use std::fmt::Write as _;

use crate::rules::{FieldConstraint, RuleSet};
use crate::cycle::CycleKind;
use crate::node::NodeKind;

/// 고를 수 있는 값 하나와 **그것이 무엇을 움직이는가.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ValueChoice {
    pub value: String,
    pub meaning: String,
}

/// 다른 칸의 값이 이 칸을 가르는 경우 — 그 한 갈래.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Branch {
    /// 가르는 칸의 이름. dotted canonical 표기다.
    pub deciding: String,
    /// 그 칸이 이 값일 때.
    pub when: String,
    pub values: Vec<ValueChoice>,
}

/// 한 칸을 적는 계약.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct FieldContract {
    /// dotted canonical 이름 — 사람이 그대로 베껴 적는 글자다.
    pub name: String,
    /// 비워 둘 수 없는가.
    pub non_empty: bool,
    /// 지금 그대로 고를 수 있는 값들. 자유 서술이면 비어 있다.
    ///
    /// **갈래가 있으면 여기는 비운다** — 실제로 적용되는 것은 갈래 쪽이고, 둘 다 실으면
    /// 같은 설명이 두 번 나온다.
    pub values: Vec<ValueChoice>,
    /// 다른 칸이 값을 가르는 경우의 갈래들.
    pub branches: Vec<Branch>,
    /// 명세에는 있으나 **아직 밟을 수 없는** 값 — 값과 그 까닭.
    pub not_yet: Vec<(String, String)>,
}

impl FieldContract {
    /// 값을 열거하지 않는 자유 서술 칸인가.
    pub fn is_free_text(&self) -> bool {
        self.values.is_empty() && self.branches.is_empty()
    }
}

/// 이 자리를 닫는 계약 전부.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CloseContract {
    /// 무엇을 닫는가 — `step:C2/S5 · outcome` 또는 `cycle:C2 · experiment`.
    subject: String,
    fields: Vec<FieldContract>,
}

impl CloseContract {
    /// 그 Cycle Kind 안의 Step 하나를 닫는 계약.
    pub fn of_step(
        rules: &RuleSet,
        cycle: CycleKind,
        kind: NodeKind,
        subject: impl Into<String>,
    ) -> Option<CloseContract> {
        let step = rules.rules(cycle, kind)?;
        Some(CloseContract {
            subject: subject.into(),
            fields: read_fields(&step.close_requires, &step.field_constraints),
        })
    }

    /// Cycle 하나를 닫는 계약.
    pub fn of_cycle(
        rules: &RuleSet,
        cycle: CycleKind,
        subject: impl Into<String>,
    ) -> Option<CloseContract> {
        let declared = rules.cycle_rules(cycle)?;
        Some(CloseContract {
            subject: subject.into(),
            fields: read_fields(&declared.close_requires, &declared.field_constraints),
        })
    }

    pub fn subject(&self) -> &str {
        &self.subject
    }

    pub fn fields(&self) -> &[FieldContract] {
        &self.fields
    }

    /// 적어야 하는 칸의 이름들 — **명세가 부르는 그대로, dotted canonical.**
    pub fn field_names(&self) -> Vec<&str> {
        self.fields.iter().map(|field| field.name.as_str()).collect()
    }

    /// 사람이 그대로 베껴 적는 골격. `hint` 는 `# step:C2/S5 · outcome` 처럼 뒤에 붙는다.
    ///
    /// `fill` 이 값을 주면 `…` 대신 그 값을 적는다 — Cycle Report 의 `outcome_ref` 처럼
    /// **가리켜야 하는 주소가 이미 정해진** 칸이 있기 때문이다.
    pub fn skeleton(&self, fill: impl Fn(&str) -> Option<String>) -> String {
        let mut out = format!("  gil close <<'EOF'   # {}\n", self.subject);
        for field in &self.fields {
            match fill(&field.name) {
                Some(value) => out.push_str(&format!("  {}: {value}\n", field.name)),
                None => out.push_str(&format!("  {}: …\n", field.name)),
            }
        }
        out.push_str("  EOF");
        out
    }

    /// 칸마다 무엇을 적을 수 있는지 — **지금 이 자리에 필요한 것만.**
    ///
    /// 다른 Node Kind 의 제약도, 전체 문법도 여기서 펼치지 않는다. 자유 서술 칸은 이름만
    /// 나온다 — 열거할 값이 없는 칸에 줄을 더 쓰면 정작 골라야 하는 칸이 안 읽힌다.
    pub fn constraints(&self, indent: &str) -> String {
        let mut out = String::new();
        for (index, field) in self.fields.iter().enumerate() {
            // 값이 딸린 칸은 앞뒤로 빈 줄을 둔다 — 어디까지가 한 칸의 선택지인지
            // 눈으로 갈려야 한다. 이름만 있는 칸끼리는 붙여 둔다.
            if index > 0 && !(self.fields[index - 1].is_free_text() && field.is_free_text()) {
                out.push('\n');
            }
            let _ = write!(out, "{indent}{}", field.name);
            if field.non_empty && field.is_free_text() {
                out.push_str("  (비울 수 없다)");
            }
            out.push('\n');

            // 한 칸 안에서 **같은 값의 뜻을 두 번 적지 않는다.** 갈래가 여럿이면 같은 값이
            // 여러 갈래에 나오는데, 그때마다 설명을 되풀이하면 정작 갈래의 차이가 안 읽힌다.
            let mut said: Vec<&str> = Vec::new();
            for choice in &field.values {
                say(&mut out, indent, "  ", choice, &mut said);
            }
            for branch in &field.branches {
                let _ = writeln!(out, "{indent}  {}가 {}이면", branch.deciding, branch.when);
                for choice in &branch.values {
                    say(&mut out, indent, "    ", choice, &mut said);
                }
            }
            // 아직 밟을 수 없는 값은 **허용값 목록에 섞지 않는다.** 섞으면 읽는 쪽이 그것을
            // 적고, 적은 뒤에야 아직임을 알게 된다.
            if !field.not_yet.is_empty() {
                let _ = writeln!(out, "{indent}  아직 없음");
                for (value, why) in &field.not_yet {
                    let _ = writeln!(out, "{indent}    {value} — {why}");
                }
            }
        }
        out
    }
}

/// 값 한 줄 — 처음 나올 때만 뜻을 붙인다.
fn say<'a>(
    out: &mut String,
    indent: &str,
    depth: &str,
    choice: &'a ValueChoice,
    said: &mut Vec<&'a str>,
) {
    match said.contains(&choice.value.as_str()) {
        true => {
            let _ = writeln!(out, "{indent}{depth}{}", choice.value);
        }
        false => {
            said.push(&choice.value);
            let _ = writeln!(out, "{indent}{depth}{} — {}", choice.value, choice.meaning);
        }
    }
}

/// 요구된 칸들을 계약으로 읽는다 — **계층을 가리지 않는다.**
///
/// Step 이든 Cycle 이든 문법의 어휘가 같으므로 읽는 방식도 하나다.
fn read_fields(
    close_requires: &[String],
    constraints: &BTreeMap<String, FieldConstraint>,
) -> Vec<FieldContract> {
    close_requires
        .iter()
        .map(|name| match constraints.get(name) {
            None => FieldContract {
                name: name.clone(),
                non_empty: false,
                values: Vec::new(),
                branches: Vec::new(),
                not_yet: Vec::new(),
            },
            Some(constraint) => {
                let branches: Vec<Branch> = constraint
                    .allowed_values_when
                    .iter()
                    .flat_map(|(deciding, table)| {
                        // 갈래의 차례는 **가르는 칸이 값을 적어 둔 차례**다. 표는 이름순으로
                        // 눕지만 사람이 읽는 차례는 명세가 적은 차례여야 한다.
                        ordered(constraints.get(deciding), table)
                            .into_iter()
                            .map(move |(when, narrowed)| Branch {
                                deciding: deciding.clone(),
                                when: when.clone(),
                                values: choices(constraint, narrowed.iter().map(String::as_str)),
                            })
                    })
                    .collect();
                FieldContract {
                    name: name.clone(),
                    non_empty: constraint.non_empty,
                    // 갈래가 있으면 평평한 목록은 싣지 않는다 — 같은 설명을 두 번 내지 않는다.
                    values: match branches.is_empty() {
                        true => choices(constraint, constraint.allowed_values.iter().map(String::as_str)),
                        false => Vec::new(),
                    },
                    branches,
                    not_yet: constraint
                        .not_yet
                        .iter()
                        .map(|(value, why)| (value.clone(), why.clone()))
                        .collect(),
                }
            }
        })
        .collect()
}

/// 가르는 칸이 값을 적어 둔 차례로 표를 늘어놓는다. 그 칸에 열거가 없으면 이름순 그대로.
fn ordered<'a>(
    deciding: Option<&FieldConstraint>,
    table: &'a BTreeMap<String, Vec<String>>,
) -> Vec<(&'a String, &'a Vec<String>)> {
    let Some(deciding) = deciding else {
        return table.iter().collect();
    };
    let mut rows: Vec<(&String, &Vec<String>)> = Vec::with_capacity(table.len());
    for value in &deciding.allowed_values {
        if let Some((key, narrowed)) = table.get_key_value(value) {
            rows.push((key, narrowed));
        }
    }
    for (key, narrowed) in table {
        if !rows.iter().any(|(seen, _)| *seen == key) {
            rows.push((key, narrowed));
        }
    }
    rows
}

/// 값들에 **명세가 적어 둔 뜻**을 붙인다. 뜻은 여기서 짓지 않는다.
fn choices<'a>(
    constraint: &FieldConstraint,
    values: impl Iterator<Item = &'a str>,
) -> Vec<ValueChoice> {
    values
        .map(|value| ValueChoice {
            value: value.to_string(),
            meaning: constraint.meaning_of(value).to_string(),
        })
        .collect()
}
