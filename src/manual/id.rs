//! Topic 주소 — **공개 의미이지 파일 경로가 아니다.**
//!
//! ```text
//! current
//! step/verify/close
//! artifact/dirty/non-verify
//! ```
//!
//! 계약을 **생성 시점에** 강제한다(Manual Model §4). 이 타입을 손에 넣었다면 다음이 이미
//! 참이다.
//!
//! ```text
//! ASCII 소문자 · 숫자 · `-` · segment 사이의 `/`
//! 빈 segment 없음 · 선행/후행 `/` 없음 · `//` 없음
//! `.` 도 `..` 도 없음
//! 양끝 공백을 다듬지 않는다 — 다듬으면 두 글자가 한 주소가 된다
//! ```
//!
//! **경로로도 enum 으로도 암묵 변환하지 않는다.** 주소가 파일 경로가 되면 폴더를 옮기는
//! 순간 공개 주소가 바뀌고, enum 이 되면 내부 이름이 공개 계약이 된다.

use std::fmt;

/// canonical Topic 주소 하나.
#[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(crate) struct TopicId(String);

impl TopicId {
    /// 사람이 적어 준 글자를 주소로 읽는다. 계약을 어기면 **왜 어겼는지**와 함께 거절한다.
    pub(crate) fn parse(text: &str) -> Result<TopicId, TopicIdError> {
        if text.is_empty() {
            return Err(TopicIdError::Empty);
        }
        // **다듬지 않는다.** ` current` 를 받아 주면 그 글자도 같은 주소가 되고, 그러면
        // 주소가 하나가 아니게 된다.
        if text.trim() != text {
            return Err(TopicIdError::Padded);
        }
        if text.starts_with('/') || text.ends_with('/') {
            return Err(TopicIdError::EdgeSlash);
        }

        for segment in text.split('/') {
            if segment.is_empty() {
                return Err(TopicIdError::EmptySegment);
            }
            if segment == "." || segment == ".." {
                return Err(TopicIdError::DotSegment {
                    segment: segment.to_string(),
                });
            }
            if let Some(bad) = segment.chars().find(|c| !is_usable(*c)) {
                return Err(TopicIdError::BadCharacter { found: bad });
            }
        }
        Ok(TopicId(text.to_string()))
    }

    /// **아직 시험만 쓴다.** 읽는 자리는 [`Display`](fmt::Display) 하나면 충분하다.
    #[cfg(test)]
    pub(crate) fn as_str(&self) -> &str {
        &self.0
    }
}

/// 주소에 쓸 수 있는 글자 — ASCII 소문자·숫자·`-`.
fn is_usable(c: char) -> bool {
    c.is_ascii_lowercase() || c.is_ascii_digit() || c == '-'
}

impl fmt::Display for TopicId {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.0)
    }
}

/// 주소가 아닌 이유. **「없는 Topic」과 다르다** — 이건 글자부터 주소가 아니다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum TopicIdError {
    Empty,
    Padded,
    EdgeSlash,
    EmptySegment,
    DotSegment { segment: String },
    BadCharacter { found: char },
}

impl fmt::Display for TopicIdError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            TopicIdError::Empty => write!(f, "주소가 비어 있다"),
            TopicIdError::Padded => {
                write!(f, "앞뒤에 공백이 있다 — 공백을 다듬어 받지 않는다")
            }
            TopicIdError::EdgeSlash => write!(f, "`/` 로 시작하거나 끝난다"),
            TopicIdError::EmptySegment => write!(f, "빈 조각이 있다 (`//`)"),
            TopicIdError::DotSegment { segment } => {
                write!(f, "{segment:?} 조각은 주소가 아니다")
            }
            TopicIdError::BadCharacter { found } => write!(
                f,
                "{found:?} 는 쓸 수 없다 — ASCII 소문자·숫자·`-` 와 조각 사이의 `/` 만 쓴다"
            ),
        }
    }
}

impl std::error::Error for TopicIdError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn the_addresses_the_model_lists_are_all_legal() {
        for text in [
            "current",
            "interview/approval",
            "step/verify/close",
            "cycle/experiment/close",
            "artifact/restore",
            "artifact/dirty/non-verify",
            "report/observation-vs-interpretation",
            "error/parent-not-closed",
            "a1/b2-c3",
        ] {
            let id = TopicId::parse(text).unwrap_or_else(|err| panic!("{text:?}: {err}"));
            // **정확한 왕복.** 읽은 글자가 그대로 나온다.
            assert_eq!(id.as_str(), text);
            assert_eq!(id.to_string(), text);
        }
    }

    #[test]
    fn everything_that_is_not_an_address_is_refused_with_a_reason() {
        for (text, expected) in [
            ("", TopicIdError::Empty),
            (" current", TopicIdError::Padded),
            ("current ", TopicIdError::Padded),
            ("\tcurrent", TopicIdError::Padded),
            ("/current", TopicIdError::EdgeSlash),
            ("current/", TopicIdError::EdgeSlash),
            ("current//world", TopicIdError::EmptySegment),
            (
                "current/.",
                TopicIdError::DotSegment {
                    segment: ".".to_string(),
                },
            ),
            (
                ".",
                TopicIdError::DotSegment {
                    segment: ".".to_string(),
                },
            ),
            (
                "..",
                TopicIdError::DotSegment {
                    segment: "..".to_string(),
                },
            ),
            (
                "artifact/../restore",
                TopicIdError::DotSegment {
                    segment: "..".to_string(),
                },
            ),
            ("Current", TopicIdError::BadCharacter { found: 'C' }),
            ("artifact/Restore", TopicIdError::BadCharacter { found: 'R' }),
            ("current world", TopicIdError::BadCharacter { found: ' ' }),
            ("current_world", TopicIdError::BadCharacter { found: '_' }),
            ("current.", TopicIdError::BadCharacter { found: '.' }),
            ("artifact\\restore", TopicIdError::BadCharacter { found: '\\' }),
        ] {
            assert_eq!(
                TopicId::parse(text).unwrap_err(),
                expected,
                "{text:?} 가 다른 이유로 거절됐다"
            );
        }
    }

    #[test]
    fn an_address_does_not_quietly_become_a_path() {
        // 경로로 변환하는 문이 없다. 있으면 폴더를 옮기는 순간 공개 주소가 바뀐다.
        let id = TopicId::parse("artifact/dirty/non-verify").unwrap();
        assert_eq!(id.as_str(), "artifact/dirty/non-verify");
    }
}
