//! **고른 Step 하나의 상세** — 초기 View 가 싣지 않은 해상도.
//!
//! [`super::view::MonitorViewV1`] 은 Graph 를 읽는 데 필요한 낮은 해상도만 나른다. 화면에
//! 한 번에 보이는 Report 는 **선택한 하나**뿐이므로, 나머지를 미리 실으면 값을 치르고 쓰지
//! 않는다. 그래서 상세는 따로, canonical `StepRef` 하나로 청한다.
//!
//! ```text
//! MonitorViewV1   낮은 해상도 — kind · state · 대표 칸 한 줄
//! NodeDetailV1    고른 하나 — 저장된 Report 전부
//! ```
//!
//! # 물러서지 않는다
//!
//! 청한 `StepRef` 가 가리키는 Cycle 과 Step 을 **정확히** 찾는다. 비슷한 번호나 다른 Cycle 의
//! 같은 Step 번호로 물러서지 않는다 — 물러서는 순간 화면은 묻지 않은 것을 답하게 된다.
//! 없으면 [`DetailError::NotFound`] 로 청한 주소를 그대로 담아 거절한다.
//!
//! # 읽기만 한다
//!
//! 세계를 다시 관측하지 않고, 새 Snapshot 을 만들지 않고, 아무것도 저장하지 않는다. 잠금도
//! [`ProjectSession`] 이 이미 쥔 것뿐이다 — 이 함수는 새로 잡지 않는다.

use serde::{Deserialize, Serialize};

use super::view::{NodeStateV1, SCHEMA_VERSION, StepKindV1};
use crate::refs::StepRef;
use crate::report::Report;
use crate::session::ProjectSession;

/// 고른 Step 하나의 사실.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct NodeDetailV1 {
    pub schema_version: u32,
    pub step_ref: String,
    /// **청한 Step 이 실제로 담긴 Cycle.** 청한 주소의 앞부분을 되풀이하는 것이 아니라,
    /// 찾아낸 Cycle 자신이 말하는 제 주소다.
    pub cycle_ref: String,
    pub kind: StepKindV1,
    pub state: NodeStateV1,
    /// 저장된 Report. **아직 닫히지 않았으면 없다.**
    pub report: Option<ReportV1>,
}

/// 저장된 Report 하나.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReportV1 {
    /// **이름순.** JSON object 의 key 차례에 기대지 않고 배열의 차례로 그 계약을 나른다.
    pub fields: Vec<ReportFieldV1>,
}

/// Report 의 칸 하나 — **원문 그대로.**
///
/// 이름도 값도 자르거나 옮기거나 고르지 않는다. 문법에 없는 칸이라도 검증된 Report 에
/// 있다면 제 이름으로 나온다 — 화면이 아는 것만 고르는 whitelist 를 두지 않는다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ReportFieldV1 {
    pub name: String,
    pub value: String,
}

/// 상세를 줄 수 없는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum DetailError {
    /// 이 Project 에 그 Step 이 없다.
    ///
    /// **청한 주소를 그대로 담는다.** 무엇을 물었는지가 답에 남아야 부르는 쪽이 제 실수와
    /// 프로젝트의 변화를 가를 수 있다.
    NotFound { step_ref: String },
}

impl std::fmt::Display for DetailError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            DetailError::NotFound { step_ref } => {
                write!(f, "{step_ref} 은 이 Project 에 없다")
            }
        }
    }
}

impl std::error::Error for DetailError {}

impl ProjectSession {
    /// 고른 Step 하나의 상세를 읽는다.
    ///
    /// # 어떻게 찾는가
    ///
    /// ```text
    /// cycles.nodes()  중에서 제 주소가 step.cycle() 과 같은 Cycle 하나
    ///   → cycle.steps().nodes()  중에서 제 주소가 step 과 같은 Node 하나
    /// ```
    ///
    /// 두 걸음 모두 **canonical 주소를 견주어** 찾는다. 번호를 계산하지도, 가까운 것을
    /// 고르지도 않는다. 어느 걸음에서든 없으면 그대로 거절한다.
    ///
    /// 검증된 domain graph 만 지난다 — `.gil/state.yaml` 을 직접 읽는 길은 여기 없다.
    pub fn node_detail_v1(&self, step: StepRef) -> Result<NodeDetailV1, DetailError> {
        let missing = || DetailError::NotFound {
            step_ref: step.to_string(),
        };
        let cycle = self
            .project()
            .cycles()
            .nodes()
            .iter()
            .find(|cycle| cycle.id().to_ref() == step.cycle())
            .ok_or_else(missing)?;
        let node = cycle
            .steps()
            .nodes()
            .iter()
            .find(|node| cycle.step_ref(node.id) == step)
            .ok_or_else(missing)?;
        // **경계는 조회하지 않는다.** 경계는 Step 이 아니므로 「그런 Step 이 없다」가
        // 정확한 답이다 — 다른 값으로 숨겨 상세를 지어내지 않는다.
        let kind = super::view::step_kind(node.kind).ok_or_else(missing)?;

        Ok(NodeDetailV1 {
            schema_version: SCHEMA_VERSION,
            // 찾아낸 것이 말하는 제 주소를 적는다.
            step_ref: cycle.step_ref(node.id).to_string(),
            cycle_ref: cycle.id().to_ref().to_string(),
            kind,
            state: super::view::state(node.status),
            // **없으면 없다.** 빈 Report 를 닫힌 Report 로 가장하지 않는다.
            report: node.report.as_ref().map(fields),
        })
    }
}

/// 저장된 Report 를 이름순 목록으로.
///
/// [`Report`] 의 canonical 차례가 이름순이고 삽입 순서는 어디에도 기록되지 않는다. 그래서
/// 여기서 정렬하지 않는다 — **원본의 차례를 그대로 옮긴다.**
fn fields(report: &Report) -> ReportV1 {
    ReportV1 {
        fields: report
            .field_names()
            .map(|name| ReportFieldV1 {
                name: name.to_string(),
                value: report.get(name).unwrap_or_default().to_string(),
            })
            .collect(),
    }
}
