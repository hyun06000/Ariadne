//! `gil-spec.yaml` 을 읽어 담는 자리.
//!
//! **규칙은 코드가 아니라 이 파일이 갖는다.** 여기 있는 것은 그 파일을 읽고, 스스로
//! 앞뒤가 맞는지 확인하는 일뿐이다.

use std::collections::BTreeMap;
use std::fmt;
use std::fs;
use std::path::Path;

use serde::Deserialize;

use crate::node::NodeKind;

/// 한 Step Kind 의 규칙.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StepRules {
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

/// 한 Report 칸의 값에 걸리는 제약.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct FieldConstraint {
    /// 이 칸이 가질 수 있는 값 전부. 비어 있으면 값을 열거하지 않는다는 뜻이다.
    #[serde(default)]
    pub allowed_values: Vec<String>,
    /// 참이면 빈 값(공백뿐인 값 포함)으로는 닫을 수 없다.
    #[serde(default)]
    pub non_empty: bool,
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
}

/// `gil-spec.yaml` 한 벌.
#[derive(Debug, Clone, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct RuleSet {
    step_kinds: BTreeMap<NodeKind, StepRules>,
}

impl RuleSet {
    /// 문자열에서 읽는다. 읽고 나서 스스로 앞뒤가 맞는지 확인한다.
    pub fn from_yaml_str(yaml: &str) -> Result<Self, SpecError> {
        let set: RuleSet = serde_norway::from_str(yaml).map_err(SpecError::Parse)?;
        set.check_symmetry()?;
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

    /// 이 Kind 의 규칙. 명세에 없는 Kind(경계 표식 등)면 `None`.
    pub fn rules(&self, kind: NodeKind) -> Option<&StepRules> {
        self.step_kinds.get(&kind)
    }

    /// 명세가 이 Kind 를 Step Kind 로 선언했는가.
    pub fn declares(&self, kind: NodeKind) -> bool {
        self.step_kinds.contains_key(&kind)
    }

    /// 선언된 Step Kind 전부(이름순).
    pub fn step_kinds(&self) -> impl Iterator<Item = (NodeKind, &StepRules)> {
        self.step_kinds.iter().map(|(k, v)| (*k, v))
    }

    /// 이 부모 뒤에 열 수 있다고 명세가 말하는 자식들.
    ///
    /// 부모가 선언된 Kind 면 그 `allowed_children` 이고, 경계 표식이면 자신을
    /// `allowed_parents` 에 적어 둔 Kind 들이다. 거절 메시지가 갈 곳을 말할 수 있게 쓴다.
    pub fn allowed_children_of(&self, parent: NodeKind) -> Vec<NodeKind> {
        match self.rules(parent) {
            Some(rules) => rules.allowed_children.clone(),
            None => self
                .step_kinds()
                .filter(|(_, rules)| rules.allowed_parents.contains(&parent))
                .map(|(kind, _)| kind)
                .collect(),
        }
    }

    /// 부모 쪽 선언과 자식 쪽 선언이 서로 어긋나지 않는지 본다.
    ///
    /// 한 변을 두 자리에 적는 구조라 한쪽만 고치면 조용히 갈린다. 그래서 읽을 때 센다.
    fn check_symmetry(&self) -> Result<(), SpecError> {
        for (parent, rules) in self.step_kinds() {
            for child in &rules.allowed_children {
                // 선언되지 않은 Kind(경계 표식)는 제 쪽 목록이 없으니 대조할 것이 없다.
                if let Some(child_rules) = self.rules(*child)
                    && !child_rules.allowed_parents.contains(&parent)
                {
                    return Err(SpecError::Inconsistent(format!(
                        "{parent}.allowed_children 에 {child} 가 있는데 \
                         {child}.allowed_parents 에는 {parent} 가 없다"
                    )));
                }
            }
            for grandparent in &rules.allowed_parents {
                if let Some(parent_rules) = self.rules(*grandparent)
                    && !parent_rules.allowed_children.contains(&parent)
                {
                    return Err(SpecError::Inconsistent(format!(
                        "{parent}.allowed_parents 에 {grandparent} 가 있는데 \
                         {grandparent}.allowed_children 에는 {parent} 가 없다"
                    )));
                }
            }
        }
        Ok(())
    }

    /// 값 제약이 **실재하는 칸**을 가리키는지 본다.
    ///
    /// `close_requires` 에 없는 칸에 제약을 걸면 그 제약은 한 번도 발동하지 않는다 —
    /// 걸어 둔 사람은 걸렸다고 믿는다. 조용히 안 도는 규칙은 없는 규칙보다 나쁘다.
    fn check_constraints_point_at_real_fields(&self) -> Result<(), SpecError> {
        for (kind, rules) in self.step_kinds() {
            for (field, constraint) in &rules.field_constraints {
                if !rules.close_requires.contains(field) {
                    return Err(SpecError::Inconsistent(format!(
                        "{kind}.field_constraints 가 {field} 에 값 제약을 걸었는데 \
                         {kind}.close_requires 에는 {field} 가 없다"
                    )));
                }
                if constraint.allowed_values.is_empty()
                    && !constraint.non_empty
                    && constraint.allowed_values_when.is_empty()
                {
                    return Err(SpecError::Inconsistent(format!(
                        "{kind}.field_constraints 의 {field} 가 아무것도 제약하지 않는다"
                    )));
                }
                self.check_narrowing(kind, field, constraint, rules)?;
            }
        }
        Ok(())
    }

    /// 값을 좁히는 표가 실재하는 칸과 실재하는 값을 가리키는지 본다.
    fn check_narrowing(
        &self,
        kind: NodeKind,
        field: &str,
        constraint: &FieldConstraint,
        rules: &StepRules,
    ) -> Result<(), SpecError> {
        for (deciding_field, table) in &constraint.allowed_values_when {
            if !rules.close_requires.contains(deciding_field) {
                return Err(SpecError::Inconsistent(format!(
                    "{kind}.{field} 의 허용값을 {deciding_field} 가 가르는데 \
                     {kind}.close_requires 에 {deciding_field} 가 없다 — 가를 값이 늘 비어 있다"
                )));
            }
            let deciding_values = rules
                .field_constraints
                .get(deciding_field)
                .map(|c| c.allowed_values.as_slice())
                .unwrap_or(&[]);

            for (deciding_value, narrowed) in table {
                if !deciding_values.is_empty() && !deciding_values.contains(deciding_value) {
                    return Err(SpecError::Inconsistent(format!(
                        "{kind}.{field} 이(가) {deciding_field}={deciding_value} 일 때를 적었는데 \
                         {deciding_field} 는 그 값을 가질 수 없다"
                    )));
                }
                for value in narrowed {
                    if !constraint.allowed_values.is_empty()
                        && !constraint.allowed_values.contains(value)
                    {
                        return Err(SpecError::Inconsistent(format!(
                            "{kind}.{field} 이(가) {deciding_field}={deciding_value} 일 때 \
                             {value} 를 허락하는데 그 값은 {field}.allowed_values 에 없다"
                        )));
                    }
                }
            }
        }
        Ok(())
    }
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
