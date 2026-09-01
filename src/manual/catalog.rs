//! 함께 실린 Topic 의 **주소 정본.**
//!
//! 주소 문자열이 사는 자리는 여기 하나다. 이것을 쓰는 자리는 둘이고, **서로 다른 물음에
//! 답한다.**
//!
//! ```text
//! Refusal Router    거절당했다 — 무엇을 읽어야 하는가
//! Action Guidance   밟을 수 있다 — 어떻게 하는가
//! ```
//!
//! 두 물음이 다르니 판정 함수는 나뉜 채로 둔다. 그러나 **주소는 나누지 않는다** — 같은
//! 글자를 두 파일에 적으면 Topic 을 옮긴 날 한쪽만 고쳐지고, 그 화면은 없는 문서를
//! 가리킨 채 조용히 산다.
//!
//! 주소를 글자로 들고 다니지 않고 이 enum 으로 다니는 까닭도 같다. 부르는 쪽이 임의의
//! 글자를 [`TopicId`] 로 만들 수 있으면 실리지 않은 주소가 화면에 나타날 수 있다.

use super::TopicId;

/// **코드가 가리키는** 함께 실린 Topic 하나.
///
/// 여기 없는 Topic 이 없다는 뜻이 아니다 — Topic 사이의 `related`·`examples` 링크는
/// Manual 자신이 구성할 때 검사한다. 이 목록이 담는 것은 **Rust 코드가 주소로 가리키는
/// 것들**이고, 그것들만이 코드와 문서가 따로 낡을 수 있는 자리다.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Bundled {
    VerifyClose,
    Restore,
    DirtyNonVerify,
    OpenContract,
    ExperimentClose,
    CycleRevisit,
    RevisitTarget,
}

impl Bundled {
    /// 전부 — Router 와 Action Guidance 가 가리키는 것을 **함께** 훑기 위한 목록.
    #[cfg(test)]
    pub(crate) const ALL: [Bundled; 7] = [
        Bundled::VerifyClose,
        Bundled::Restore,
        Bundled::DirtyNonVerify,
        Bundled::OpenContract,
        Bundled::ExperimentClose,
        Bundled::CycleRevisit,
        Bundled::RevisitTarget,
    ];

    /// canonical 주소.
    pub(crate) fn address(self) -> &'static str {
        match self {
            Bundled::VerifyClose => "step/verify/close",
            Bundled::Restore => "artifact/restore",
            Bundled::DirtyNonVerify => "artifact/dirty/non-verify",
            Bundled::OpenContract => "action/open-contract",
            Bundled::ExperimentClose => "cycle/experiment/close",
            Bundled::CycleRevisit => "cycle/revisit",
            Bundled::RevisitTarget => "cycle/revisit/target",
        }
    }

    /// 그 주소의 typed 값.
    ///
    /// **여기서만 판다.** 정본이 canonical 이 아니면 그것은 이 파일의 잘못이고, 시험이
    /// 먼저 잡는다 — 사용자가 적은 글자를 읽는 [`TopicId::parse`] 와는 다른 자리다.
    pub(crate) fn id(self) -> TopicId {
        TopicId::parse(self.address()).expect("정본 주소는 canonical 이다")
    }
}
