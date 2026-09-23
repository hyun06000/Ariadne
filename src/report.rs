//! Report — Step 을 닫을 때 함께 남기는 기록.
//!
//! v0.1 에서 Report 는 **이름 붙은 칸의 모음**이다. 어떤 칸이 있어야 하는지는
//! `gil-spec.yaml` 의 `close_requires` 가 정한다(코드가 아니라).
//!
//! # 사람이 적어 준 글을 읽는 꼴 ([`Report::parse`])
//!
//! **남의 문법을 빌려 쓰지 않는다.** 한때 YAML 로 받았는데, YAML 에서 ` #` 뒤는 주석이라
//! `result: 기존 Walk의 #7 을 찾았다` 가 **`기존 Walk의` 로 잘린 채 성공했다**(실사용 보고 #124).
//! `3.10` 이 `3.1` 이 되는 것도 같은 병이다. 성공했는데 다른 데이터가 되는 것 —
//! 옛 구현이 커밋 트레일러를 스키마로 쓰다 물린 상처와 **구조가 같다.**
//!
//! 그래서 규칙을 우리가 갖는다. 넷뿐이다.
//!
//! ```text
//! problem: 줄 끝까지 그대로다 — #7 도 3.10 도 그냥 글자다
//! next_direction:
//!   action: revisit          ← 들여쓰면 이름이 점으로 이어진다
//! interpretation: |
//!   여러 줄은 이렇게 연다.
//!   여기서도 #7 은 #7 이다.
//! empty_field:               ← 아래에 아무것도 없으면 빈 값이다
//! ```
//!
//! 주석이 없고, 인용이 없고, 형 변환이 없다. 적은 글자가 그대로 값이 된다.

use std::collections::BTreeMap;
use std::fmt;

/// Report 가 쓰는 칸의 이름 — **`gil-spec.yaml` 이 부르는 그대로, 한 자리에.**
///
/// 이 이름들은 story·context·monitor 가 **같은 원본에서 같은 사실을 읽으려고** 쓴다.
/// 각 renderer 가 제 파일에 따로 적어 두면 한 곳에서 오타 하나가 나도 그 renderer 만
/// 조용히 빈 값을 보이고, 세 화면이 서로 다른 말을 하게 된다.
///
/// **여기 있는 것은 이름뿐이다.** 어떤 칸이 필요한지, 어떤 값이 허락되는지는 여전히
/// 문법이 정한다 — 이 목록은 그 판정에 끼어들지 않는다.
pub(crate) mod field {
    pub(crate) const PROBLEM: &str = "problem";
    pub(crate) const SUCCESS_CONDITION: &str = "success_condition";
    pub(crate) const VERDICT: &str = "verdict";
    pub(crate) const HANDOFF_SUMMARY: &str = "handoff_summary";
    pub(crate) const NEXT_ACTION: &str = "next_direction.action";
    pub(crate) const NEXT_REASON: &str = "next_direction.reason";

    // Step 하나를 한 줄로 대표하는 칸들. 어느 Step kind 가 어느 칸을 쓰는지는
    // [`crate::monitor::summary_field`] 한 자리가 정한다.
    pub(crate) const QUESTION: &str = "question";
    pub(crate) const RESPONSE: &str = "response";
    pub(crate) const INTERPRETATION: &str = "interpretation";
    pub(crate) const STATEMENT: &str = "statement";
    pub(crate) const HYPOTHESIS: &str = "hypothesis";
    pub(crate) const RESULT: &str = "result";
    pub(crate) const LESSON: &str = "lesson";
}

/// 이름 붙은 칸들의 모음. 순서는 이름순으로 고정된다(메시지·시험이 흔들리지 않게).
#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct Report {
    fields: BTreeMap<String, String>,
}

impl Report {
    pub fn new() -> Self {
        Report::default()
    }

    /// 칸 하나를 채운 새 Report 를 돌려준다.
    pub fn with(mut self, name: impl Into<String>, value: impl Into<String>) -> Self {
        self.insert(name, value);
        self
    }

    pub fn insert(&mut self, name: impl Into<String>, value: impl Into<String>) {
        self.fields.insert(name.into(), value.into());
    }

    pub fn remove(&mut self, name: &str) {
        self.fields.remove(name);
    }

    pub fn get(&self, name: &str) -> Option<&str> {
        self.fields.get(name).map(String::as_str)
    }

    /// 그 이름의 칸이 있는가.
    ///
    /// v0.1 은 **있는지만** 본다. 내용이 비었는지는 명세가 말하지 않아서 재지 않는다.
    pub fn has(&self, name: &str) -> bool {
        self.fields.contains_key(name)
    }

    pub fn field_names(&self) -> impl Iterator<Item = &str> {
        self.fields.keys().map(String::as_str)
    }

    pub fn is_empty(&self) -> bool {
        self.fields.is_empty()
    }
}

/// 여러 줄 값을 여는 표. 이 글자만 값의 자리에 홀로 서면 아래가 값이 된다.
const BLOCK: &str = "|";

/// 읽는 동안 열려 있는 여러 줄 값.
struct Block {
    name: String,
    lines: Vec<String>,
    /// 첫 내용 줄이 정한다 — 그만큼을 모든 줄에서 벗겨 낸다.
    indent: Option<usize>,
    /// 이 값을 연 칸의 들여쓰기. 그보다 깊어야 값의 줄이다.
    opened_at: usize,
}

impl Report {
    /// 사람이 적어 준 글을 Report 로 읽는다.
    ///
    /// 규칙은 모듈 문서에 넷으로 적혀 있다. **적은 글자가 그대로 값이 된다** —
    /// 값을 조용히 줄이거나 바꾸는 자리는 이 함수 안에 없다.
    pub fn parse(text: &str) -> Result<Report, ReportSyntaxError> {
        let mut report = Report::new();
        // 열려 있는 이름 마디: (들여쓰기, 여기까지의 이름 앞머리, 자식을 받았는가)
        let mut names: Vec<(usize, String, bool)> = Vec::new();
        let mut block: Option<Block> = None;
        let mut blanks = 0;

        for (index, raw) in text.lines().enumerate() {
            let line = index + 1;
            let indent = indent_of(raw, line)?;
            let empty = raw.trim().is_empty();

            // ① 여러 줄 값이 열려 있으면 먼저 그쪽에 묻는다.
            if let Some(open) = &block {
                if empty {
                    // 값 안의 빈 줄은 뒤에 내용이 더 있을 때만 값이 된다.
                    blanks += 1;
                    continue;
                }
                let inside = match open.indent {
                    Some(indent_of_block) => indent >= indent_of_block,
                    None => indent > open.opened_at,
                };
                if inside {
                    let open = block.as_mut().expect("방금 열려 있는 것을 보았다");
                    let width = *open.indent.get_or_insert(indent);
                    open.lines.extend(std::iter::repeat_n(String::new(), blanks));
                    blanks = 0;
                    open.lines.push(raw.chars().skip(width).collect());
                    continue;
                }
                let open = block.take().expect("방금 열려 있는 것을 보았다");
                report.insert(open.name, open.lines.join("\n"));
                blanks = 0;
            }
            if empty {
                continue;
            }

            // ② 얕아진 만큼 이름 마디를 닫는다.
            while names.last().is_some_and(|(at, _, _)| indent <= *at) {
                close_name(&mut names, &mut report);
            }
            if names.is_empty() && indent > 0 {
                return Err(ReportSyntaxError {
                    line,
                    detail: "이 줄의 들여쓰기가 어디에도 붙지 않는다 — 여러 줄 값이라면 \
                             윗줄을 `이름: |` 로 열어라"
                        .to_string(),
                });
            }

            // ③ 새 칸.
            let Some((name, rest)) = raw.trim().split_once(':') else {
                return Err(ReportSyntaxError {
                    line,
                    detail: "칸 이름이 없다 — `이름: 값` 꼴이어야 한다".to_string(),
                });
            };
            let name = name.trim_end();
            if name.is_empty() || name.contains(char::is_whitespace) {
                return Err(ReportSyntaxError {
                    line,
                    detail: format!("{name:?} 는 칸 이름으로 쓸 수 없다 — 이름에 빈칸이 없어야 한다"),
                });
            }
            if let Some((_, _, got_child)) = names.last_mut() {
                *got_child = true;
            }
            let prefix = names.last().map(|(_, at, _)| at.as_str()).unwrap_or("");
            let full = format!("{prefix}{name}");

            // 값은 여기서부터 줄 끝까지다. 이 뒤로 아무것도 해석하지 않는다.
            let value = rest.strip_prefix(' ').unwrap_or(rest).trim_end();
            if value == BLOCK {
                block = Some(Block {
                    name: full,
                    lines: Vec::new(),
                    indent: None,
                    opened_at: indent,
                });
            } else if value.is_empty() {
                names.push((indent, format!("{full}."), false));
            } else {
                report.insert(full, value);
            }
        }

        if let Some(open) = block {
            report.insert(open.name, open.lines.join("\n"));
        }
        while !names.is_empty() {
            close_name(&mut names, &mut report);
        }
        Ok(report)
    }
}

/// 이름 마디를 닫는다. 자식을 하나도 못 받았으면 그건 **빈 값을 적은 칸**이었다.
fn close_name(names: &mut Vec<(usize, String, bool)>, report: &mut Report) {
    let (_, prefix, got_child) = names.pop().expect("부르는 쪽이 비지 않은 것을 확인했다");
    if !got_child {
        report.insert(prefix.trim_end_matches('.'), "");
    }
}

/// 앞의 빈칸을 센다. 탭은 거절한다 — 폭이 보는 곳마다 달라 값이 조용히 어긋난다.
fn indent_of(raw: &str, line: usize) -> Result<usize, ReportSyntaxError> {
    let width = raw.len() - raw.trim_start().len();
    match raw[..width].contains('\t') {
        true => Err(ReportSyntaxError {
            line,
            detail: "들여쓰기에 탭이 있다 — 빈칸으로 들여써라".to_string(),
        }),
        false => Ok(width),
    }
}

/// 적어 준 글이 이 꼴이 아닌 이유. 몇 번째 줄인지를 함께 말한다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ReportSyntaxError {
    /// 1부터 센 줄 번호.
    pub line: usize,
    pub detail: String,
}

impl fmt::Display for ReportSyntaxError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}번째 줄: {}", self.line, self.detail)
    }
}

impl std::error::Error for ReportSyntaxError {}

impl<K, V> FromIterator<(K, V)> for Report
where
    K: Into<String>,
    V: Into<String>,
{
    fn from_iter<I: IntoIterator<Item = (K, V)>>(iter: I) -> Self {
        Report {
            fields: iter.into_iter().map(|(k, v)| (k.into(), v.into())).collect(),
        }
    }
}
