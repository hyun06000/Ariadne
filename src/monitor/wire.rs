//! **바깥으로 나가는 바이트** — canonical JSON v1 하나.
//!
//! [`super::view`] 가 사실의 모양을 소유하고, 이 파일은 그것을 글자로 옮기고 되읽는 자리
//! 하나다. **encoder 와 decoder 가 규칙을 따로 갖지 않는다** — 둘 다 같은 타입의 같은
//! `derive` 에서 나오므로, 한쪽만 바뀔 길이 없다.
//!
//! ```text
//! MonitorViewV1 → encode_view_v1 → compact UTF-8 JSON
//!                 decode_view_v1 ← 같은 규칙으로 되읽는다
//! ```
//!
//! # 규칙이 어디서 오는가
//!
//! | 규칙 | 어디서 |
//! |---|---|
//! | enum 은 snake_case 낱말 | `wire_words!` 가 `#[serde(rename = …)]` 을 함께 낳는다 |
//! | `None` 도 `null` 로 | `skip_serializing_if` 를 **쓰지 않는다** |
//! | 빈 목록도 `[]` 로 | `Vec` 의 기본 동작 |
//! | 모르는 key 는 무시 | `deny_unknown_fields` 를 **쓰지 않는다** |
//! | 모르는 enum 값은 거절 | serde 가 알려진 값 밖을 받지 않는다 |
//! | 배열 순서 보존 | `Vec` 이 순서를 지닌다 |
//! | compact | `to_string`(줄바꿈·들여쓰기 없음) |
//!
//! 규칙이 타입 쪽에 살기 때문에 이 파일에는 판정이 거의 없다. 하나뿐인 판정은 판 번호다.
//!
//! # 판 번호는 여기서 본다
//!
//! `schema_version` 이 1이 아니면 **읽지 않는다.** 모르는 판의 글자를 아는 척 읽으면 그
//! 순간부터 화면이 무엇을 그리고 있는지 아무도 말할 수 없다.

use super::detail::NodeDetailV1;
use super::view::{MonitorViewV1, SCHEMA_VERSION};

/// 바이트 경계에서 생길 수 있는 일.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum WireError {
    /// 글자로 옮기지 못했다.
    Encode { said: String },
    /// 글자를 되읽지 못했다 — 문법이 아니거나, 모르는 enum 값이거나, 칸이 없다.
    Decode { said: String },
    /// 이 판이 읽을 수 있는 번호가 아니다.
    ///
    /// **추측해 읽지 않는다.** 모르는 판은 모르는 의미다.
    UnsupportedSchema { found: u32 },
}

impl std::fmt::Display for WireError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            WireError::Encode { said } => write!(f, "View 를 JSON 으로 옮기지 못했다: {said}"),
            WireError::Decode { said } => write!(f, "JSON 을 View 로 되읽지 못했다: {said}"),
            WireError::UnsupportedSchema { found } => write!(
                f,
                "schema_version {found} 은 이 판(v{SCHEMA_VERSION})이 읽을 수 없다"
            ),
        }
    }
}

impl std::error::Error for WireError {}

/// View 하나를 **compact UTF-8 JSON** 한 줄로.
///
/// 같은 View 는 언제나 같은 글자가 된다 — 칸의 차례는 타입이 정하고, 배열의 차례는 값이
/// 정한다.
pub fn encode_view_v1(view: &MonitorViewV1) -> Result<String, WireError> {
    serde_json::to_string(view).map_err(|said| WireError::Encode {
        said: said.to_string(),
    })
}

/// JSON 한 벌을 typed View 로 되읽는다.
///
/// **판 번호를 먼저 본다.** 모르는 번호면 나머지를 읽지 않는다 — 같은 칸 이름이 다른 판에서
/// 다른 뜻일 수 있기 때문이다.
pub fn decode_view_v1(json: &str) -> Result<MonitorViewV1, WireError> {
    check_schema(json)?;
    serde_json::from_str(json).map_err(|said| WireError::Decode {
        said: said.to_string(),
    })
}

/// 판 번호만 먼저 꺼내 본다 — **이 단계에서는 나머지 모양을 요구하지 않는다.**
///
/// 그래서 모르는 판의 글자도 번호는 읽히고, 「모르는 판」과 「망가진 글자」가 갈린다.
fn check_schema(json: &str) -> Result<(), WireError> {
    let peeked: SchemaPeek = serde_json::from_str(json).map_err(|said| WireError::Decode {
        said: said.to_string(),
    })?;
    match peeked.schema_version == SCHEMA_VERSION {
        true => Ok(()),
        false => Err(WireError::UnsupportedSchema {
            found: peeked.schema_version,
        }),
    }
}

/// 상세 하나를 **compact UTF-8 JSON** 한 줄로.
///
/// View 와 **같은 규칙**을 쓴다 — 같은 derive 에서 나오므로 둘이 갈릴 수 없다.
pub fn encode_detail_v1(detail: &NodeDetailV1) -> Result<String, WireError> {
    serde_json::to_string(detail).map_err(|said| WireError::Encode {
        said: said.to_string(),
    })
}

/// JSON 한 벌을 typed 상세로 되읽는다. 판 번호를 먼저 본다.
pub fn decode_detail_v1(json: &str) -> Result<NodeDetailV1, WireError> {
    check_schema(json)?;
    serde_json::from_str(json).map_err(|said| WireError::Decode {
        said: said.to_string(),
    })
}

/// 판 번호 하나만 보는 눈.
///
/// 모르는 칸을 거절하지 않으므로, **번호를 읽는 일이 나머지 모양에 걸리지 않는다.**
#[derive(serde::Deserialize)]
struct SchemaPeek {
    schema_version: u32,
}

#[cfg(test)]
mod tests {
    use super::super::graph::tests::reading_one;
    use super::super::view::*;
    use super::*;
    use crate::{ActionKind, CycleKind, NodeKind};

    /// 일곱 동작과 모든 optional 칸이 채워진 View 하나.
    fn full() -> MonitorViewV1 {
        let mut seen = reading_one();
        let make = |kind: ActionKind, command: Option<&str>| crate::NextAction {
            kind,
            command: command.map(str::to_string),
            reason: "까닭".to_string(),
            help_ref: None,
        };
        seen.next_actions = vec![
            make(ActionKind::CloseStep(NodeKind::Verify), Some("gil close")),
            make(ActionKind::OpenStep(NodeKind::Analysis), None),
            make(ActionKind::CloseCycle(CycleKind::Experiment), Some("gil close")),
            make(ActionKind::OpenCycle(CycleKind::Experiment), None),
            make(ActionKind::OpenBranch(CycleKind::Interview), None),
            make(ActionKind::Revisit, Some("gil revisit")),
            make(ActionKind::Restore, Some("gil restore")),
        ];
        seen.next_actions[6].help_ref =
            Some(crate::manual::TopicId::parse("artifact/restore").expect("주소"));
        monitor_view_v1(&seen).expect("View")
    }

    fn json_of(view: &MonitorViewV1) -> serde_json::Value {
        serde_json::from_str(&encode_view_v1(view).expect("옮긴다")).expect("JSON")
    }

    // ── ① 모양 ───────────────────────────────────────────────────────────

    #[test]
    fn an_absent_value_is_written_as_null_and_never_dropped() {
        let mut seen = reading_one();
        seen.current_step = None;
        seen.current_will = None;
        seen.world.reason = None;
        let view = monitor_view_v1(&seen).expect("View");
        let json = json_of(&view);

        // 최상위.
        for key in ["current_will"] {
            assert!(json.get(key).is_some(), "{key} 가 사라졌다");
            assert!(json[key].is_null(), "{key} 가 null 이 아니다");
        }
        assert!(json["current"]["step_ref"].is_null(), "step_ref 가 사라졌다");
        assert!(json["world"]["reason"].is_null(), "reason 이 사라졌다");

        // 열린 Cycle 의 Report 와 열린 Step 의 요약.
        let here = json["timeline"]
            .as_array()
            .expect("배열")
            .iter()
            .find(|one| one["cycle_ref"] == "cycle:C3")
            .expect("지금");
        assert!(here.get("report").is_some() && here["report"].is_null());
        let open = here["steps"]
            .as_array()
            .expect("배열")
            .iter()
            .find(|step| step["state"] == "open")
            .expect("열린 Step");
        assert!(open.get("summary").is_some() && open["summary"].is_null());

        // 그리고 **글자에도** 생략이 없다.
        let text = encode_view_v1(&view).expect("옮긴다");
        assert!(text.contains("\"current_will\":null"), "{text}");
        assert!(text.contains("\"step_ref\":null"), "{text}");
    }

    #[test]
    fn an_empty_collection_is_written_as_an_empty_array() {
        let mut seen = reading_one();
        seen.timeline.clear();
        seen.next_actions.clear();
        let view = monitor_view_v1(&seen).expect("View");
        let text = encode_view_v1(&view).expect("옮긴다");
        assert!(text.contains("\"timeline\":[]"), "{text}");
        assert!(text.contains("\"next_actions\":[]"), "{text}");

        // Step 이 하나도 없는 Cycle 도 `[]` 다.
        let mut seen = reading_one();
        seen.timeline[0].steps.clear();
        let json = json_of(&monitor_view_v1(&seen).expect("View"));
        assert_eq!(json["timeline"][0]["steps"], serde_json::json!([]));
    }

    #[test]
    fn the_json_is_compact() {
        let text = encode_view_v1(&full()).expect("옮긴다");
        assert!(!text.contains('\n'), "줄바꿈이 들어갔다");
        assert!(!text.contains(": "), "칸 뒤에 빈칸이 있다");
        assert!(text.starts_with('{') && text.ends_with('}'));
    }

    // ── ② 여덟 낱말 ──────────────────────────────────────────────────────

    #[test]
    fn all_eight_view_enums_write_exactly_the_spec_words() {
        let words = |values: &[&str]| values.iter().map(|w| format!("\"{w}\"")).collect::<Vec<_>>();
        let checks: Vec<(Vec<String>, Vec<String>)> = vec![
            (
                CycleKindV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                words(&["interview", "experiment"]),
            ),
            (
                StepKindV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                // 경계 둘은 여기 없다 — §3.3.
                words(&[
                    "question", "interpretation", "synthesis", "define", "hypothesis",
                    "verify", "analysis", "outcome",
                ]),
            ),
            (
                NodeStateV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                words(&["open", "closed"]),
            ),
            (
                TimelineRelationV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                words(&["active_path", "revisit_source", "abandoned", "other"]),
            ),
            (
                WorldStateV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                words(&["clean", "dirty", "unknown"]),
            ),
            (
                VerdictV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                words(&["success", "failure"]),
            ),
            (
                DirectionActionV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                words(&["open_child", "revisit", "close_cycle"]),
            ),
            (
                NextActionKindV1::ALL.iter().map(|v| format!("\"{}\"", v.as_wire())).collect(),
                words(&[
                    "close_step", "open_step", "close_cycle", "open_cycle", "open_branch",
                    "revisit", "restore",
                ]),
            ),
        ];
        for (mine, spec) in &checks {
            assert_eq!(mine, spec, "낱말이 명세와 다르다");
        }
        assert_eq!(checks.len(), 8, "여덟 enum 을 다 보지 않았다");

        // 그리고 **JSON 이 실제로 그 낱말을 쓴다** — `as_wire` 와 serde 가 갈리지 않는다.
        macro_rules! written {
            ($($value:expr),+ $(,)?) => {$(
                assert_eq!(
                    serde_json::to_string(&$value).expect("옮긴다"),
                    format!("\"{}\"", $value.as_wire()),
                    "{:?} 의 JSON 이 as_wire 와 다르다", $value
                );
            )+};
        }
        for one in CycleKindV1::ALL { written!(*one); }
        for one in StepKindV1::ALL { written!(*one); }
        for one in NodeStateV1::ALL { written!(*one); }
        for one in TimelineRelationV1::ALL { written!(*one); }
        for one in WorldStateV1::ALL { written!(*one); }
        for one in VerdictV1::ALL { written!(*one); }
        for one in DirectionActionV1::ALL { written!(*one); }
        for one in NextActionKindV1::ALL { written!(*one); }
    }

    #[test]
    fn a_boundary_word_is_not_a_step_kind_the_wire_will_read() {
        // 밖에서 보내와도 되읽히지 않는다.
        for word in ["\"cycle_entry\"", "\"cycle_exit\""] {
            assert!(
                serde_json::from_str::<StepKindV1>(word).is_err(),
                "{word} 를 Step 종류로 받아들였다"
            );
        }
        // View 안의 Step 자리에서도 마찬가지다.
        let text = encode_view_v1(&full()).expect("옮긴다");
        let twisted = text.replacen("\"kind\":\"question\"", "\"kind\":\"cycle_entry\"", 1);
        assert_ne!(twisted, text, "바꿀 자리가 없다");
        assert!(
            matches!(decode_view_v1(&twisted), Err(WireError::Decode { .. })),
            "경계를 Step 으로 되읽었다"
        );
        // 그리고 상세에서도.
        assert!(!text.contains("cycle_entry") && !text.contains("cycle_exit"));
    }

    #[test]
    fn every_enum_value_survives_a_round_trip() {
        macro_rules! there_and_back {
            ($kind:ty) => {
                for one in <$kind>::ALL {
                    let text = serde_json::to_string(one).expect("옮긴다");
                    let back: $kind = serde_json::from_str(&text).expect("되읽는다");
                    assert_eq!(back, *one, "{one:?} 가 왕복하지 못했다");
                }
            };
        }
        there_and_back!(CycleKindV1);
        there_and_back!(StepKindV1);
        there_and_back!(NodeStateV1);
        there_and_back!(TimelineRelationV1);
        there_and_back!(WorldStateV1);
        there_and_back!(VerdictV1);
        there_and_back!(DirectionActionV1);
        there_and_back!(NextActionKindV1);
    }

    // ── ③ 거절과 관용 ────────────────────────────────────────────────────

    #[test]
    fn an_unknown_enum_word_is_refused_not_guessed() {
        let text = encode_view_v1(&full()).expect("옮긴다");
        for (from, to) in [
            ("\"active_path\"", "\"main_line\""),
            ("\"verify\"", "\"validate\""),
            ("\"failure\"", "\"inconclusive\""),
            ("\"close_step\"", "\"finish_step\""),
        ] {
            let twisted = text.replacen(from, to, 1);
            assert_ne!(twisted, text, "{from} 이 글자에 없다 — 시험이 아무것도 재지 않는다");
            assert!(
                matches!(decode_view_v1(&twisted), Err(WireError::Decode { .. })),
                "모르는 낱말 {to} 를 받아들였다"
            );
        }
    }

    #[test]
    fn an_unknown_object_key_is_ignored_within_the_same_schema() {
        let view = full();
        let text = encode_view_v1(&view).expect("옮긴다");
        // 최상위에도, 안쪽 객체에도 모르는 칸을 넣는다.
        let widened = text
            .replacen("{\"schema_version\":1", "{\"tomorrow\":{\"a\":[1,2]},\"schema_version\":1", 1)
            .replacen("\"cycle_ref\":\"cycle:C1\"", "\"lane\":3,\"cycle_ref\":\"cycle:C1\"", 1);
        assert_ne!(widened, text);
        let back = decode_view_v1(&widened).expect("모르는 칸은 지나친다");
        assert_eq!(back, view, "모르는 칸이 사실을 바꿨다");
    }

    #[test]
    fn a_schema_version_that_is_not_one_is_refused() {
        let text = encode_view_v1(&full()).expect("옮긴다");
        for found in [0u32, 2, 99] {
            let other = text.replacen("\"schema_version\":1", &format!("\"schema_version\":{found}"), 1);
            assert_eq!(
                decode_view_v1(&other),
                Err(WireError::UnsupportedSchema { found }),
                "판 {found} 을 읽었다"
            );
        }
        // 번호가 아예 없어도 읽지 않는다.
        let without = text.replacen("\"schema_version\":1,", "", 1);
        assert!(matches!(decode_view_v1(&without), Err(WireError::Decode { .. })));
        // 그리고 1은 읽는다.
        assert!(decode_view_v1(&text).is_ok());
    }

    // ── ④ 글은 원문 그대로 ──────────────────────────────────────────────

    #[test]
    fn a_nasty_string_crosses_the_wire_exactly_as_written() {
        let nasty = "따옴표 \" 역슬래시 \\ 줄바꿈 \n 탭 \t <script>alert(1)</script> & < > \u{1f600}";
        let mut seen = reading_one();
        seen.timeline[0].steps[0].summary = Some(nasty.to_string());
        seen.timeline[0].facts.experiment_definition = Some(crate::ExperimentDefinition {
            problem: nasty.to_string(),
            success_condition: nasty.to_string(),
        });
        let view = monitor_view_v1(&seen).expect("View");
        let back = decode_view_v1(&encode_view_v1(&view).expect("옮긴다")).expect("되읽는다");

        assert_eq!(back.timeline[0].steps[0].summary.as_deref(), Some(nasty));
        let definition = back.timeline[0].experiment_definition.as_ref().expect("정의");
        assert_eq!(definition.problem, nasty);

        // JSON 이 필요한 escape 만 했다 — HTML 로 바꾸지 않았다.
        let text = encode_view_v1(&view).expect("옮긴다");
        assert!(text.contains("<script>"), "HTML escape 를 했다: {text}");
        assert!(!text.contains("&lt;"), "HTML escape 를 했다");
        assert!(text.contains("\\\""), "따옴표를 escape 하지 않았다");
        assert!(text.contains("\\\\"), "역슬래시를 escape 하지 않았다");
        assert!(text.contains("\\n") && text.contains("\\t"), "줄바꿈·탭이 사라졌다");
    }

    #[test]
    fn four_thousand_characters_arrive_whole() {
        let long = "가".repeat(4000);
        let mut seen = reading_one();
        seen.timeline[1].steps[0].summary = Some(long.clone());
        let view = monitor_view_v1(&seen).expect("View");
        let back = decode_view_v1(&encode_view_v1(&view).expect("옮긴다")).expect("되읽는다");
        let said = back.timeline[1].steps[0].summary.as_ref().expect("요약");
        assert_eq!(said.chars().count(), 4000, "잘렸다");
        assert_eq!(*said, long);
    }

    // ── ⑤ 차례와 결정성 ─────────────────────────────────────────────────

    #[test]
    fn the_order_of_every_array_survives_the_wire() {
        let view = full();
        let back = decode_view_v1(&encode_view_v1(&view).expect("옮긴다")).expect("되읽는다");

        let cycles = |one: &MonitorViewV1| -> Vec<String> {
            one.timeline.iter().map(|at| at.cycle_ref.clone()).collect()
        };
        assert_eq!(cycles(&back), cycles(&view));
        assert_eq!(cycles(&view), ["cycle:C1", "cycle:C2", "cycle:C3"], "번호순으로 다시 늘어놨다");

        for (one, other) in back.timeline.iter().zip(&view.timeline) {
            let steps = |at: &TimelineCycleV1| -> Vec<String> {
                at.steps.iter().map(|s| s.step_ref.clone()).collect()
            };
            assert_eq!(steps(one), steps(other), "{} 의 Step 차례", one.cycle_ref);
        }
        let kinds = |one: &MonitorViewV1| -> Vec<NextActionKindV1> {
            one.next_actions.iter().map(|at| at.kind).collect()
        };
        assert_eq!(kinds(&back), kinds(&view));
        assert_eq!(kinds(&view)[0], NextActionKindV1::CloseStep);
        assert_eq!(kinds(&view)[6], NextActionKindV1::Restore);
    }

    #[test]
    fn the_same_view_writes_the_same_bytes_every_time() {
        let view = full();
        let once = encode_view_v1(&view).expect("한 번");
        for _ in 0..5 {
            assert_eq!(encode_view_v1(&view).expect("또"), once, "글자가 흔들렸다");
        }
        // 그리고 되읽어 다시 쓴 것도 같다.
        let back = decode_view_v1(&once).expect("되읽는다");
        assert_eq!(back, view, "왕복이 사실을 바꿨다");
        assert_eq!(encode_view_v1(&back).expect("다시"), once, "왕복이 글자를 바꿨다");
    }

    #[test]
    fn the_whole_view_round_trips_with_every_optional_filled() {
        let view = full();
        let back = decode_view_v1(&encode_view_v1(&view).expect("옮긴다")).expect("되읽는다");
        assert_eq!(back, view);
        // 채워진 것들이 실제로 채워져 있었다 — 아니면 이 시험이 아무것도 재지 않는다.
        assert!(back.current.step_ref.is_some());
        assert!(back.timeline.iter().any(|one| one.report.is_some()));
        assert!(back.timeline.iter().any(|one| one.experiment_definition.is_some()));
        assert!(back.timeline.iter().any(|one| one.revisit_from_cycle_ref.is_some()));
        assert!(back.next_actions.iter().any(|one| one.help_ref.is_some()));
        assert!(back.next_actions.iter().any(|one| one.step_kind.is_some()));
        assert!(back.next_actions.iter().any(|one| one.cycle_kind.is_some()));
        assert_eq!(back.next_actions[6].help_ref.as_deref(), Some("artifact/restore"));
    }


}
