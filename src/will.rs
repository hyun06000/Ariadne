//! Will — **지금 무엇을 하려는가.**
//!
//! Context 가 "지금 무엇이 참인가" 를 말한다면 Will 은 "지금 무엇을 하려는가" 를 말한다
//! (Will Model §14). 둘을 가르는 까닭은 실사용에서 값을 치렀기 때문이다 — `gil context` 로
//! 상태와 가설을 정확히 복원한 Agent 가, **열린 Verify 에서 무엇을 먼저 해야 하는지**
//! 몰라 검증하기도 전에 `gil close` 를 눌렀다(Roadmap M2C).
//!
//! ```text
//! Context   Cycle 2 의 Verify 가 열려 있다. 가설은 HTTP(S) 검사다.
//! Will      비HTTP 입력 테스트를 실행해 실패를 관측한다.   ← 이것이 없었다
//! Grammar   Report 가 준비되면 gil close 로 닫는다.
//! ```
//!
//! # GIL 이 지어내지 않는다
//!
//! Node Kind 만 보고 구체적인 Will 을 만들지 않는다(Will Model §7). `question` 이라는 이름은
//! *무엇을* 물을지 모른다. 그래서 세 칸은 **Agent 가 `gil open` 의 stdin 으로 명시한다** —
//! 그것이 [`ActionContract`] 다. 문법은 Close Report 와 같은 field parser 를 쓰지만,
//! 이것은 Close Report 가 아니라 **행동 계약**이다.
//!
//! # status 를 저장하지 않는다
//!
//! Active 인지 Done 인지는 필드가 아니라 **저장된 자리**가 말한다(Will Model §4).
//! Journey 의 `active_will` register 에 있으면 Active, `done_wills` 목록에 있으면 Done 이다.
//! 같은 사실을 두 자리에 적으면 한쪽이 낡는다.

use std::fmt;

use crate::refs::{ExistenceRef, StepRef, WillRef};
use crate::report::Report;

/// 무엇을 이루려는가.
pub const OBJECTIVE: &str = "objective";
/// 지금 실제 세계에서 가장 먼저 할 행동. **GIL 명령만 적어서는 안 된다.**
pub const NEXT_ACTION: &str = "next_action";
/// 완료를 판정할 관측 가능한 조건.
pub const DONE_WHEN: &str = "done_when";

/// 행동 계약의 세 칸 — 적는 순서 그대로.
pub const CONTRACT_FIELDS: [&str; 3] = [OBJECTIVE, NEXT_ACTION, DONE_WHEN];

/// Agent 가 `gil open` 의 stdin 으로 적어 준 세 칸.
///
/// 아직 이름도 target 도 없다 — 그 둘은 **Node 를 여는 그 transaction 이** 정한다
/// (Will Model §4 「원자적 Open 으로 둘의 관계가 고정되므로」).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActionContract {
    objective: String,
    next_action: String,
    done_when: String,
}

impl ActionContract {
    /// 세 칸을 그대로 받는다. 시험과 host 가 쓰는 문.
    pub fn new(
        objective: impl Into<String>,
        next_action: impl Into<String>,
        done_when: impl Into<String>,
    ) -> ActionContract {
        ActionContract {
            objective: objective.into(),
            next_action: next_action.into(),
            done_when: done_when.into(),
        }
    }

    /// 사람이 적어 준 글에서 읽는다.
    ///
    /// **셋 다 있어야 하고 셋 다 비어 있을 수 없다.** 빠진 것과 비운 것을 따로 세지 않는다 —
    /// 어느 쪽이든 사람이 할 일은 하나다: 그 칸을 적어라.
    pub fn from_report(report: &Report) -> Result<ActionContract, ContractError> {
        let missing: Vec<&'static str> = CONTRACT_FIELDS
            .into_iter()
            .filter(|field| {
                report
                    .get(field)
                    .is_none_or(|value| value.trim().is_empty())
            })
            .collect();
        if !missing.is_empty() {
            return Err(ContractError::Missing { fields: missing });
        }
        Ok(ActionContract::new(
            report.get(OBJECTIVE).expect("방금 있는 것을 봤다"),
            report.get(NEXT_ACTION).expect("방금 있는 것을 봤다"),
            report.get(DONE_WHEN).expect("방금 있는 것을 봤다"),
        ))
    }

    /// 이 계약을 실제 Will 로 만든다 — 이름과 target 이 붙는 자리.
    pub(crate) fn into_will(
        self,
        id: WillRef,
        existence: ExistenceRef,
        target: StepRef,
    ) -> Will {
        Will {
            id,
            existence,
            target,
            objective: self.objective,
            next_action: self.next_action,
            done_when: self.done_when,
        }
    }
}

/// 행동 한 단위.
///
/// Done 이 되면 **바뀌지 않는다**(Will Model §6). 그래서 여기에는 고치는 문이 없다 —
/// Active 인 동안의 덮어쓰기는 register 를 통째로 갈아 끼우는 것이지 필드를 고치는 것이
/// 아니다. v0 의 traversal CLI 에는 그 덮어쓰기 명령조차 두지 않는다(Will Model §7).
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Will {
    id: WillRef,
    existence: ExistenceRef,
    target: StepRef,
    objective: String,
    next_action: String,
    done_when: String,
}

impl Will {
    pub fn id(&self) -> WillRef {
        self.id
    }

    /// 이 Will 을 가진 지속적 Existence.
    pub fn existence(&self) -> ExistenceRef {
        self.existence
    }

    /// 이 Will 과 함께 열린 실행형 Node.
    pub fn target(&self) -> StepRef {
        self.target
    }

    pub fn objective(&self) -> &str {
        &self.objective
    }

    pub fn next_action(&self) -> &str {
        &self.next_action
    }

    pub fn done_when(&self) -> &str {
        &self.done_when
    }

    /// 저장이 읽어 온 값으로 다시 세운다.
    pub(crate) fn restore(
        id: WillRef,
        existence: ExistenceRef,
        target: StepRef,
        objective: String,
        next_action: String,
        done_when: String,
    ) -> Will {
        Will {
            id,
            existence,
            target,
            objective,
            next_action,
            done_when,
        }
    }
}

/// 행동 계약을 읽지 못한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ContractError {
    /// 비어 있거나 아예 없는 칸이 있다.
    Missing { fields: Vec<&'static str> },
}

impl fmt::Display for ContractError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ContractError::Missing { fields } => write!(
                f,
                "행동 계약에 {} 이(가) 없다 — 실행형 Node 는 무엇을 하려는지 적지 않고 \
                 열지 않는다.\n\
                 GIL 은 Node 종류만 보고 그 내용을 지어내지 않는다.",
                fields.join(", ")
            ),
        }
    }
}

impl std::error::Error for ContractError {}
