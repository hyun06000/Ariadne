//! Typed reference — **주소가 제 종류를 말하는가.**
//!
//! 재는 것은 셋이다.
//!
//! 1. 명세가 적어 둔 꼴이 **글자 그대로** 왕복하는가([`GIL Node Model v0.1` §2.1]).
//! 2. 종류가 없거나 다른 종류인 값을 거절하는가.
//! 3. 수가 canonical 이 아닌 값을 거절하는가.
//!
//! 여기서 문구를 재지 않는다. 거절의 **이유**는 무엇이 틀렸는지 사람이 알아야 하므로 종류만
//! 확인하고, 문장은 확인하지 않는다.
//!
//! [`GIL Node Model v0.1` §2.1]: ../../spec/GIL_Node_Model_v0.1.md

use gil::{
    ChainRef, CycleRef, ExistenceRef, JourneyRef, KnowledgeRef, MemoryRef, ParticipantRef,
    RefSyntaxError, RelationRef, SnapshotRef, StateRef, StepRef, WillRef,
};

/// 읽고 다시 적었을 때 **한 글자도 달라지지 않아야** 한다.
macro_rules! round_trip {
    ($ty:ty, $text:literal) => {{
        let parsed: $ty = $text
            .parse()
            .unwrap_or_else(|err| panic!("{} 를 읽지 못했다: {err}", $text));
        assert_eq!(parsed.to_string(), $text, "왕복이 글자를 바꿨다");
        parsed
    }};
}

/// 거절돼야 하는 값. 이유의 종류까지 확인한다.
macro_rules! refused {
    ($ty:ty, $text:expr, $reason:pat) => {{
        let err = $text
            .parse::<$ty>()
            .expect_err(concat!(stringify!($text), " 가 통과했다"));
        assert!(
            matches!(err, $reason),
            "{:?} 를 다른 이유로 거절했다: {err:?}",
            $text
        );
        err
    }};
}

// ── 명세가 적어 둔 열두 꼴 ─────────────────────────────────────────────────

#[test]
fn every_kind_the_spec_lists_survives_the_round_trip() {
    // §2.1 의 목록 그대로다. 여기 있는 글자가 곧 저장에 눕는 글자다.
    round_trip!(ChainRef, "chain:C1");
    round_trip!(CycleRef, "cycle:C2");
    round_trip!(StepRef, "step:C2/S3");
    round_trip!(ExistenceRef, "existence:X1");
    round_trip!(JourneyRef, "journey:X1@J7");
    round_trip!(ParticipantRef, "participant:U1");
    round_trip!(RelationRef, "relation:R1");
    round_trip!(WillRef, "will:W4");
    round_trip!(StateRef, "state:ES3");
    round_trip!(KnowledgeRef, "knowledge:K18");
    round_trip!(MemoryRef, "memory:M11");
    round_trip!(SnapshotRef, "snapshot:A1");
}

#[test]
fn the_bare_id_is_the_reference_without_its_kind() {
    // 객체 자신의 `id` 칸은 bare 를 적는다(§2.1). 남을 가리키는 칸만 prefix 를 지닌다.
    assert_eq!(round_trip!(CycleRef, "cycle:C2").id(), "C2");
    assert_eq!(round_trip!(StepRef, "step:C2/S3").id(), "S3");
    assert_eq!(round_trip!(WillRef, "will:W4").id(), "W4");
    assert_eq!(round_trip!(StateRef, "state:ES3").id(), "ES3");
    assert_eq!(round_trip!(JourneyRef, "journey:X1@J7").id(), "X1@J7");
}

// ── 종류가 없거나 다른 종류다 ──────────────────────────────────────────────

#[test]
fn a_bare_name_is_not_a_reference() {
    // 이것이 이 타입의 존재 이유다. `C2` 는 무엇의 2번인지 말하지 않는다.
    refused!(CycleRef, "C2", RefSyntaxError::NoKind { .. });
    refused!(StepRef, "S3", RefSyntaxError::NoKind { .. });
    refused!(ExistenceRef, "X1", RefSyntaxError::NoKind { .. });
    refused!(JourneyRef, "X1@J7", RefSyntaxError::NoKind { .. });
    refused!(WillRef, "W4", RefSyntaxError::NoKind { .. });
    // 화면의 축약도 저장 주소가 아니다.
    refused!(StepRef, "#3", RefSyntaxError::NoKind { .. });
}

#[test]
fn a_reference_of_another_kind_is_refused() {
    // Chain 과 Cycle 은 **같은 글자 `C`** 를 쓴다. 종류가 없으면 여기서 조용히 섞인다.
    refused!(ChainRef, "cycle:C2", RefSyntaxError::WrongKind { .. });
    refused!(CycleRef, "chain:C1", RefSyntaxError::WrongKind { .. });

    refused!(ExistenceRef, "journey:X1@J7", RefSyntaxError::WrongKind { .. });
    refused!(JourneyRef, "existence:X1", RefSyntaxError::WrongKind { .. });
    refused!(StepRef, "cycle:C2", RefSyntaxError::WrongKind { .. });
    refused!(WillRef, "state:ES3", RefSyntaxError::WrongKind { .. });
    refused!(KnowledgeRef, "memory:M11", RefSyntaxError::WrongKind { .. });
    refused!(MemoryRef, "knowledge:K18", RefSyntaxError::WrongKind { .. });
    refused!(ParticipantRef, "relation:R1", RefSyntaxError::WrongKind { .. });
    refused!(RelationRef, "participant:U1", RefSyntaxError::WrongKind { .. });
    refused!(SnapshotRef, "cycle:C2", RefSyntaxError::WrongKind { .. });
    refused!(StateRef, "knowledge:K18", RefSyntaxError::WrongKind { .. });
}

#[test]
fn a_kind_gil_does_not_know_is_refused() {
    refused!(CycleRef, "node:C2", RefSyntaxError::UnknownKind { .. });
    refused!(CycleRef, "cycles:C2", RefSyntaxError::UnknownKind { .. });
    refused!(CycleRef, ":C2", RefSyntaxError::UnknownKind { .. });
    // 종류 이름의 대소문자도 글자 그대로여야 한다.
    refused!(CycleRef, "Cycle:C2", RefSyntaxError::UnknownKind { .. });
    refused!(CycleRef, "CYCLE:C2", RefSyntaxError::UnknownKind { .. });
}

#[test]
fn the_letter_must_be_the_kinds_own() {
    refused!(CycleRef, "cycle:X1", RefSyntaxError::WrongLetter { .. });
    refused!(ExistenceRef, "existence:C1", RefSyntaxError::WrongLetter { .. });
    refused!(StateRef, "state:E3", RefSyntaxError::WrongLetter { .. });
    refused!(WillRef, "will:U4", RefSyntaxError::WrongLetter { .. });
    refused!(SnapshotRef, "snapshot:S1", RefSyntaxError::WrongLetter { .. });
    // 이름 글자의 대소문자도 그대로여야 한다.
    refused!(CycleRef, "cycle:c2", RefSyntaxError::WrongLetter { .. });
    refused!(StateRef, "state:es3", RefSyntaxError::WrongLetter { .. });
}

// ── 수는 canonical 이어야 한다 ─────────────────────────────────────────────

#[test]
fn a_number_must_be_canonical_decimal() {
    // 빈 수
    refused!(CycleRef, "cycle:C", RefSyntaxError::EmptyNumber { .. });
    refused!(StateRef, "state:ES", RefSyntaxError::EmptyNumber { .. });

    // 십진수가 아닌 것 — 음수·기호·다른 글자
    refused!(CycleRef, "cycle:C-1", RefSyntaxError::NotANumber { .. });
    refused!(CycleRef, "cycle:C+1", RefSyntaxError::NotANumber { .. });
    refused!(CycleRef, "cycle:C1a", RefSyntaxError::NotANumber { .. });
    refused!(CycleRef, "cycle:C1.0", RefSyntaxError::NotANumber { .. });
    refused!(CycleRef, "cycle:CC1", RefSyntaxError::NotANumber { .. });
    // ASCII 십진수만 받는다 — 다른 글자 체계의 숫자는 십진수가 아니다.
    refused!(CycleRef, "cycle:C١", RefSyntaxError::NotANumber { .. });
    refused!(CycleRef, "cycle:C１", RefSyntaxError::NotANumber { .. });

    // 선행 0 — 같은 것을 두 가지로 적게 된다
    refused!(CycleRef, "cycle:C01", RefSyntaxError::LeadingZero { .. });
    refused!(CycleRef, "cycle:C02", RefSyntaxError::LeadingZero { .. });
    refused!(JourneyRef, "journey:X1@J00", RefSyntaxError::LeadingZero { .. });
    refused!(StateRef, "state:ES00", RefSyntaxError::LeadingZero { .. });
    refused!(StateRef, "state:ES007", RefSyntaxError::LeadingZero { .. });
}

#[test]
fn zero_belongs_only_to_the_first_revision_and_the_first_state() {
    // §2.1: 초기 revision 과 초기 Existence State 만 0 을 쓴다.
    round_trip!(JourneyRef, "journey:X1@J0");
    round_trip!(StateRef, "state:ES0");

    refused!(ChainRef, "chain:C0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(CycleRef, "cycle:C0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(StepRef, "step:C2/S0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(StepRef, "step:C0/S3", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(ExistenceRef, "existence:X0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(JourneyRef, "journey:X0@J7", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(ParticipantRef, "participant:U0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(RelationRef, "relation:R0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(WillRef, "will:W0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(KnowledgeRef, "knowledge:K0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(MemoryRef, "memory:M0", RefSyntaxError::ZeroNotAllowed { .. });
    refused!(SnapshotRef, "snapshot:A0", RefSyntaxError::ZeroNotAllowed { .. });
}

#[test]
fn the_number_may_be_large() {
    // 이름은 계속 발급되고 재사용하지 않는다. 자릿수가 늘어도 같은 규칙이다.
    assert_eq!(round_trip!(CycleRef, "cycle:C4294967295").number(), u32::MAX);
    // 그 너머는 수로 읽히지 않는다.
    refused!(CycleRef, "cycle:C4294967296", RefSyntaxError::NotANumber { .. });
}

// ── 빈칸과 빈 글 ───────────────────────────────────────────────────────────

#[test]
fn whitespace_anywhere_is_refused() {
    // 양끝을 다듬어 받으면 같은 주소가 여러 글자꼴을 갖는다 — 왕복이 깨진다.
    refused!(CycleRef, " cycle:C2", RefSyntaxError::Whitespace { .. });
    refused!(CycleRef, "cycle:C2 ", RefSyntaxError::Whitespace { .. });
    refused!(CycleRef, "cycle: C2", RefSyntaxError::Whitespace { .. });
    refused!(CycleRef, "cycle :C2", RefSyntaxError::Whitespace { .. });
    refused!(CycleRef, "cycle:C 2", RefSyntaxError::Whitespace { .. });
    refused!(CycleRef, "cycle:C2\n", RefSyntaxError::Whitespace { .. });
    refused!(CycleRef, "cycle:C2\t", RefSyntaxError::Whitespace { .. });
    refused!(StepRef, "step:C2 /S3", RefSyntaxError::Whitespace { .. });
    refused!(JourneyRef, "journey:X1 @J7", RefSyntaxError::Whitespace { .. });
}

#[test]
fn an_empty_text_is_not_a_reference() {
    refused!(CycleRef, "", RefSyntaxError::Empty);
    refused!(StepRef, "", RefSyntaxError::Empty);
    refused!(JourneyRef, "", RefSyntaxError::Empty);
    // 종류만 있고 몸통이 없는 것은 빈 수다.
    refused!(CycleRef, "cycle:", RefSyntaxError::EmptyNumber { .. });
}

// ── 복합 주소: Step ────────────────────────────────────────────────────────

#[test]
fn a_step_without_its_cycle_is_refused() {
    // Step 이름은 소속 Cycle 안에서만 유일하다 — Cycle 이 빠지면 어느 Node 인지 정해지지 않는다.
    refused!(StepRef, "step:S3", RefSyntaxError::Shape { .. });
    refused!(StepRef, "step:C2", RefSyntaxError::Shape { .. });
    refused!(StepRef, "step:C2/S3/S4", RefSyntaxError::Shape { .. });
    refused!(StepRef, "step:C1/C2/S3", RefSyntaxError::Shape { .. });

    // 조각이 둘이지만 비어 있는 경우
    refused!(StepRef, "step:/S3", RefSyntaxError::WrongLetter { .. });
    refused!(StepRef, "step:C2/", RefSyntaxError::WrongLetter { .. });

    // 안쪽 Cycle 은 **bare ID** 다. 종류를 또 붙이지 않는다.
    refused!(StepRef, "step:cycle:C2/S3", RefSyntaxError::WrongLetter { .. });
}

#[test]
fn a_step_splits_into_its_cycle_and_number_and_joins_back() {
    let step = round_trip!(StepRef, "step:C2/S3");
    assert_eq!(step.cycle(), "cycle:C2".parse::<CycleRef>().unwrap());
    assert_eq!(step.step(), 3);

    let rebuilt = StepRef::new(step.cycle(), step.step()).expect("3번 Step 은 성립한다");
    assert_eq!(rebuilt, step, "분해했다 다시 조립하니 다른 것이 됐다");
    assert_eq!(rebuilt.to_string(), "step:C2/S3");

    // 같은 번호라도 다른 Cycle 이면 다른 Node 다.
    let elsewhere = StepRef::new("cycle:C1".parse().unwrap(), 3).unwrap();
    assert_ne!(elsewhere, step, "소속 Cycle 이 다른데 같은 Step 이 됐다");
    assert_eq!(elsewhere.to_string(), "step:C1/S3");

    // 0번 Step 은 없다.
    assert!(StepRef::new(step.cycle(), 0).is_none());
}

// ── 복합 주소: Journey ─────────────────────────────────────────────────────

#[test]
fn a_journey_without_both_halves_is_refused() {
    refused!(JourneyRef, "journey:J7", RefSyntaxError::Shape { .. });
    refused!(JourneyRef, "journey:X1", RefSyntaxError::Shape { .. });
    refused!(JourneyRef, "journey:X1@J7@J8", RefSyntaxError::Shape { .. });

    refused!(JourneyRef, "journey:@J7", RefSyntaxError::WrongLetter { .. });
    refused!(JourneyRef, "journey:X1@", RefSyntaxError::WrongLetter { .. });
    refused!(JourneyRef, "journey:existence:X1@J7", RefSyntaxError::WrongLetter { .. });
}

#[test]
fn a_journey_splits_into_its_existence_and_revision_and_joins_back() {
    let journey = round_trip!(JourneyRef, "journey:X1@J7");
    assert_eq!(journey.existence(), "existence:X1".parse::<ExistenceRef>().unwrap());
    assert_eq!(journey.revision(), 7);

    let rebuilt = JourneyRef::new(journey.existence(), journey.revision());
    assert_eq!(rebuilt, journey, "분해했다 다시 조립하니 다른 것이 됐다");
    assert_eq!(rebuilt.to_string(), "journey:X1@J7");

    // 빈 초기 revision 도 같은 길로 조립된다.
    let first = JourneyRef::new(journey.existence(), 0);
    assert_eq!(first.to_string(), "journey:X1@J0");
    assert_eq!(first.revision(), 0);

    // 같은 revision 번호라도 다른 Existence 면 다른 Journey 다.
    let other = JourneyRef::new("existence:X2".parse().unwrap(), 7);
    assert_ne!(other, journey, "소유한 Existence 가 다른데 같은 Journey 가 됐다");
    assert_eq!(other.to_string(), "journey:X2@J7");
}

// ── 만들기와 거절의 이유 ───────────────────────────────────────────────────

#[test]
fn a_kind_that_does_not_use_zero_refuses_to_be_built_with_it() {
    // 읽는 자리와 만드는 자리가 같은 답을 해야 한다.
    assert!(CycleRef::new(0).is_none());
    assert!(WillRef::new(0).is_none());
    assert!(SnapshotRef::new(0).is_none());

    assert!(StateRef::new(0).is_some());
    assert_eq!(StateRef::new(0).unwrap().to_string(), "state:ES0");

    assert_eq!(CycleRef::new(2).unwrap().to_string(), "cycle:C2");
    assert_eq!(KnowledgeRef::new(18).unwrap().to_string(), "knowledge:K18");
}

#[test]
fn a_refusal_says_something() {
    // 무엇이 틀렸는지 사람이 읽을 수 있어야 한다 — 문구는 재지 않고 비었는지만 본다.
    for text in [
        "", "C2", "#3", "node:C2", "cycle:X1", "cycle:C", "cycle:C0", "cycle:C01", "cycle:C2 ",
        "step:S3", "journey:X1",
    ] {
        let err = text
            .parse::<CycleRef>()
            .err()
            .or_else(|| text.parse::<StepRef>().err())
            .expect("이 값들은 어느 종류로도 읽히면 안 된다");
        assert!(!err.to_string().trim().is_empty(), "{text:?} 를 이유 없이 거절했다");
    }
}
