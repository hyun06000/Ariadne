//! `gil-spec.yaml` 을 읽어 담는 자리.
//!
//! **규칙은 코드가 아니라 이 파일이 갖는다.** 여기 있는 것은 그 파일을 읽고, 스스로
//! 앞뒤가 맞는지 확인하는 일뿐이다.
//!
//! 계층이 둘이다 — Cycle 을 닫는 규칙과 그 안의 Step 을 닫는 규칙.
//! **둘은 같은 어휘를 쓴다**: 어떤 칸이 있어야 하는가 · 어떤 값이 올 수 있는가 ·
//! 비어도 되는가 · 다른 칸이 값을 좁히는가. 계층이 달라도 묻는 방식은 같기 때문이다.
//!
//! **Step 문법은 Cycle Kind 안에 산다.** 같은 이름의 Step 이라도 Interview 와 Experiment 가
//! 요구하는 것이 다르고, 서로의 Step 을 열 수 없어야 한다. 한 자리에 평평하게 두면 그 둘을
//! 가를 방법이 없다.

use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::Path;

use serde::Deserialize;

use crate::cycle::CycleKind;
use crate::node::NodeKind;

/// 한 Step Kind 의 규칙.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StepRules {
    /// **이 Kind 가 무엇을 하는 자리인가** — 한 줄로.
    ///
    /// 열 곳이 여럿일 때와 `gil open --help` 가 보여 주는 말이다. [`CycleRules::description`]
    /// 과 같은 규칙이다 — renderer 에 흩어 적지 않는다(Agent UX Model §4.2).
    #[serde(default)]
    pub description: String,
    /// 이 Kind 를 자식으로 둘 수 있는 부모들.
    pub allowed_parents: Vec<NodeKind>,
    /// 이 Kind 뒤에 열 수 있는 자식들.
    pub allowed_children: Vec<NodeKind>,
    /// 이 Kind 를 닫으려면 Report 에 있어야 하는 칸들.
    pub close_requires: Vec<String>,
    /// 칸의 **값**에 걸리는 제약. 제약이 없는 칸은 여기 없다.
    #[serde(default)]
    pub field_constraints: BTreeMap<String, FieldConstraint>,
}

/// 한 Cycle Kind 의 규칙 — **그 안의 Step 문법까지 함께 갖는다.**
///
/// 같은 이름의 Step 이라도 Cycle Kind 마다 요구하는 것이 다르다. Interview 의 `outcome` 은
/// 승인된 Synthesis 를 가리켜야 하고 `success` 로만 닫히지만, Experiment 의 `outcome` 은
/// `failure` 로도 닫힌다. 그래서 Step 문법은 Cycle Kind **안에** 산다 — 한 자리에 섞어 두면
/// 어느 쪽 규칙인지 물을 수 없다.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct CycleRules {
    /// **이 Kind 가 무엇을 하는 자리인가** — 한 줄로.
    ///
    /// 고를 것이 여럿일 때 사람에게 보여 주는 말이다. renderer 에 흩어 적지 않는다
    /// (Agent UX Model §4.2) — 같은 설명이 두 자리에 있으면 한쪽이 낡고, 그때 Kind 를
    /// 늘린 사람은 화면이 왜 옛말을 하는지 모른다.
    #[serde(default)]
    pub description: String,
    /// 이 Kind 의 Cycle 을 닫으려면 Cycle Report 에 있어야 하는 칸들.
    pub close_requires: Vec<String>,
    #[serde(default)]
    pub field_constraints: BTreeMap<String, FieldConstraint>,
    /// 이 Kind 의 Cycle 안에서 열 수 있는 Step 들.
    pub step_kinds: BTreeMap<NodeKind, StepRules>,
}

/// 한 Report 칸의 값에 걸리는 제약.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FieldConstraint {
    /// 이 칸이 가질 수 있는 값 전부. 비어 있으면 값을 열거하지 않는다는 뜻이다.
    #[serde(default)]
    pub allowed_values: Vec<String>,
    /// 각 값이 **무엇을 움직이는가** — 값 → 한두 문장의 짧은 안내.
    ///
    /// `close_cycle` 이나 `open_child` 같은 raw enum 만 보여 주면, 읽는 쪽은 그것이 어느
    /// 계층에서 무엇을 움직이는지 모른 채 고른다. 실사용 dogfood 에서 Agent 는 허용값을
    /// **오류를 통해서만** 알아냈다 — 그 값을 알아내려고 일부러 한 번 실패한 것이다.
    ///
    /// 그래서 설명의 진실 원천은 renderer 가 아니라 이 파일이다. 실행 가능한 값에는
    /// 빠짐없이 있어야 하고(없으면 명세를 읽지 않는다), 아직 밟을 수 없는 값의 까닭은
    /// [`FieldConstraint::not_yet`] 이 따로 갖는다 — 둘을 한 목록에 섞지 않는다.
    #[serde(default)]
    pub value_descriptions: BTreeMap<String, String>,
    /// 참이면 빈 값(공백뿐인 값 포함)으로는 닫을 수 없다.
    #[serde(default)]
    pub non_empty: bool,
    /// 명세가 정의했지만 **아직 짓지 않은** 값들 — 값 → 아직 못 쓰는 까닭.
    ///
    /// 설계에서 지우는 것과 지금 실행할 수 있는 것은 다르다. 여기 적힌 값은 `allowed_values`
    /// 에 없어 거절되지만, 거절할 때 **왜 아직인지**를 말한다 — 그러지 않으면 명세를 읽은
    /// 사람은 제 눈을 의심하게 된다.
    #[serde(default)]
    pub not_yet: BTreeMap<String, String>,
    /// **다른 칸의 값에 따라** 허용값이 좁아지는 경우.
    ///
    /// `{ 가르는_칸: { 그_칸의_값: [좁혀진 허용값…] } }`.
    /// 가르는 칸의 값이 표에 없으면 좁히지 않는다(`allowed_values` 가 그대로 쓰인다).
    #[serde(default)]
    pub allowed_values_when: BTreeMap<String, BTreeMap<String, Vec<String>>>,
}

impl FieldConstraint {
    /// 다른 칸의 값까지 본 뒤 **지금 이 Report 에서** 이 칸이 가질 수 있는 값.
    ///
    /// 좁히는 근거가 있었다면 (가르는 칸, 그 값) 을 함께 돌려준다 — 거절할 때 이유를 말하려고.
    pub fn allowed_here<'a>(
        &'a self,
        lookup: impl Fn(&str) -> Option<&'a str>,
    ) -> (&'a [String], Option<(&'a str, &'a str)>) {
        for (deciding_field, table) in &self.allowed_values_when {
            let Some(deciding_value) = lookup(deciding_field) else {
                continue;
            };
            if let Some(narrowed) = table.get(deciding_value) {
                return (narrowed, Some((deciding_field, deciding_value)));
            }
        }
        (&self.allowed_values, None)
    }

    /// 그 값이 무엇을 움직이는가. 명세가 적어 두지 않았으면 빈 글.
    ///
    /// 읽을 때 [`RuleSet::from_yaml_str`] 이 이미 빠짐없음을 쟀으므로, 실행 가능한 값에
    /// 대해서는 언제나 비어 있지 않다.
    pub fn meaning_of(&self, value: &str) -> &str {
        self.value_descriptions
            .get(value)
            .map(String::as_str)
            .unwrap_or_default()
    }

    /// 이 칸이 실제로 가질 수 있는 값 전부 — 조건부로만 허용되는 값까지.
    ///
    /// `allowed_values` 가 비어 있어도 `allowed_values_when` 만으로 값이 정해질 수 있다.
    /// 설명이 빠짐없는지 재는 자리와 화면이 같은 목록을 봐야 하므로 여기서 한 번에 모은다.
    pub fn every_value(&self) -> Vec<&str> {
        let mut values: Vec<&str> = self.allowed_values.iter().map(String::as_str).collect();
        for table in self.allowed_values_when.values() {
            for narrowed in table.values() {
                for value in narrowed {
                    if !values.iter().any(|seen| *seen == value.as_str()) {
                        values.push(value);
                    }
                }
            }
        }
        values
    }
}

/// 바이너리에 함께 실린 명세 — 저장소를 떠나 설치된 뒤에도 규칙은 같은 파일에서 온다.
///
/// 옮겨 적은 사본이 아니라 `spec/gil-spec.yaml` **그 파일**이다. 사본을 두면 한쪽이 낡는다.
pub const BUILTIN_SPEC: &str = include_str!(concat!(
    env!("CARGO_MANIFEST_DIR"),
    "/spec/gil-spec.yaml"
));

/// `gil-spec.yaml` 한 벌.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuleSet {
    cycle_kinds: BTreeMap<CycleKind, CycleRules>,
}

impl RuleSet {
    /// 함께 실린 명세로 한 벌 만든다.
    ///
    /// 설치된 `gil` 은 저장소 곁에 서 있지 않다 — 규칙을 찾아 헤매는 대신 지니고 다닌다.
    pub fn builtin() -> Result<Self, SpecError> {
        RuleSet::from_yaml_str(BUILTIN_SPEC)
    }

    /// 문자열에서 읽는다. 읽고 나서 스스로 앞뒤가 맞는지 확인한다.
    pub fn from_yaml_str(yaml: &str) -> Result<Self, SpecError> {
        let set: RuleSet = serde_norway::from_str(yaml).map_err(SpecError::Parse)?;
        set.check_symmetry()?;
        set.check_every_cycle_kind_has_rules()?;
        set.check_every_step_kind_says_what_it_is()?;
        set.check_constraints_point_at_real_fields()?;
        Ok(set)
    }

    /// 파일에서 읽는다.
    pub fn from_path(path: impl AsRef<Path>) -> Result<Self, SpecError> {
        let path = path.as_ref();
        let text = fs::read_to_string(path).map_err(|source| SpecError::Read {
            path: path.display().to_string(),
            source,
        })?;
        RuleSet::from_yaml_str(&text)
    }

    /// 그 Cycle Kind 안에서 이 Step Kind 의 규칙. 그 Cycle 이 열 수 없는 Step 이면 `None`.
    ///
    /// **Cycle Kind 를 함께 묻는다.** 같은 `outcome` 이라도 Interview 와 Experiment 가 요구하는
    /// 것이 다르므로, Cycle 을 모르고 Step 규칙을 답할 수 없다.
    pub fn rules(&self, cycle: CycleKind, kind: NodeKind) -> Option<&StepRules> {
        self.cycle_rules(cycle)?.step_kinds.get(&kind)
    }

    /// 이 Cycle Kind 의 규칙.
    pub fn cycle_rules(&self, kind: CycleKind) -> Option<&CycleRules> {
        self.cycle_kinds.get(&kind)
    }

    /// 명세가 이 Kind 를 **그 Cycle 안의** Step Kind 로 선언했는가.
    pub fn declares(&self, cycle: CycleKind, kind: NodeKind) -> bool {
        self.rules(cycle, kind).is_some()
    }

    /// 그 Cycle Kind 안에 선언된 Step Kind 전부(이름순).
    pub fn step_kinds(&self, cycle: CycleKind) -> impl Iterator<Item = (NodeKind, &StepRules)> {
        self.cycle_rules(cycle)
            .into_iter()
            .flat_map(|rules| rules.step_kinds.iter().map(|(k, v)| (*k, v)))
    }

    /// 선언된 Cycle Kind 전부(이름순).
    pub fn cycle_kinds(&self) -> impl Iterator<Item = (CycleKind, &CycleRules)> {
        self.cycle_kinds.iter().map(|(k, v)| (*k, v))
    }

    /// 그 Cycle 안에서 이 부모 뒤에 열 수 있다고 명세가 말하는 자식들.
    ///
    /// 부모가 선언된 Kind 면 그 `allowed_children` 이고, 경계 표식이면 자신을
    /// `allowed_parents` 에 적어 둔 Kind 들이다. 거절 메시지가 갈 곳을 말할 수 있게 쓴다.
    pub fn allowed_children_of(&self, cycle: CycleKind, parent: NodeKind) -> Vec<NodeKind> {
        match self.rules(cycle, parent) {
            Some(rules) => rules.allowed_children.clone(),
            None => self
                .step_kinds(cycle)
                .filter(|(_, rules)| rules.allowed_parents.contains(&parent))
                .map(|(kind, _)| kind)
                .collect(),
        }
    }

    /// 부모 쪽 선언과 자식 쪽 선언이 서로 어긋나지 않는지 본다.
    ///
    /// 한 변을 두 자리에 적는 구조라 한쪽만 고치면 조용히 갈린다. 그래서 읽을 때 센다.
    /// **Cycle Kind 안에서만 잰다** — 다른 Cycle 의 Step 은 서로의 부모가 될 수 없다.
    fn check_symmetry(&self) -> Result<(), SpecError> {
        for (cycle, _) in self.cycle_kinds() {
            for (parent, rules) in self.step_kinds(cycle) {
                for child in &rules.allowed_children {
                    // 선언되지 않은 Kind(경계 표식)는 제 쪽 목록이 없으니 대조할 것이 없다.
                    if let Some(child_rules) = self.rules(cycle, *child)
                        && !child_rules.allowed_parents.contains(&parent)
                    {
                        return Err(SpecError::Inconsistent(format!(
                            "{cycle}.{parent}.allowed_children 에 {child} 가 있는데 \
                             {child}.allowed_parents 에는 {parent} 가 없다"
                        )));
                    }
                }
                for grandparent in &rules.allowed_parents {
                    if let Some(parent_rules) = self.rules(cycle, *grandparent)
                        && !parent_rules.allowed_children.contains(&parent)
                    {
                        return Err(SpecError::Inconsistent(format!(
                            "{cycle}.{parent}.allowed_parents 에 {grandparent} 가 있는데 \
                             {grandparent}.allowed_children 에는 {parent} 가 없다"
                        )));
                    }
                }
            }
        }
        Ok(())
    }

    /// 이 크레이트가 아는 Cycle Kind 전부에 규칙이 있는지 본다.
    ///
    /// 없으면 그 Kind 의 Cycle 은 **닫을 방법이 없는 채로 열린다** — 여는 자리에서 막지 않으면
    /// 사람이 다 걷고 나서야 알게 된다.
    fn check_every_cycle_kind_has_rules(&self) -> Result<(), SpecError> {
        for kind in CycleKind::ALL {
            let Some(rules) = self.cycle_kinds.get(&kind) else {
                return Err(SpecError::Inconsistent(format!(
                    "cycle_kinds 에 {kind} 가 없다 — 그 Cycle 은 닫을 방법 없이 열리게 된다"
                )));
            };
            // 고를 것이 여럿일 때 이 말이 화면에 나온다. 없으면 사람은 이름만 보고 골라야 한다.
            if rules.description.trim().is_empty() {
                return Err(SpecError::Inconsistent(format!(
                    "cycle_kinds 의 {kind} 에 description 이 없다 — \
                     고를 것이 여럿일 때 보여 줄 말이 없다"
                )));
            }
        }
        Ok(())
    }

    /// 선언된 Step Kind 마다 **무엇을 하는 자리인지** 한 줄이 있는지 본다.
    ///
    /// 없으면 열 곳이 여럿일 때 사람은 이름만 보고 골라야 한다. Cycle Kind 와 같은 규칙이다.
    fn check_every_step_kind_says_what_it_is(&self) -> Result<(), SpecError> {
        for (cycle, _) in self.cycle_kinds() {
            for (kind, rules) in self.step_kinds(cycle) {
                if rules.description.trim().is_empty() {
                    return Err(SpecError::Inconsistent(format!(
                        "{cycle}.{kind} 에 description 이 없다 — \
                         열 곳이 여럿일 때 보여 줄 말이 없다"
                    )));
                }
            }
        }
        Ok(())
    }

    /// 값 제약이 **실재하는 칸**을 가리키는지 본다 — 두 계층 모두.
    ///
    /// `close_requires` 에 없는 칸에 제약을 걸면 그 제약은 한 번도 발동하지 않는다 —
    /// 걸어 둔 사람은 걸렸다고 믿는다. 조용히 안 도는 규칙은 없는 규칙보다 나쁘다.
    fn check_constraints_point_at_real_fields(&self) -> Result<(), SpecError> {
        for (cycle, _) in self.cycle_kinds() {
            for (kind, rules) in self.step_kinds(cycle) {
                check_report_rules(
                    &format!("{cycle}.{kind}"),
                    &rules.close_requires,
                    &rules.field_constraints,
                )?;
            }
        }
        for (kind, rules) in self.cycle_kinds() {
            check_report_rules(
                &format!("{kind} cycle"),
                &rules.close_requires,
                &rules.field_constraints,
            )?;
        }
        Ok(())
    }
}

/// 한 계층의 Report 규칙이 스스로 앞뒤가 맞는지 본다.
///
/// **Step 이든 Cycle 이든 같은 검사를 받는다** — 계층마다 따로 적으면 한쪽이 낡는다.
fn check_report_rules(
    subject: &str,
    close_requires: &[String],
    field_constraints: &BTreeMap<String, FieldConstraint>,
) -> Result<(), SpecError> {
    for (field, constraint) in field_constraints {
        if !close_requires.contains(field) {
            return Err(SpecError::Inconsistent(format!(
                "{subject}.field_constraints 가 {field} 에 값 제약을 걸었는데 \
                 {subject}.close_requires 에는 {field} 가 없다"
            )));
        }
        for (value, why) in &constraint.not_yet {
            if constraint.allowed_values.contains(value) {
                return Err(SpecError::Inconsistent(format!(
                    "{subject}.{field} 가 {value} 를 아직 못 쓴다면서 allowed_values 에도 두었다"
                )));
            }
            if why.trim().is_empty() {
                return Err(SpecError::Inconsistent(format!(
                    "{subject}.{field} 의 {value} 가 아직인 까닭을 적지 않았다"
                )));
            }
        }
        if constraint.allowed_values.is_empty()
            && !constraint.non_empty
            && constraint.allowed_values_when.is_empty()
            && constraint.not_yet.is_empty()
        {
            return Err(SpecError::Inconsistent(format!(
                "{subject}.field_constraints 의 {field} 가 아무것도 제약하지 않는다"
            )));
        }
        check_narrowing(subject, field, constraint, close_requires, field_constraints)?;
        // 값이 무엇인지부터 앞뒤가 맞은 뒤에 **그 값들이 스스로를 설명하는지** 잰다.
        check_value_descriptions(subject, field, constraint)?;
    }
    Ok(())
}

/// **실행 가능한 값에는 빠짐없이 설명이 있는가.**
///
/// 설명이 없는 값은 화면에 raw enum 으로만 나오고, 읽는 쪽은 그것을 알아내려고 한 번
/// 실패한다(실사용 dogfood 가 그랬다). 그래서 없으면 명세를 **읽지 않는다** — 조용히
/// 비워 두면 Kind 를 늘린 사람은 화면이 왜 헐거운지 모른다.
fn check_value_descriptions(
    subject: &str,
    field: &str,
    constraint: &FieldConstraint,
) -> Result<(), SpecError> {
    // ① 조건부로만 허용되는 값까지 포함해 빠짐없이.
    for value in constraint.every_value() {
        match constraint.value_descriptions.get(value) {
            None => {
                return Err(SpecError::Inconsistent(format!(
                    "{subject}.{field} 의 {value} 에 value_descriptions 가 없다 — \
                     raw enum 만 보여 주면 읽는 쪽은 그 값을 오류로 알아내게 된다"
                )));
            }
            Some(meaning) if meaning.trim().is_empty() => {
                return Err(SpecError::Inconsistent(format!(
                    "{subject}.{field} 의 {value} 설명이 비어 있다"
                )));
            }
            Some(_) => {}
        }
    }
    // ② 아직 밟을 수 없는 값은 실행 가능한 값과 **섞이지 않는다.** 까닭은 not_yet 이 갖는다.
    for value in constraint.not_yet.keys() {
        if constraint.value_descriptions.contains_key(value) {
            return Err(SpecError::Inconsistent(format!(
                "{subject}.{field} 의 {value} 가 아직 못 쓰는 값인데 value_descriptions 에도 \
                 있다 — 아직인 까닭은 not_yet 하나가 갖는다"
            )));
        }
    }
    // ③ 아무 값도 가리키지 않는 설명은 한 번도 화면에 안 나온다 — 적은 사람은 나온다고 믿는다.
    for value in constraint.value_descriptions.keys() {
        if !constraint.every_value().iter().any(|v| v == value) {
            return Err(SpecError::Inconsistent(format!(
                "{subject}.{field} 의 value_descriptions 에 {value} 가 있는데 \
                 그 칸은 그 값을 가질 수 없다"
            )));
        }
    }
    Ok(())
}

/// 값을 좁히는 표가 실재하는 칸과 실재하는 값을 가리키는지 본다.
fn check_narrowing(
    subject: &str,
    field: &str,
    constraint: &FieldConstraint,
    close_requires: &[String],
    field_constraints: &BTreeMap<String, FieldConstraint>,
) -> Result<(), SpecError> {
    for (deciding_field, table) in &constraint.allowed_values_when {
        if !close_requires.contains(deciding_field) {
            return Err(SpecError::Inconsistent(format!(
                "{subject}.{field} 의 허용값을 {deciding_field} 가 가르는데 \
                 {subject}.close_requires 에 {deciding_field} 가 없다 — 가를 값이 늘 비어 있다"
            )));
        }
        let deciding_values = field_constraints
            .get(deciding_field)
            .map(|c| c.allowed_values.as_slice())
            .unwrap_or(&[]);

        for (deciding_value, narrowed) in table {
            if !deciding_values.is_empty() && !deciding_values.contains(deciding_value) {
                return Err(SpecError::Inconsistent(format!(
                    "{subject}.{field} 이(가) {deciding_field}={deciding_value} 일 때를 적었는데 \
                     {deciding_field} 는 그 값을 가질 수 없다"
                )));
            }
            for value in narrowed {
                if !constraint.allowed_values.is_empty()
                    && !constraint.allowed_values.contains(value)
                {
                    return Err(SpecError::Inconsistent(format!(
                        "{subject}.{field} 이(가) {deciding_field}={deciding_value} 일 때 \
                         {value} 를 허락하는데 그 값은 {field}.allowed_values 에 없다"
                    )));
                }
            }
        }
    }
    Ok(())
}

/// 명세를 읽다가 난 문제.
#[derive(Debug)]
pub enum SpecError {
    Read { path: String, source: std::io::Error },
    Parse(serde_norway::Error),
    Inconsistent(String),
}

impl fmt::Display for SpecError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            SpecError::Read { path, source } => {
                write!(f, "명세 파일을 읽지 못했다: {path} — {source}")
            }
            SpecError::Parse(source) => write!(f, "명세 파일의 형식이 맞지 않다: {source}"),
            SpecError::Inconsistent(detail) => {
                write!(f, "명세가 스스로 어긋난다: {detail}")
            }
        }
    }
}

impl std::error::Error for SpecError {
    fn source(&self) -> Option<&(dyn std::error::Error + 'static)> {
        match self {
            SpecError::Read { source, .. } => Some(source),
            SpecError::Parse(source) => Some(source),
            SpecError::Inconsistent(_) => None,
        }
    }
}
