//! Existence 와 Journey — **세계를 살아가는 쪽.**
//!
//! Cycle Graph 가 "여기는 어떤 곳인가" 를 답한다면, 여기는 "지금의 나는 누구인가" 를 답한다.
//! 두 축은 서로의 함수가 아니다(Time Model §3) — 그래서 같은 파일에 눕더라도 타입이 갈린다.
//!
//! ```text
//! Existence X1
//! └─ Journey
//!    └─ revisions
//!       └─ J0  existence_state_ref: state:ES0
//!              knowledge_head_ref:  null
//!              memory_head_ref:     null
//!              relations_head_ref:  null
//!              will_head_ref:       null
//! ```
//!
//! # 지금 있는 것은 뼈대뿐이다
//!
//! Knowledge·Memory·Relations·Will 은 **아직 짓지 않았다.** 그래서 head 는 `None` 으로만
//! 존재하고, 이 모듈에는 그 객체들의 타입이 없다 — 없는 것을 이름만 두면 읽는 쪽이 있다고
//! 믿는다. Journey revision 이 그 자리를 비워 둘 수 있다는 것은 명세가 허락한 것이다
//! (Existence Model §4: *"초기 revision 에서 아직 없는 Knowledge·Memory·Relations·Will head 만
//! `null` 일 수 있다"*).
//!
//! # Existence State 만은 비울 수 없다
//!
//! `existence_state_ref` 는 **모든 revision 에서 필수**다. Existence 가 생겼는데 State 가
//! 없다는 상태를 명세가 금지한다. 다만 그 State 의 내용 schema 는 아직 정해지지 않았으므로
//! ES0 은 **실재하는 빈 객체**다 — 성격·역할·전문성을 대신 채우지 않는다.

use std::collections::BTreeMap;

use crate::refs::{ExistenceRef, JourneyRef, KnowledgeRef, MemoryRef, RelationRef, StateRef, WillRef};
use crate::will::Will;

/// Existence State 하나.
///
/// **내용이 없다.** 무엇이 들어갈지는 아직 명세가 정하지 않았고, 여기서 발명하지 않는다.
/// 그래도 객체는 실재해야 한다 — J0 의 `existence_state_ref` 가 가리킬 자리가 필요하다.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Default)]
pub struct ExistenceState;

/// Journey 의 한 판 — 그 순간 확정된 자기 상태의 머리들.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Revision {
    /// **비울 수 없다.** 모든 revision 이 실재하는 State 를 가리킨다.
    existence_state: StateRef,
    /// 아직 짓지 않은 것들. 생기기 전까지 `None`.
    knowledge_head: Option<KnowledgeRef>,
    memory_head: Option<MemoryRef>,
    relations_head: Option<RelationRef>,
    will_head: Option<WillRef>,
}

impl Revision {
    /// 아무것도 쌓이지 않은 판. State 하나만 가리킨다.
    pub fn empty(state: StateRef) -> Revision {
        Revision {
            existence_state: state,
            knowledge_head: None,
            memory_head: None,
            relations_head: None,
            will_head: None,
        }
    }

    pub fn existence_state(&self) -> StateRef {
        self.existence_state
    }

    pub fn knowledge_head(&self) -> Option<KnowledgeRef> {
        self.knowledge_head
    }

    pub fn memory_head(&self) -> Option<MemoryRef> {
        self.memory_head
    }

    pub fn relations_head(&self) -> Option<RelationRef> {
        self.relations_head
    }

    pub fn will_head(&self) -> Option<WillRef> {
        self.will_head
    }

    /// 이 판의 머리를 **그대로 물려받고** Will 머리만 옮긴 다음 판.
    ///
    /// 실행형 Close 가 만드는 새 판이다(Existence Model §4). Knowledge·Memory·Relations·State
    /// 는 이번 transaction 에서 바뀐 것이 없으므로 **같은 것을 가리킨다** — 판이 하나 늘었다는
    /// 이유로 아직 짓지도 않은 머리를 새로 만들지 않는다.
    pub(crate) fn with_will_head(&self, will: WillRef) -> Revision {
        Revision {
            will_head: Some(will),
            ..self.clone()
        }
    }

    /// 저장이 읽어 온 값으로 다시 세운다.
    pub(crate) fn restore(
        existence_state: StateRef,
        knowledge_head: Option<KnowledgeRef>,
        memory_head: Option<MemoryRef>,
        relations_head: Option<RelationRef>,
        will_head: Option<WillRef>,
    ) -> Revision {
        Revision {
            existence_state,
            knowledge_head,
            memory_head,
            relations_head,
            will_head,
        }
    }
}

/// 한 Existence 가 살아온 판들.
///
/// revision 은 **확정된 내용이 바뀔 때만** 늘어난다(Existence Model §4). 지금 그것을 늘리는
/// 사건은 하나뿐이다 — 최초 Existence 와 빈 J0 의 생성.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Journey {
    /// **지금 하려는 하나의 행동.** 있으면 Active 다 — status 필드를 따로 두지 않는다.
    ///
    /// mutable register 다. 프로세스 경계는 넘지만 아직 immutable Timeline 에는 없다.
    active_will: Option<Will>,
    /// **끝낸 행동들, 끝낸 순서대로.** 여기 있으면 Done 이다.
    ///
    /// ref 목록이 아니라 **객체 목록**이다(Will Model §4). append 만 한다 — 지우지도,
    /// 사이에 끼워 넣지도, 고치지도 않는다.
    done_wills: Vec<Will>,
    revisions: BTreeMap<u32, Revision>,
}

impl Journey {
    /// 빈 초기 판 하나로 시작한다.
    pub(crate) fn start(state: StateRef) -> Journey {
        Journey {
            active_will: None,
            done_wills: Vec::new(),
            revisions: BTreeMap::from([(0, Revision::empty(state))]),
        }
    }

    /// 지금 하려는 행동. 없으면 **GIL 은 그것을 지어내지 않는다**(Will Model §10).
    pub fn active_will(&self) -> Option<&Will> {
        self.active_will.as_ref()
    }

    /// 끝낸 행동들 — 끝낸 순서대로.
    pub fn done_wills(&self) -> &[Will] {
        &self.done_wills
    }

    /// 마지막으로 끝낸 행동. `will_head_ref` 가 가리키는 자리다.
    pub fn last_done_will(&self) -> Option<&Will> {
        self.done_wills.last()
    }

    /// 아직 쓰지 않은 다음 판 번호.
    ///
    /// 지난 판은 지우지 않으므로 **가장 큰 번호 다음**이면 재사용이 없다. 따로 high-water
    /// mark 를 저장하지 않는다 — 두 자리에 적으면 한쪽이 낡는다.
    pub(crate) fn next_revision(&self) -> u32 {
        self.revisions.last_key_value().map_or(0, |(number, _)| number + 1)
    }

    /// 하려는 행동을 건다. **이미 걸려 있으면 부르는 쪽이 먼저 막는다.**
    pub(crate) fn set_active_will(&mut self, will: Will) {
        self.active_will = Some(will);
    }

    /// 걸려 있던 행동을 끝낸 것으로 옮긴다 — register 를 비우고 목록 끝에 붙인다.
    ///
    /// 옮기는 것이지 **베끼는 것이 아니다.** 같은 객체가 두 자리에 동시에 있으면
    /// 어느 쪽이 진짜인지 파일이 말하지 못한다.
    pub(crate) fn complete_active_will(&mut self) -> Option<WillRef> {
        let will = self.active_will.take()?;
        let id = will.id();
        self.done_wills.push(will);
        Some(id)
    }

    /// 새 판 하나를 얹고 그 번호를 돌려준다.
    pub(crate) fn push_revision(&mut self, revision: Revision) -> u32 {
        let number = self.next_revision();
        self.revisions.insert(number, revision);
        number
    }

    /// 그 번호의 판. 없으면 `None`.
    pub fn revision(&self, number: u32) -> Option<&Revision> {
        self.revisions.get(&number)
    }

    /// 번호순으로 전부.
    pub fn revisions(&self) -> impl Iterator<Item = (u32, &Revision)> {
        self.revisions.iter().map(|(number, rev)| (*number, rev))
    }

    pub(crate) fn restore(
        active_will: Option<Will>,
        done_wills: Vec<Will>,
        revisions: BTreeMap<u32, Revision>,
    ) -> Journey {
        Journey {
            active_will,
            done_wills,
            revisions,
        }
    }
}

/// 프로젝트 안에서 지속되는 행동 주체 하나.
///
/// **런타임 모델이나 세션이 아니다**(Existence Model §2). 같은 프로젝트를 여는 다른 모델과
/// 세션이 같은 `existence_ref` 를 읽으면 같은 Journey 를 이어받는다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Existence {
    id: ExistenceRef,
    /// 지금 서 있는 판. `id` 와 같은 Existence 를 가리킨다.
    current: JourneyRef,
    journey: Journey,
}

impl Existence {
    /// 최초 Existence 를 만든다 — 빈 State 하나와 빈 초기 판 J0.
    pub(crate) fn start(id: ExistenceRef, state: StateRef) -> Existence {
        Existence {
            id,
            current: JourneyRef::new(id, 0),
            journey: Journey::start(state),
        }
    }

    pub fn id(&self) -> ExistenceRef {
        self.id
    }

    /// 지금 이 Existence 가 서 있는 Journey 판.
    pub fn current_journey(&self) -> JourneyRef {
        self.current
    }

    pub fn journey(&self) -> &Journey {
        &self.journey
    }

    /// 지금 이 존재가 하려는 행동.
    pub fn active_will(&self) -> Option<&Will> {
        self.journey.active_will()
    }

    /// Journey 를 고친다 — **[`Project`](crate::Project) 의 transaction 안에서만.**
    ///
    /// 판을 올리는 것과 Will 을 옮기는 것과 Node 를 닫는 것이 한 save 에 들어가야 하므로,
    /// 이 문은 그 transaction 을 조립하는 자리에만 열어 둔다.
    pub(crate) fn journey_mut(&mut self) -> &mut Journey {
        &mut self.journey
    }

    /// 서 있는 판을 옮긴다. 새 판을 얹은 **직후에만** 부른다.
    pub(crate) fn stand_at(&mut self, journey: JourneyRef) {
        self.current = journey;
    }

    /// 지금 판의 내용. 복원 검사를 통과한 상태에서는 언제나 있다.
    pub fn current_revision(&self) -> Option<&Revision> {
        self.journey.revision(self.current.revision())
    }

    pub(crate) fn restore(id: ExistenceRef, current: JourneyRef, journey: Journey) -> Existence {
        Existence {
            id,
            current,
            journey,
        }
    }
}
