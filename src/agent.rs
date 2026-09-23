//! **Agent Core handshake v1** — Plugin 이 이름이나 경로만 보고 Core 를 믿지 않는 문.
//!
//! Plugin 은 자기 안에 실린 binary 하나를 Agent 의 GIL 로 쓴다. 그 파일이 거기 있다는 사실은
//! 아무것도 보장하지 않는다 — 다른 판일 수도, 다른 architecture 일 수도, 실행조차 안 될 수도
//! 있다. 그래서 **실제로 실행해 보고** 자기가 무엇인지 말하게 한다.
//!
//! Companion 의 handshake 와 이름이 비슷하지만 **뜻이 다르다.** 그쪽은 "사람이 볼 창이 떠
//! 있는가" 를 묻고, 이쪽은 "Agent 가 부를 Core 가 이 판과 맞는가" 를 묻는다. 같은 문자열을
//! 억지로 나눠 쓰면 한쪽 계약이 바뀔 때 다른 쪽이 조용히 깨진다. 그래서 따로 둔다.
//!
//! 이 문은 Project 를 열지 않고 잠금을 잡지 않는다. 상수만 적어 내보낸다.

use serde::{Deserialize, Serialize};

pub const DESCRIPTOR_ARG: &str = "--gil-agent-descriptor";
pub const PROBE_ARG: &str = "--gil-agent-probe";

pub const SCHEMA_VERSION: u32 = 1;
pub const PROTOCOL_VERSION: u32 = 1;
/// Agent 가 부를 수 있는 명령의 판. 명령이 늘거나 뜻이 바뀌면 이 수가 오른다.
pub const ACTION_SURFACE: u32 = 1;
pub const PRODUCT: &str = "gil_core";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RangeV1 {
    pub min: u32,
    pub max: u32,
}

impl RangeV1 {
    const fn exact(version: u32) -> Self {
        Self {
            min: version,
            max: version,
        }
    }
}

/// 이 binary 가 스스로 말하는 공개 계약. 경로·Project·사용자 이름은 싣지 않는다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DescriptorV1 {
    pub schema_version: u32,
    pub product: String,
    pub core_version: String,
    pub protocol: RangeV1,
    /// 이 판이 읽고 쓰는 저장 format. 범위 밖 Project 는 Core 가 거절한다.
    pub storage_format: RangeV1,
    pub action_surface: RangeV1,
    pub os: String,
    pub arch: String,
}

impl DescriptorV1 {
    pub fn current() -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            product: PRODUCT.to_string(),
            core_version: env!("CARGO_PKG_VERSION").to_string(),
            protocol: RangeV1::exact(PROTOCOL_VERSION),
            storage_format: RangeV1::exact(crate::FORMAT),
            action_surface: RangeV1::exact(ACTION_SURFACE),
            // **지금 이 binary 가 지어진 대상**이다. 부르는 쪽이 자기 기계와 견준다.
            os: std::env::consts::OS.to_string(),
            arch: std::env::consts::ARCH.to_string(),
        }
    }
}

/// 실행 중인 binary 가 **지금** 답했다는 증거. 파일을 읽은 것과 구별된다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct ProbeReplyV1 {
    pub schema_version: u32,
    pub challenge: String,
    pub core: DescriptorV1,
}

fn valid_challenge(challenge: &str) -> bool {
    (16..=128).contains(&challenge.len())
        && challenge
            .bytes()
            .all(|one| one.is_ascii_alphanumeric() || one == b'-' || one == b'_')
}

/// handshake 인수이면 답을 돌려주고 평범한 명령 처리를 막는다.
///
/// 그 밖의 인수는 건드리지 않는다 — `None` 을 주어 원래 문법이 그대로 돌게 한다.
pub fn answer_cli(args: &[String]) -> Option<Result<String, String>> {
    match (args.first().map(String::as_str), args.len()) {
        (Some(DESCRIPTOR_ARG), 1) => Some(Ok(format!(
            "{}\n",
            serde_json::to_string(&DescriptorV1::current()).expect("descriptor JSON")
        ))),
        (Some(PROBE_ARG), 2) => {
            let challenge = &args[1];
            if !valid_challenge(challenge) {
                return Some(Err("challenge 모양이 잘못됐다".to_string()));
            }
            let replied = ProbeReplyV1 {
                schema_version: SCHEMA_VERSION,
                challenge: challenge.clone(),
                core: DescriptorV1::current(),
            };
            Some(Ok(format!(
                "{}\n",
                serde_json::to_string(&replied).expect("probe JSON")
            )))
        }
        _ => None,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(words: &[&str]) -> Vec<String> {
        words.iter().map(|one| one.to_string()).collect()
    }

    #[test]
    fn the_descriptor_is_compact_json_without_a_path_or_project() {
        let said = answer_cli(&args(&[DESCRIPTOR_ARG]))
            .expect("descriptor")
            .expect("answer");
        assert_eq!(said.matches('\n').count(), 1, "한 줄이어야 한다");
        assert!(!said.contains("/Users/"));
        assert!(!said.contains("project"));

        let decoded: DescriptorV1 = serde_json::from_str(said.trim_end()).expect("descriptor");
        assert_eq!(decoded, DescriptorV1::current());
        // 저장 format 은 지어낸 값이 아니라 **Core 가 실제로 쓰는 그것**이다.
        assert_eq!(decoded.storage_format, RangeV1::exact(crate::FORMAT));
        assert_eq!(decoded.product, PRODUCT);
    }

    #[test]
    fn the_descriptor_says_which_machine_it_was_built_for() {
        let one = DescriptorV1::current();
        assert!(!one.os.is_empty() && !one.arch.is_empty());
        // 부르는 쪽이 자기 기계와 견줄 수 있어야 한다 — 빈 값이면 아무것이나 통과한다.
        assert_eq!(one.os, std::env::consts::OS);
        assert_eq!(one.arch, std::env::consts::ARCH);
    }

    #[test]
    fn a_probe_echoes_the_challenge_it_was_given() {
        let challenge = "fresh_challenge_0001";
        let said = answer_cli(&args(&[PROBE_ARG, challenge]))
            .expect("probe")
            .expect("answer");
        let replied: ProbeReplyV1 = serde_json::from_str(said.trim_end()).expect("reply");
        assert_eq!(replied.challenge, challenge);
        assert_eq!(replied.core, DescriptorV1::current());
    }

    #[test]
    fn a_misshapen_challenge_is_refused_instead_of_answered() {
        for bad in ["", "short", &"x".repeat(129), "has space", "sem;colon"] {
            let said = answer_cli(&args(&[PROBE_ARG, bad])).expect("probe");
            assert!(said.is_err(), "{bad:?} 를 받아 주었다");
        }
    }

    #[test]
    fn ordinary_commands_never_enter_the_handshake_door() {
        for words in [
            vec!["status"],
            vec!["open"],
            vec!["help", "gil"],
            vec![DESCRIPTOR_ARG, "extra"],
            vec![PROBE_ARG],
            vec![PROBE_ARG, "fresh_challenge_0001", "extra"],
        ] {
            assert_eq!(answer_cli(&args(&words)), None, "{words:?}");
        }
    }
}
