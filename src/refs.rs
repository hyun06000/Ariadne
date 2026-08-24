//! Typed reference — **가리키는 값이 제 종류를 스스로 말한다.**
//!
//! `gil-spec.yaml` 이 규칙을 갖듯, 주소의 규칙은 `GIL Node Model v0.1` §2.1 이 갖는다.
//! 여기 있는 것은 그 문법을 읽고 쓰는 절차뿐이다.
//!
//! ```text
//! chain:C1         cycle:C2          step:C2/S3
//! existence:X1     journey:X1@J7     participant:U1
//! relation:R1      will:W4           state:ES3
//! knowledge:K18    memory:M11        snapshot:A1
//! ```
//!
//! # 왜 종류를 값에 넣는가
//!
//! bare `C2` 는 **무엇의 2번인지 말하지 않는다.** Chain 도 Cycle 도 `C` 를 쓰고, Step 의
//! `S3` 은 어느 Cycle 의 3번인지 말하지 않는다. 종류가 빠진 주소는 읽는 쪽이 문맥으로
//! 짐작해야 하고, 짐작이 어긋나는 순간 **다른 Node 를 가리키면서도 성공한다** — 옛 도구가
//! 커밋 트레일러를 스키마로 쓰다 물린 상처와 구조가 같다.
//!
//! `#3` 은 현재 Cycle 이 자명한 화면에서만 쓰는 **인간용 축약**이다. 저장·Report 의 구조적
//! 참조·API 입력에는 오지 않는다([`RefSyntaxError::NoKind`] 가 그것을 거절한다).
//!
//! # 서로 대입되지 않는다
//!
//! 열두 종류가 **각자 다른 타입**이다. 같은 수를 담아도 [`CycleRef`] 를 [`ChainRef`] 자리에
//! 넣을 수 없다 — 둘 다 `C` 를 쓰기 때문에 문자열로 두면 조용히 섞인다. 종류 사이를 오가는
//! `From` 도 두지 않는다.
//!
//! # 아직 아무 데도 연결하지 않았다
//!
//! 저장([`store`](crate::store))도 CLI 도 Report parser 도 아직 bare 수를 쓴다. 이 모듈은
//! **그것들과 무관하게 혼자 선다** — 주소 문법을 먼저 못 박고, 옮겨 붙이는 것은 다음 걸음의
//! 몫이다. 그래서 여기에는 `Serialize` 도 달지 않는다(달면 그 순간 저장 형식이 된다).

use std::fmt;
use std::str::FromStr;

/// 이 크레이트가 아는 종류 이름 전부.
///
/// 모르는 이름과 **다른 종류의 이름**을 갈라 말하기 위해 여기 한 벌 둔다 — `cycle:C2` 를
/// [`ChainRef`] 로 읽으려 한 사람에게 "모르는 종류다" 라고 답하면 무엇이 틀렸는지 모른다.
const KINDS: [&str; 12] = [
    "chain",
    "cycle",
    "step",
    "existence",
    "journey",
    "participant",
    "relation",
    "will",
    "state",
    "knowledge",
    "memory",
    "snapshot",
];

/// 적어 준 글이 주소로 읽히지 않는 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RefSyntaxError {
    /// 빈 글이다.
    Empty,
    /// 종류가 없다 — bare `C2`·`S3`·`#3` 은 영구 reference 가 아니다.
    NoKind { text: String },
    /// 이 크레이트가 모르는 종류다.
    UnknownKind { kind: String },
    /// 아는 종류지만 이 자리에 올 것이 아니다.
    WrongKind {
        expected: &'static str,
        found: String,
    },
    /// 이름의 글자가 그 종류의 것이 아니다.
    WrongLetter {
        expected: &'static str,
        text: String,
    },
    /// 복합 주소의 모양이 아니다.
    Shape {
        expected: &'static str,
        text: String,
    },
    /// 수가 비어 있다.
    EmptyNumber { text: String },
    /// 십진수가 아니다 — 음수·기호·다른 글자.
    NotANumber { text: String },
    /// 선행 0 은 canonical 이 아니다.
    LeadingZero { text: String },
    /// 이 종류는 0 을 이름으로 쓰지 않는다.
    ZeroNotAllowed { text: String },
    /// 빈칸이 섞였다.
    Whitespace { text: String },
}

impl fmt::Display for RefSyntaxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RefSyntaxError::Empty => write!(f, "빈 글은 주소가 아니다"),
            RefSyntaxError::NoKind { text } => write!(
                f,
                "{text:?} 에는 종류가 없다 — 영구 reference 는 `cycle:C2` 처럼 종류를 지닌다.\n\
                 `#3` 같은 축약은 현재 Cycle 이 자명한 화면에서만 쓴다"
            ),
            RefSyntaxError::UnknownKind { kind } => {
                write!(f, "{kind:?} 는 gil 이 아는 종류가 아니다 — 아는 것: {}", KINDS.join(", "))
            }
            RefSyntaxError::WrongKind { expected, found } => {
                write!(f, "여기는 {expected} 의 자리인데 {found:?} 를 적었다")
            }
            RefSyntaxError::WrongLetter { expected, text } => {
                write!(f, "{text:?} 는 {expected:?} 로 시작해야 한다")
            }
            RefSyntaxError::Shape { expected, text } => {
                write!(f, "{text:?} 는 {expected} 꼴이 아니다")
            }
            RefSyntaxError::EmptyNumber { text } => write!(f, "{text:?} 에 수가 없다"),
            RefSyntaxError::NotANumber { text } => {
                write!(f, "{text:?} 의 수 자리가 십진수가 아니다")
            }
            RefSyntaxError::LeadingZero { text } => {
                write!(f, "{text:?} 는 선행 0 을 지녔다 — 같은 것을 두 가지로 적게 된다")
            }
            RefSyntaxError::ZeroNotAllowed { text } => write!(
                f,
                "{text:?} 는 0 을 쓸 수 없는 종류다 — 0 은 초기 revision(J0)과 초기 \
                 Existence State(ES0)의 것이다"
            ),
            RefSyntaxError::Whitespace { text } => {
                write!(f, "{text:?} 에 빈칸이 섞였다")
            }
        }
    }
}

impl std::error::Error for RefSyntaxError {}

/// 앞머리의 종류를 떼고 **몸통만** 돌려준다.
///
/// 여기서 세 가지를 본다: 비었는가 · 빈칸이 섞였는가 · 종류가 이 자리의 것인가.
/// 몸통을 어떻게 읽을지는 부르는 쪽이 안다(단순한 이름인지 복합 주소인지가 다르다).
fn body_of<'a>(text: &'a str, expected: &'static str) -> Result<&'a str, RefSyntaxError> {
    if text.is_empty() {
        return Err(RefSyntaxError::Empty);
    }
    // 빈칸은 어디에 있든 거절한다. 양끝을 다듬어 받으면 같은 주소가 여러 글자꼴을 갖는다.
    if text.chars().any(char::is_whitespace) {
        return Err(RefSyntaxError::Whitespace {
            text: text.to_string(),
        });
    }

    let Some((kind, body)) = text.split_once(':') else {
        return Err(RefSyntaxError::NoKind {
            text: text.to_string(),
        });
    };
    if kind == expected {
        return Ok(body);
    }
    match KINDS.contains(&kind) {
        true => Err(RefSyntaxError::WrongKind {
            expected,
            found: text.to_string(),
        }),
        false => Err(RefSyntaxError::UnknownKind {
            kind: kind.to_string(),
        }),
    }
}

/// `C2` 처럼 **글자 + 수** 하나를 읽는다.
///
/// 수의 규칙은 명세가 정한다(§2.1): ASCII 십진수의 canonical 표기만, 선행 0 없음,
/// 0 은 `J0`·`ES0` 에만.
fn id_of(text: &str, letter: &'static str, zero_allowed: bool) -> Result<u32, RefSyntaxError> {
    let Some(digits) = text.strip_prefix(letter) else {
        return Err(RefSyntaxError::WrongLetter {
            expected: letter,
            text: text.to_string(),
        });
    };
    if digits.is_empty() {
        return Err(RefSyntaxError::EmptyNumber {
            text: text.to_string(),
        });
    }
    // 음수도, `+1` 도, 다른 문자 체계의 숫자도 여기서 걸린다.
    if !digits.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err(RefSyntaxError::NotANumber {
            text: text.to_string(),
        });
    }
    if digits.len() > 1 && digits.starts_with('0') {
        return Err(RefSyntaxError::LeadingZero {
            text: text.to_string(),
        });
    }

    let number: u32 = digits.parse().map_err(|_| RefSyntaxError::NotANumber {
        text: text.to_string(),
    })?;
    if number == 0 && !zero_allowed {
        return Err(RefSyntaxError::ZeroNotAllowed {
            text: text.to_string(),
        });
    }
    Ok(number)
}

/// 글자 하나와 수 하나로 이루어진 종류들.
///
/// 열 종류가 같은 규칙을 따르므로 한 자리에 적는다 — 손으로 열 번 옮겨 적으면 언젠가
/// 한 벌이 낡는다.
macro_rules! simple_refs {
    ($(
        $(#[$doc:meta])*
        $name:ident = $kind:literal $letter:literal $zero:literal;
    )*) => {$(
        $(#[$doc])*
        #[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
        pub struct $name(u32);

        impl $name {
            /// reference 앞머리에 적히는 종류의 이름.
            pub const KIND: &'static str = $kind;
            /// 이 종류의 이름이 시작하는 글자.
            pub const LETTER: &'static str = $letter;
            /// 0 을 이름으로 쓸 수 있는가.
            pub const ZERO_ALLOWED: bool = $zero;

            /// 수 하나로 만든다. 이 종류가 쓰지 않는 0 이면 `None`.
            pub fn new(number: u32) -> Option<Self> {
                match number == 0 && !Self::ZERO_ALLOWED {
                    true => None,
                    false => Some($name(number)),
                }
            }

            /// 이름의 수.
            pub fn number(self) -> u32 {
                self.0
            }

            /// **종류 없는 이름** — `C2` 처럼. 객체 자신의 `id` 칸과 복합 주소의 안쪽이 쓴다
            /// (명세 §2.1: 자신의 `id` 는 bare, 남을 가리키는 칸만 prefix 를 지닌다).
            pub fn id(self) -> String {
                format!("{}{}", Self::LETTER, self.0)
            }
        }

        impl fmt::Display for $name {
            fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
                write!(f, "{}:{}{}", Self::KIND, Self::LETTER, self.0)
            }
        }

        impl FromStr for $name {
            type Err = RefSyntaxError;

            fn from_str(text: &str) -> Result<Self, Self::Err> {
                let body = body_of(text, Self::KIND)?;
                // 종류만 있고 이름이 없는 `cycle:` — 글자가 틀린 것이 아니라 아예 없다.
                if body.is_empty() {
                    return Err(RefSyntaxError::EmptyNumber { text: text.to_string() });
                }
                Ok($name(id_of(body, Self::LETTER, Self::ZERO_ALLOWED)?))
            }
        }
    )*};
}

simple_refs! {
    /// `chain:C1` — Chain 하나. 프로젝트 전체에서 유일하다.
    ChainRef = "chain" "C" false;

    /// `cycle:C2` — Cycle 하나. 프로젝트 전체에서 유일하므로 Chain 경로를 앞에 붙이지 않는다.
    CycleRef = "cycle" "C" false;

    /// `existence:X1` — 프로젝트 안에서 지속되는 행동 주체.
    ExistenceRef = "existence" "X" false;

    /// `participant:U1` — 프로젝트를 함께 만드는 참여자.
    ParticipantRef = "participant" "U" false;

    /// `relation:R1` — 참여자 사이의 관계.
    RelationRef = "relation" "R" false;

    /// `will:W4` — 지금 수행하려는 행동 한 단위. **프로젝트 전체에서 유일하다** — 한
    /// Existence 의 Journey 안에 살더라도 다른 Existence 의 Will 과 이름을 나눠 쓰지 않는다.
    WillRef = "will" "W" false;

    /// `state:ES3` — Existence State 한 판. 초기 상태가 `ES0` 이라 0 을 쓴다.
    StateRef = "state" "ES" true;

    /// `knowledge:K18` — Knowledge head.
    KnowledgeRef = "knowledge" "K" false;

    /// `memory:M11` — Memory head.
    MemoryRef = "memory" "M" false;

    /// `snapshot:A1` — Artifact snapshot 하나.
    SnapshotRef = "snapshot" "A" false;
}

/// `step:C2/S3` — 어느 Cycle 의 몇 번째 Step 인가.
///
/// Step 의 이름은 **소속 Cycle 안에서만** 유일하다. 그래서 Cycle 을 함께 지니지 않은 Step
/// 주소는 성립하지 않는다 — `C1` 의 `S3` 과 `C2` 의 `S3` 은 다른 Node 다.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct StepRef {
    cycle: CycleRef,
    step: u32,
}

impl StepRef {
    pub const KIND: &'static str = "step";
    /// Step 이름이 시작하는 글자.
    pub const LETTER: &'static str = "S";
    /// Step 은 1 부터 센다.
    pub const ZERO_ALLOWED: bool = false;

    /// Cycle 과 Step 번호로 조립한다. 0 번 Step 은 없으므로 그때는 `None`.
    pub fn new(cycle: CycleRef, step: u32) -> Option<StepRef> {
        match step == 0 {
            true => None,
            false => Some(StepRef { cycle, step }),
        }
    }

    /// 이 Step 이 담긴 Cycle.
    pub fn cycle(self) -> CycleRef {
        self.cycle
    }

    /// Cycle 안에서의 번호.
    pub fn step(self) -> u32 {
        self.step
    }

    /// **종류 없는 이름** — `S3` 처럼. 객체 자신의 `id` 칸이 쓴다.
    pub fn id(self) -> String {
        format!("{}{}", Self::LETTER, self.step)
    }
}

impl fmt::Display for StepRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:{}/{}", Self::KIND, self.cycle.id(), self.id())
    }
}

impl FromStr for StepRef {
    type Err = RefSyntaxError;

    fn from_str(text: &str) -> Result<Self, Self::Err> {
        let body = body_of(text, Self::KIND)?;
        let shape = RefSyntaxError::Shape {
            expected: "step:<cycle>/<step>",
            text: text.to_string(),
        };

        let Some((cycle, step)) = body.split_once('/') else {
            return Err(shape);
        };
        // 조각이 셋 이상이면 어느 것이 Step 인지 정해지지 않는다.
        if step.contains('/') {
            return Err(shape);
        }

        Ok(StepRef {
            cycle: CycleRef(id_of(cycle, CycleRef::LETTER, CycleRef::ZERO_ALLOWED)?),
            step: id_of(step, Self::LETTER, Self::ZERO_ALLOWED)?,
        })
    }
}

/// `journey:X1@J7` — 어느 Existence 의 몇 번째 Journey revision 인가.
///
/// revision 은 그 Existence 안에서만 뜻이 있다. 그래서 Existence 를 함께 지닌다.
/// 빈 초기 revision 이 `J0` 이라 revision 만 0 을 쓴다.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct JourneyRef {
    existence: ExistenceRef,
    revision: u32,
}

impl JourneyRef {
    pub const KIND: &'static str = "journey";
    /// revision 이름이 시작하는 글자.
    pub const LETTER: &'static str = "J";
    /// 빈 초기 revision 이 `J0` 이다.
    pub const ZERO_ALLOWED: bool = true;

    /// Existence 와 revision 번호로 조립한다.
    pub fn new(existence: ExistenceRef, revision: u32) -> JourneyRef {
        JourneyRef {
            existence,
            revision,
        }
    }

    /// 이 Journey 를 소유한 Existence.
    pub fn existence(self) -> ExistenceRef {
        self.existence
    }

    /// 그 Existence 안에서의 revision 번호.
    pub fn revision(self) -> u32 {
        self.revision
    }

    /// **종류 없는 이름** — `X1@J7` 처럼.
    pub fn id(self) -> String {
        format!("{}@{}{}", self.existence.id(), Self::LETTER, self.revision)
    }
}

impl fmt::Display for JourneyRef {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:{}", Self::KIND, self.id())
    }
}

impl FromStr for JourneyRef {
    type Err = RefSyntaxError;

    fn from_str(text: &str) -> Result<Self, Self::Err> {
        let body = body_of(text, Self::KIND)?;
        let shape = RefSyntaxError::Shape {
            expected: "journey:<existence>@<revision>",
            text: text.to_string(),
        };

        let Some((existence, revision)) = body.split_once('@') else {
            return Err(shape);
        };
        if revision.contains('@') {
            return Err(shape);
        }

        Ok(JourneyRef {
            existence: ExistenceRef(id_of(
                existence,
                ExistenceRef::LETTER,
                ExistenceRef::ZERO_ALLOWED,
            )?),
            revision: id_of(revision, Self::LETTER, Self::ZERO_ALLOWED)?,
        })
    }
}
