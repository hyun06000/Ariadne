//! Manual — **필요한 규칙 하나를 안정된 주소로 읽는다.**
//!
//! 전체 명세를 미리 주입하는 Wiki 가 아니다. 지금 막힌 자리 하나를 푸는 Topic 하나를
//! 그 주소로 읽는다(Manual Model §1·§18).
//!
//! ```text
//! gil --help          명령 목록
//! gil open --help     지금 자리의 입력 계약
//! gil help <주소>     그 규칙의 뜻과 복구법        ← 여기
//! ```
//!
//! # 바이너리와 같은 버전으로 묶인다
//!
//! Topic 본문은 [`include_str!`] 로 **컴파일에 들어간다.** 그래서
//!
//! ```text
//! 설치본만 있으면 원본 저장소 없이 읽힌다
//! Wiki 서버·Git·MCP·네트워크가 필요 없다
//! 작업 폴더의 같은 이름 파일이 덮어쓸 길이 없다 — 파일을 찾지 않기 때문이다
//! 도움말을 읽어도 프로젝트에 파일이 하나도 생기지 않는다
//! ```
//!
//! **source 파일의 자리는 공개 계약이 아니다.** 주소는 front matter 의 `id` 가 정하고,
//! 폴더를 옮겨도 주소는 그대로다(§11).
//!
//! # 원본을 복제하지 않는다
//!
//! 필수 Report 칸은 Topic 본문에 손으로 적지 않고 **Grammar 에서 투영한다**(§6). 본문의
//! `{{close_requires:<cycle>/<kind>}}` 한 줄이 그 자리를 가리키고, 읽는 순간
//! `gil-spec.yaml` 이 답한다. 두 자리에 적으면 한쪽이 낡는다.

mod id;
mod router;
mod when;

use std::collections::BTreeMap;
use std::fmt;

use serde::Deserialize;

use crate::contract::CloseContract;
use crate::cycle::CycleKind;
use crate::node::NodeKind;
use crate::rules::{RuleSet, SpecError};
use crate::session::{ProjectSession, WorldState};

pub(crate) use id::{TopicId, TopicIdError};
pub use router::{Refusal, Usage, more_about, with_help};
pub(crate) use when::{Condition, Confirmation, Inside, ManualContext, WhenError, WorldMark};

/// 함께 실린 Topic 들.
///
/// **여기 있는 것은 파일을 가리키는 줄뿐이다.** 본문은 `.md` 에 산다 — Topic 하나가
/// 늘 때 여기 한 줄과 파일 하나가 늘고, 이 파일의 다른 코드는 그대로다.
const SOURCES: &[&str] = &[
    include_str!("topics/current.md"),
    include_str!("topics/step/verify/close.md"),
    include_str!("topics/artifact/restore.md"),
    include_str!("topics/artifact/dirty/non-verify.md"),
    include_str!("topics/action/open-contract.md"),
    include_str!("topics/cycle/experiment/close.md"),
    include_str!("topics/cycle/revisit.md"),
    include_str!("topics/cycle/revisit/target.md"),
];

/// 본문이 Grammar 를 가리키는 표시 — **여는 괄호와 닫는 괄호.**
///
/// 이름은 아래 [`fill`] 이 아는 셋뿐이다. 모르는 이름은 조용히 지우지 않고 그 사실을 적는다.
const OPEN: &str = "{{";
const CLOSE: &str = "}}";

// ── Topic ──────────────────────────────────────────────────────────────────

/// front matter 로 읽는 값들 — **이번에 필요한 최소 계약만.**
#[derive(Debug, Deserialize)]
struct FrontMatter {
    id: String,
    title: String,
    summary: String,
    /// 코어가 이미 판정한 상태의 짧은 표지. **새 전이 엔진이 아니다**(§6).
    ///
    /// `None` 은 **필드가 없다** — 모든 상태에 적용된다는 뜻이다.
    /// `Some(빈 map)` 은 `applies_when: {}` 이고, 그것은 자국이지 뜻이 아니다.
    ///
    /// 값을 `Value` 로 받는 이유: 글자가 아닌 값을 **여기서 명시적으로** 거절하기 위해서다.
    /// `String` 으로 받으면 거절 여부가 serde 의 관대함에 달린다.
    applies_when: Option<BTreeMap<String, serde_norway::Value>>,
    #[serde(default)]
    related: Vec<String>,
    #[serde(default)]
    examples: Vec<String>,
    /// 옛 주소. 언제나 canonical Topic 하나로 끝나야 한다(§4).
    #[serde(default)]
    aliases: Vec<String>,
}

/// Topic 하나.
#[derive(Debug, Clone)]
pub(crate) struct Topic {
    id: TopicId,
    title: String,
    summary: String,
    /// 적힌 조건만 AND 로 잰다. 비어 있으면 **모든 상태**에 적용된다.
    applies_when: Vec<Condition>,
    related: Vec<TopicId>,
    examples: Vec<TopicId>,
    aliases: Vec<TopicId>,
    /// `[이름]` 절들 — 적힌 차례 그대로.
    sections: Vec<(String, String)>,
}

impl Topic {
    pub(crate) fn title(&self) -> &str {
        &self.title
    }

    pub(crate) fn summary(&self) -> &str {
        &self.summary
    }

    /// 적힌 조건들. 비어 있으면 모든 상태에 적용된다. **아직 시험만 쓴다.**
    #[cfg(test)]
    pub(crate) fn applies_when(&self) -> &[Condition] {
        &self.applies_when
    }

    /// 지금 상태에 **모든 조건이** 맞는가. 조건이 없으면 언제나 맞다.
    pub(crate) fn applies_to(&self, here: &ManualContext) -> bool {
        self.applies_when.iter().all(|when| when.holds(here))
    }

    pub(crate) fn sections(&self) -> impl Iterator<Item = (&str, &str)> {
        self.sections
            .iter()
            .map(|(name, body)| (name.as_str(), body.as_str()))
    }

    // 아래 둘은 **아직 시험만 쓴다.** 상태 기반 `gil help` 가 다음 조각이고, 쓰는 자리도
    // 없이 표면을 넓히지 않는다(§1).

    #[cfg(test)]
    pub(crate) fn id(&self) -> &TopicId {
        &self.id
    }

    #[cfg(test)]
    pub(crate) fn section(&self, name: &str) -> Option<&str> {
        self.sections
            .iter()
            .find(|(found, _)| found == name)
            .map(|(_, body)| body.as_str())
    }
}

/// 하나의 source 를 Topic 으로 읽는다 — front matter 와 본문을 가른다.
///
/// 형식은 하나뿐이다: `---` 줄 · YAML · `---` 줄 · Markdown 본문. 범용 Markdown AST 도
/// Wiki 엔진도 필요 없다 — 여기서 알아야 하는 것은 절의 경계뿐이다.
fn read(source: &str) -> Result<Topic, ManualError> {
    let rest = source
        .strip_prefix("---\n")
        .ok_or(ManualError::NoFrontMatter)?;
    let (matter, body) = rest
        .split_once("\n---\n")
        .ok_or(ManualError::UnterminatedFrontMatter)?;

    let front: FrontMatter =
        serde_norway::from_str(matter).map_err(|source| ManualError::BadFrontMatter {
            said: source.to_string(),
        })?;

    let address = |text: &str| {
        TopicId::parse(text).map_err(|source| ManualError::BadAddress {
            value: text.to_string(),
            source,
        })
    };

    Ok(Topic {
        id: address(&front.id)?,
        title: front.title,
        summary: front.summary,
        applies_when: conditions(front.applies_when)?,
        related: front
            .related
            .iter()
            .map(|text| address(text))
            .collect::<Result<_, _>>()?,
        examples: front
            .examples
            .iter()
            .map(|text| address(text))
            .collect::<Result<_, _>>()?,
        aliases: front
            .aliases
            .iter()
            .map(|text| address(text))
            .collect::<Result<_, _>>()?,
        sections: sections(body),
    })
}

/// front matter 의 표지들을 조건으로 읽는다.
///
/// **적힌 차례가 아니라 key 차례**로 세운다(`BTreeMap`). 같은 뜻의 두 Topic 이 적은 차례
/// 때문에 다르게 정렬되지 않게.
fn conditions(
    declared: Option<BTreeMap<String, serde_norway::Value>>,
) -> Result<Vec<Condition>, ManualError> {
    let Some(declared) = declared else {
        // 필드가 없다 — 모든 상태에 적용된다.
        return Ok(Vec::new());
    };
    if declared.is_empty() {
        return Err(ManualError::BadMarker {
            source: WhenError::Empty,
        });
    }

    let mut out = Vec::with_capacity(declared.len());
    for (key, value) in declared {
        let text = value.as_str().ok_or(ManualError::BadMarker {
            source: WhenError::NotText { key: key.clone() },
        })?;
        out.push(Condition::parse(&key, text).map_err(|source| ManualError::BadMarker { source })?);
    }
    Ok(out)
}

/// `[이름]` 으로 시작하는 줄에서 절을 가른다.
///
/// 그 앞에 오는 글은 절에 들어가지 않는다 — Topic 은 절로만 이루어진다(§5).
fn sections(body: &str) -> Vec<(String, String)> {
    let mut out: Vec<(String, String)> = Vec::new();
    for line in body.lines() {
        match line
            .strip_prefix('[')
            .and_then(|rest| rest.strip_suffix(']'))
            .filter(|name| !name.is_empty())
        {
            Some(name) => out.push((name.to_string(), String::new())),
            None => {
                if let Some((_, body)) = out.last_mut() {
                    body.push_str(line);
                    body.push('\n');
                }
            }
        }
    }
    for (_, body) in &mut out {
        *body = body.trim_matches('\n').to_string();
    }
    out
}

// ── index ──────────────────────────────────────────────────────────────────

/// 검증된 Topic 목록 — **주소 하나가 Topic 하나로 끝난다.**
#[derive(Debug, Clone)]
pub(crate) struct Manual {
    topics: Vec<Topic>,
    /// 옛 주소 → canonical 주소. 이미 한 칸으로 눌러 두었다.
    aliases: BTreeMap<TopicId, TopicId>,
}

impl Manual {
    /// 바이너리에 묶인 Topic 들.
    ///
    /// **본문을 여기서 펼치지 않는다.** index 를 세우는 것과 LLM context 에 본문을 싣는
    /// 것은 다른 일이다(§3.2).
    pub(crate) fn bundled() -> Result<Manual, ManualError> {
        Manual::from_sources(SOURCES)
    }

    pub(crate) fn from_sources(sources: &[&str]) -> Result<Manual, ManualError> {
        let mut topics: Vec<Topic> = Vec::with_capacity(sources.len());
        for source in sources {
            let topic = read(source)?;
            // ① 같은 주소가 두 Topic 을 가리킬 수 없다.
            if topics.iter().any(|seen| seen.id == topic.id) {
                return Err(ManualError::DuplicateId { id: topic.id });
            }
            topics.push(topic);
        }

        let known = |id: &TopicId| topics.iter().any(|topic| &topic.id == id);

        // ② alias 는 **다른 뜻의 독립 Topic 이름을 가로챌 수 없다.**
        let mut aliases: BTreeMap<TopicId, TopicId> = BTreeMap::new();
        for topic in &topics {
            for alias in &topic.aliases {
                if known(alias) {
                    return Err(ManualError::AliasIsATopic {
                        alias: alias.clone(),
                    });
                }
                if let Some(first) = aliases.get(alias) {
                    return Err(ManualError::AliasSplits {
                        alias: alias.clone(),
                        first: first.clone(),
                        second: topic.id.clone(),
                    });
                }
                aliases.insert(alias.clone(), topic.id.clone());
            }
        }
        // ③ alias 는 언제나 실재하는 canonical Topic 하나로 끝난다. 위 두 검사가 있으므로
        //    alias 가 alias 를 가리킬 수 없고, 따라서 순환도 생길 수 없다 — 그래도
        //    **그 사실을 여기서 확인한다.** 구조가 바뀌면 이 줄이 먼저 빨개진다.
        for (alias, target) in &aliases {
            if !known(target) {
                return Err(ManualError::DanglingAlias {
                    alias: alias.clone(),
                    target: target.clone(),
                });
            }
            if aliases.contains_key(target) {
                return Err(ManualError::AliasCycle {
                    alias: alias.clone(),
                });
            }
        }

        // ④ 가리키는 주소가 전부 실재하는가.
        for topic in &topics {
            for related in &topic.related {
                if !known(related) {
                    return Err(ManualError::BrokenLink {
                        from: topic.id.clone(),
                        to: related.clone(),
                        field: "related",
                    });
                }
            }
            for example in &topic.examples {
                // 예제는 아직 Topic 으로 실리지 않는다. **주소가 주소인지**만 이미 확인했고,
                // 그 주소가 이 Topic 을 가리키는지는 여기서 본다 — 남의 Topic 을 예제라고
                // 부르면 두 뜻이 한 주소를 나눠 쓰게 된다.
                if known(example) && example != &topic.id {
                    return Err(ManualError::ExampleIsAnotherTopic {
                        from: topic.id.clone(),
                        to: example.clone(),
                    });
                }
            }
        }

        Ok(Manual { topics, aliases })
    }

    /// 그 주소의 Topic — alias 면 따라간다.
    pub(crate) fn resolve(&self, id: &TopicId) -> Option<&Topic> {
        let canonical = self.aliases.get(id).unwrap_or(id);
        self.topics.iter().find(|topic| &topic.id == canonical)
    }

    #[cfg(test)]
    pub(crate) fn topics(&self) -> &[Topic] {
        &self.topics
    }
}

// ── 사람이 읽는 꼴 ─────────────────────────────────────────────────────────

/// Topic 하나를 사람이 읽는 글로 편다.
///
/// **front matter 는 내보내지 않는다.** `id`·`applies_when` 은 Topic 을 고르는 데 쓰는
/// 기계 표지이지 읽는 사람이 볼 것이 아니다(§3.2).
pub(crate) fn render(topic: &Topic, rules: &RuleSet) -> String {
    let mut out = format!("{}\n{}\n", topic.title(), topic.summary());
    for (name, body) in topic.sections() {
        out.push_str(&format!("\n[{name}]\n"));
        out.push_str(&project(body, rules));
        out.push('\n');
    }
    out
}

/// 본문의 `{{…}}` 한 줄을 **지금 Grammar** 로 채운다.
///
/// 채우지 못하면 그 줄을 조용히 지우지 않는다 — 지우면 필수 칸이 없는 것처럼 읽힌다.
fn project(body: &str, rules: &RuleSet) -> String {
    let mut out = String::with_capacity(body.len());
    for line in body.lines() {
        match directive(line) {
            None => out.push_str(line),
            Some(said) => out.push_str(&fill(said, rules)),
        }
        out.push('\n');
    }
    out.trim_end_matches('\n').to_string()
}

fn directive(line: &str) -> Option<&str> {
    line.trim().strip_prefix(OPEN)?.strip_suffix(CLOSE)
}

/// **투영은 셋뿐이다.** 셋 다 이미 있는 읽는 자리에 물어보고, 여기서 문법을 다시 읽지 않는다.
///
/// ```text
/// open_requires                    실행형 자리를 여는 행동 계약의 칸들
/// close_requires:<cycle>/<kind>    그 Step 을 닫는 데 필요한 칸들
/// close_contract:<cycle>           그 Cycle 을 닫는 계약 — 칸과 허용값과 그 뜻까지
/// ```
///
/// 마지막 것은 `gil close --help` 와 **같은 renderer**([`CloseContract`])를 쓴다. 그래서
/// 허용값·좁혀진 갈래·「아직 없음」이 화면과 Topic 에서 갈릴 수 없다.
fn fill(said: &str, rules: &RuleSet) -> String {
    let (name, argument) = match said.split_once(':') {
        Some((name, argument)) => (name, argument),
        None => (said, ""),
    };
    match name {
        "open_requires" => listed(crate::will::CONTRACT_FIELDS.iter().copied()),
        "close_requires" => close_requires(argument, rules),
        "close_contract" => close_contract(argument, rules),
        // **조용히 지우지 않는다.** 모르는 표시가 빈 줄이 되면 그 자리에 있어야 할 것이
        // 없다는 사실이 사라진다.
        _ => unfilled(&format!("{name:?} 라는 투영은 이 gil 이 모른다")),
    }
}

fn listed<'a>(fields: impl Iterator<Item = &'a str>) -> String {
    fields
        .map(|field| format!("      {field}"))
        .collect::<Vec<_>>()
        .join("\n")
}

fn unfilled(why: &str) -> String {
    format!("      ({why})")
}

/// 그 Step 을 닫는 데 필요한 칸들 — **Grammar 가 답한다.**
fn close_requires(address: &str, rules: &RuleSet) -> String {
    let Some((cycle, kind)) = address
        .split_once('/')
        .and_then(|(cycle, kind)| Some((CycleKind::parse(cycle)?, NodeKind::parse(kind)?)))
    else {
        return unfilled(&format!("문법에서 {address:?} 를 찾지 못했다"));
    };
    match rules.rules(cycle, kind) {
        None => unfilled(&format!("문법에 {address:?} 가 없다")),
        Some(step) => listed(step.close_requires.iter().map(String::as_str)),
    }
}

/// 그 Cycle 을 닫는 계약 전부 — 칸·허용값·값의 뜻·좁혀진 갈래·아직 없는 값.
fn close_contract(name: &str, rules: &RuleSet) -> String {
    let Some(kind) = CycleKind::parse(name) else {
        return unfilled(&format!("{name:?} 는 이 gil 이 아는 Cycle 종류가 아니다"));
    };
    match CloseContract::of_cycle(rules, kind, name) {
        None => unfilled(&format!("문법에 {name:?} Cycle 이 없다")),
        Some(contract) => contract.constraints("    ").trim_end().to_string(),
    }
}

// ── 지금 상태에 맞는 Topic 고르기 ──────────────────────────────────────────

/// 기본 `gil help` 가 한 번에 보여 주는 최대 개수.
///
/// 여기 닿는 일은 지금 없다(Topic 이 넷이다). 그래도 규칙은 **결정적으로** 둔다 — 나중에
/// 늘었을 때 「몇 개까지였더라」를 그때 정하면 그 결정이 화면 모양에 끌려간다.
const MOST: usize = 5;

/// 지금 상태에 **모든 조건이 맞는** Topic 만.
///
/// 최소 개수를 채우려고 관련 없는 것을 끼워 넣지 않는다. 0개도, 1개도 답이다.
///
/// 차례:
///
/// ```text
/// ① 조건이 많은 것 — 더 구체적인 Topic 이 먼저다
/// ② 같으면 주소 오름차순 — 실행마다 흔들리지 않게
/// ```
///
/// 조건이 없는 [`current`] 는 ①에 의해 자연히 맨 뒤로 간다. 「현재 행동과 직접 연결」을
/// 재는 별도 표지는 두지 않았다 — 네 Topic 의 기대 차례가 이 두 열쇠로 전부 맞고,
/// 맞는 규칙 중 가장 단순한 것을 고른다.
pub(crate) fn select<'a>(manual: &'a Manual, here: &ManualContext) -> Selection<'a> {
    let mut chosen: Vec<&Topic> = manual
        .topics
        .iter()
        .filter(|topic| topic.applies_to(here))
        .collect();

    chosen.sort_by(|left, right| {
        right
            .applies_when
            .len()
            .cmp(&left.applies_when.len())
            .then_with(|| left.id.cmp(&right.id))
    });

    let hidden = chosen.len().saturating_sub(MOST);
    chosen.truncate(MOST);
    Selection {
        topics: chosen,
        hidden,
    }
}

/// 고른 것과, 자리가 모자라 **잘라 낸 수**.
pub(crate) struct Selection<'a> {
    pub(crate) topics: Vec<&'a Topic>,
    pub(crate) hidden: usize,
}

// ── 공개 문 ────────────────────────────────────────────────────────────────

/// 지금 프로젝트 상태를 **한 번 읽어** Topic 을 고르는 표지로 만든다.
///
/// `world_state()` 를 정확히 한 번 부른다. Topic 을 재는 동안 다시 읽지 않는다 — 네 Topic 에
/// 네 번 폴더를 훑으면 도움말 하나가 프로젝트 전체를 네 번 읽는 명령이 된다.
pub fn help_here(session: &ProjectSession) -> Result<String, HelpError> {
    let world = match session.world_state() {
        Ok(WorldState::Clean { .. }) => WorldMark::Clean,
        Ok(WorldState::Dirty { .. }) => WorldMark::Dirty,
        // **모르는 것은 dirty 가 아니다.** 관측이 안 됐다고 바뀌었다고 말하지 않는다.
        Ok(WorldState::Unknown { .. }) => WorldMark::Unknown,
        Err(source) => {
            return Err(HelpError::State {
                said: source.to_string(),
            });
        }
    };

    let project = session.project();
    let cycle = project.cycles().current();
    let walk = cycle.steps();
    let here = ManualContext::within(Inside {
        cycle_kind: cycle.kind(),
        cycle_status: cycle.status(),
        step: walk
            .current()
            .and_then(|at| walk.node(at))
            .map(|node| (node.kind, node.status)),
        world,
        // 판정을 여기서 다시 짓지 않는다 — 코어의 Verify 판정 하나를 그대로 쓴다.
        confirmation: match session.can_confirm_artifact() {
            true => Confirmation::Verify,
            false => Confirmation::Unavailable,
        },
    });

    let manual = Manual::bundled().map_err(|source| HelpError::Broken {
        said: source.to_string(),
    })?;
    Ok(index(&select(&manual, &here), Some(world)))
}

/// 프로젝트 밖의 `gil help` — **Bootstrap 과 시작 Topic 하나.**
///
/// `.gil` 을 만들지도, 위로 무리하게 거슬러 오르지도 않는다.
pub fn help_outside() -> Result<String, HelpError> {
    let manual = Manual::bundled().map_err(|source| HelpError::Broken {
        said: source.to_string(),
    })?;
    let chosen = select(&manual, &ManualContext::outside());

    let mut out = String::from("GIL 도움말\n\n현재 프로젝트가 없다.\n\n시작\n");
    for topic in &chosen.topics {
        out.push_str(&format!("  gil help {}\n", topic.id));
    }
    Ok(out)
}

/// 고른 Topic 들의 **주소와 한 줄 요약만.**
///
/// 본문을 자동으로 펼치지 않는다(§3.2). 펼치면 「필요한 하나만 읽는다」가 「매번 다 읽는다」가
/// 되고, 그것이 이 Manual 이 피하려던 바로 그것이다.
fn index(chosen: &Selection<'_>, world: Option<WorldMark>) -> String {
    if chosen.topics.is_empty() {
        return String::from(
            "지금 상태에 특별히 관련된 도움말이 없다.\n\n읽기\n  gil help <주제>\n",
        );
    }

    let mut out = String::from("현재 상태에 관련된 도움말\n\n");
    for topic in &chosen.topics {
        out.push_str(&format!("{}\n  {}\n\n", topic.id, topic.summary));
    }
    if chosen.hidden > 0 {
        out.push_str(&format!("… 그리고 {} 개 더\n\n", chosen.hidden));
    }
    // 세계를 못 본 것은 **짧게** 말한다. 까닭 전체는 `gil status` 가 이미 말한다.
    if world == Some(WorldMark::Unknown) {
        out.push_str("세계를 확인하지 못해 일부 주제를 고르지 못했다 — 까닭은 `gil status`.\n\n");
    }
    out.push_str("읽기\n  gil help <주제>\n");
    out
}

/// `gil help <주소>` — **프로젝트가 없어도 답한다.**
///
/// `.gil` 을 찾지도, 잠금을 잡지도, 상태를 읽지도 않는다. 도움말은 도구의 지식이지
/// 프로젝트의 기록이 아니다(§8).
pub fn help_topic(input: &str) -> Result<String, HelpError> {
    let id = TopicId::parse(input).map_err(|source| HelpError::NotAnAddress {
        input: input.to_string(),
        why: source.to_string(),
    })?;
    let manual = Manual::bundled().map_err(|source| HelpError::Broken {
        said: source.to_string(),
    })?;
    let topic = manual.resolve(&id).ok_or_else(|| HelpError::NoSuchTopic {
        input: input.to_string(),
    })?;
    let rules = RuleSet::builtin().map_err(HelpError::NoGrammar)?;
    Ok(render(topic, &rules))
}

/// 도움말을 주지 못한 이유.
///
/// **「주소가 아니다」와 「그런 Topic 이 없다」는 다른 일이다.** 앞의 것은 글자를 고치는
/// 문제이고, 뒤의 것은 그 주제가 아직 없다는 사실이다.
///
/// 주소 타입과 index 는 **안에 남는다**(§1). 밖으로 나가는 것은 이미 사람의 말로 적힌
/// 이유뿐이다 — 내보내면 내부 이름이 공개 계약이 된다.
#[derive(Debug)]
pub enum HelpError {
    NotAnAddress { input: String, why: String },
    NoSuchTopic { input: String },
    Broken { said: String },
    NoGrammar(SpecError),
    /// 지금 상태를 읽지 못했다 — 그 위에서 Topic 을 고를 수 없다.
    State { said: String },
}

impl fmt::Display for HelpError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            HelpError::NotAnAddress { input, why } => {
                write!(f, "{input:?} 는 도움말 주제의 주소가 아니다 — {why}")
            }
            // 무관한 전체 목록을 늘어놓지 않는다. 여기서 필요한 것은 그 주제가 없다는 사실뿐이다.
            HelpError::NoSuchTopic { input } => {
                write!(f, "그 도움말 주제는 없다: {input}")
            }
            HelpError::Broken { said } => {
                write!(f, "함께 실린 도움말이 온전하지 않다 — {said}")
            }
            HelpError::NoGrammar(source) => {
                write!(f, "함께 실린 명세를 읽지 못했다 — {source}")
            }
            HelpError::State { said } => write!(f, "{said}"),
        }
    }
}

impl std::error::Error for HelpError {}

/// 함께 실린 Manual 이 온전하지 않은 이유. **전부 빌드가 잡아야 하는 것들이다.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ManualError {
    NoFrontMatter,
    UnterminatedFrontMatter,
    BadFrontMatter {
        said: String,
    },
    BadAddress {
        value: String,
        source: TopicIdError,
    },
    DuplicateId {
        id: TopicId,
    },
    BrokenLink {
        from: TopicId,
        to: TopicId,
        field: &'static str,
    },
    ExampleIsAnotherTopic {
        from: TopicId,
        to: TopicId,
    },
    AliasIsATopic {
        alias: TopicId,
    },
    AliasSplits {
        alias: TopicId,
        first: TopicId,
        second: TopicId,
    },
    DanglingAlias {
        alias: TopicId,
        target: TopicId,
    },
    AliasCycle {
        alias: TopicId,
    },
    BadMarker {
        source: WhenError,
    },
}

impl fmt::Display for ManualError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ManualError::NoFrontMatter => write!(f, "Topic 이 front matter 로 시작하지 않는다"),
            ManualError::UnterminatedFrontMatter => {
                write!(f, "front matter 가 닫히지 않았다")
            }
            ManualError::BadFrontMatter { said } => {
                write!(f, "front matter 를 읽지 못했다 — {said}")
            }
            ManualError::BadAddress { value, source } => {
                write!(f, "{value:?} 는 주소가 아니다 — {source}")
            }
            ManualError::DuplicateId { id } => write!(
                f,
                "{id} 를 두 Topic 이 나눠 쓴다 — 한 주소는 한 Topic 이다"
            ),
            ManualError::BrokenLink { from, to, field } => {
                write!(f, "{from} 의 {field} 가 없는 주소 {to} 를 가리킨다")
            }
            ManualError::ExampleIsAnotherTopic { from, to } => write!(
                f,
                "{from} 이(가) 다른 Topic {to} 를 제 예제라고 한다 — 두 뜻이 한 주소를 \
                 나눠 쓰게 된다"
            ),
            ManualError::AliasIsATopic { alias } => write!(
                f,
                "{alias} 는 이미 다른 뜻의 Topic 이다 — 배포된 주소를 다른 뜻으로 \
                 다시 쓰지 않는다"
            ),
            ManualError::AliasSplits {
                alias,
                first,
                second,
            } => write!(
                f,
                "{alias} 가 {first} 와 {second} 둘을 가리킨다 — alias 는 canonical Topic \
                 하나로 끝나야 한다"
            ),
            ManualError::DanglingAlias { alias, target } => {
                write!(f, "{alias} 가 없는 Topic {target} 를 가리킨다")
            }
            ManualError::AliasCycle { alias } => write!(
                f,
                "{alias} 가 또 다른 alias 를 가리킨다 — alias 는 돌지 않는다"
            ),
            ManualError::BadMarker { source } => write!(f, "{source}"),
        }
    }
}

impl std::error::Error for ManualError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::node::NodeStatus;

    fn id(text: &str) -> TopicId {
        TopicId::parse(text).expect("시험이 쓰는 주소는 canonical 이다")
    }

    /// front matter 와 절 하나를 가진 최소 Topic.
    fn source(id: &str, extra: &str) -> String {
        format!(
            "---\nid: {id}\ntitle: 제목\nsummary: 한 줄\n{extra}---\n\n[언제 읽는가]\n  지금\n"
        )
    }

    #[test]
    fn the_bundled_manual_is_whole() {
        let manual = Manual::bundled().expect("함께 실린 Manual 은 언제나 온전하다");
        assert_eq!(manual.topics().len(), SOURCES.len());
    }

    #[test]
    fn every_topic_file_is_actually_bundled() {
        // `SOURCES` 에 줄 하나를 빠뜨리면 그 Topic 은 **조용히 없는 것이 된다.**
        // 파일은 저장소에 있는데 설치본이 모르는 상태가 가장 나쁘다.
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("src/manual/topics");
        let mut found: Vec<String> = Vec::new();
        collect(&root, &mut found);
        found.sort();

        let manual = Manual::bundled().unwrap();
        assert_eq!(
            found.len(),
            manual.topics().len(),
            "topics 폴더의 파일 수와 실린 Topic 수가 다르다: {found:?}"
        );
    }

    fn collect(at: &std::path::Path, out: &mut Vec<String>) {
        for entry in std::fs::read_dir(at).expect("topics 폴더를 읽는다") {
            let path = entry.expect("한 자리").path();
            match path.is_dir() {
                true => collect(&path, out),
                false if path.extension().is_some_and(|kind| kind == "md") => {
                    out.push(path.display().to_string())
                }
                false => {}
            }
        }
    }

    #[test]
    fn a_topic_without_front_matter_is_refused() {
        assert_eq!(
            Manual::from_sources(&["[언제 읽는가]\n  지금\n"]).unwrap_err(),
            ManualError::NoFrontMatter
        );
        assert_eq!(
            Manual::from_sources(&["---\nid: current\n"]).unwrap_err(),
            ManualError::UnterminatedFrontMatter
        );
    }

    #[test]
    fn a_topic_whose_declared_id_is_not_an_address_is_refused() {
        // **선언된 id 가 주소다.** 파일이 어디 있든 상관없다.
        let err = Manual::from_sources(&[&source("Current", "")]).unwrap_err();
        assert!(matches!(err, ManualError::BadAddress { .. }), "{err}");
    }

    #[test]
    fn two_topics_cannot_share_one_address() {
        let err = Manual::from_sources(&[&source("current", ""), &source("current", "")])
            .unwrap_err();
        assert_eq!(err, ManualError::DuplicateId { id: id("current") });
    }

    #[test]
    fn a_link_that_points_nowhere_is_refused() {
        let err = Manual::from_sources(&[&source("current", "related:\n  - no/such/topic\n")])
            .unwrap_err();
        assert_eq!(
            err,
            ManualError::BrokenLink {
                from: id("current"),
                to: id("no/such/topic"),
                field: "related",
            }
        );
    }

    #[test]
    fn an_example_cannot_be_another_topic() {
        let err = Manual::from_sources(&[
            &source("current", "examples:\n  - artifact/restore\n"),
            &source("artifact/restore", ""),
        ])
        .unwrap_err();
        assert_eq!(
            err,
            ManualError::ExampleIsAnotherTopic {
                from: id("current"),
                to: id("artifact/restore"),
            }
        );
    }

    #[test]
    fn an_alias_ends_at_exactly_one_canonical_topic() {
        let manual = Manual::from_sources(&[
            &source("artifact/restore", "aliases:\n  - restore\n  - world/restore\n"),
        ])
        .expect("alias 둘이 한 Topic 으로 끝난다");

        for alias in ["restore", "world/restore", "artifact/restore"] {
            assert_eq!(
                manual.resolve(&id(alias)).expect(alias).id(),
                &id("artifact/restore"),
                "{alias}"
            );
        }
    }

    #[test]
    fn an_alias_cannot_take_over_a_topic_that_means_something_else() {
        let err = Manual::from_sources(&[
            &source("current", "aliases:\n  - artifact/restore\n"),
            &source("artifact/restore", ""),
        ])
        .unwrap_err();
        assert_eq!(
            err,
            ManualError::AliasIsATopic {
                alias: id("artifact/restore"),
            }
        );
    }

    #[test]
    fn one_alias_cannot_point_at_two_topics() {
        let err = Manual::from_sources(&[
            &source("current", "aliases:\n  - here\n"),
            &source("artifact/restore", "aliases:\n  - here\n"),
        ])
        .unwrap_err();
        assert_eq!(
            err,
            ManualError::AliasSplits {
                alias: id("here"),
                first: id("current"),
                second: id("artifact/restore"),
            }
        );
    }

    #[test]
    fn an_alias_that_points_at_nothing_is_refused() {
        // 선언한 Topic 이 사라지면 그 alias 는 어디로도 가지 않는다. 구조가 바뀌어 alias 가
        // alias 를 가리키게 되면 순환 검사가 먼저 빨개진다.
        let mut manual = Manual::from_sources(&[&source("current", "aliases:\n  - here\n")])
            .expect("한 Topic 과 그 alias");
        manual.topics.clear();

        let alias = id("here");
        assert!(manual.resolve(&alias).is_none(), "없는 Topic 이 답했다");
    }

    #[test]
    fn the_sections_come_out_in_the_order_they_were_written() {
        let topic = read(
            "---\nid: current\ntitle: 제목\nsummary: 한 줄\n---\n\n\
             앞말은 절이 아니다\n\n[언제 읽는가]\n  지금\n\n[지금 할 일]\n  이것\n",
        )
        .expect("읽는다");

        let names: Vec<&str> = topic.sections().map(|(name, _)| name).collect();
        assert_eq!(names, vec!["언제 읽는가", "지금 할 일"]);
        assert_eq!(topic.section("지금 할 일"), Some("  이것"));
        // 절 밖의 글은 어디에도 실리지 않는다.
        assert!(!topic.sections().any(|(_, body)| body.contains("앞말")));
    }

    // ── Grammar 투영 ──────────────────────────────────────────────────────

    #[test]
    fn the_required_fields_come_from_the_grammar_not_the_prose() {
        let rules = RuleSet::builtin().expect("함께 실린 명세");
        let filled = project("{{close_requires:experiment/verify}}", &rules);

        let declared = rules
            .rules(CycleKind::Experiment, NodeKind::Verify)
            .expect("문법이 verify 를 선언한다");
        assert!(!declared.close_requires.is_empty());
        for field in &declared.close_requires {
            assert!(filled.contains(field.as_str()), "{field} 가 빠졌다:\n{filled}");
        }
        // **verdict 는 verify 의 칸이 아니다.**
        assert!(!filled.contains("verdict"), "{filled}");
    }

    #[test]
    fn the_cycle_contract_comes_from_the_grammar_too() {
        let rules = RuleSet::builtin().expect("함께 실린 명세");
        let filled = project("{{close_contract:experiment}}", &rules);

        let declared = rules
            .cycle_rules(CycleKind::Experiment)
            .expect("문법이 experiment Cycle 을 선언한다");
        for field in &declared.close_requires {
            assert!(filled.contains(field.as_str()), "{field} 이 빠졌다:\n{filled}");
        }
        // 허용값과 좁혀진 갈래까지 **같은 renderer** 가 낸다.
        assert!(filled.contains("success"), "{filled}");
        assert!(filled.contains("failure"), "{filled}");
        assert!(filled.contains("verdict가 success이면"), "{filled}");
        assert!(filled.contains("open_child"), "{filled}");
        // Chain 은 Experiment 의 선택지가 아니다.
        assert!(!filled.contains("close_chain"), "{filled}");
    }

    #[test]
    fn the_contract_fields_are_the_ones_the_core_requires() {
        let rules = RuleSet::builtin().expect("함께 실린 명세");
        let filled = project("{{open_requires}}", &rules);
        for field in crate::will::CONTRACT_FIELDS {
            assert!(filled.contains(field), "{field} 이 빠졌다:\n{filled}");
        }
        assert_eq!(filled.lines().count(), crate::will::CONTRACT_FIELDS.len());
    }

    #[test]
    fn a_projection_this_gil_does_not_know_is_not_silently_erased() {
        let rules = RuleSet::builtin().expect("함께 실린 명세");
        for said in [
            "{{allowed_values:experiment/verdict}}",
            "{{close_contract:chain}}",
            "{{쓰레기}}",
        ] {
            let filled = project(said, &rules);
            assert!(!filled.trim().is_empty(), "{said} 에서 줄이 사라졌다");
            // 못 채웠다는 **사실이 남는다.** 빈 줄이 되면 그 자리에 있어야 할 것이
            // 없다는 것을 아무도 모른다.
            assert!(filled.starts_with("      ("), "{said}: {filled}");
            assert!(filled.contains("아니다") || filled.contains("모른다"), "{said}: {filled}");
        }
    }

    #[test]
    fn a_directive_that_points_nowhere_is_not_silently_erased() {
        // 조용히 지우면 필수 칸이 없는 것처럼 읽힌다.
        let rules = RuleSet::builtin().expect("함께 실린 명세");
        for address in ["experiment/nosuch", "nosuch/verify", "쓰레기"] {
            let filled = project(&format!("{{{{close_requires:{address}}}}}"), &rules);
            assert!(!filled.trim().is_empty(), "{address} 에서 줄이 사라졌다");
            assert!(filled.contains("문법"), "{address}: {filled}");
        }
    }

    // ── applies_when 계약 ─────────────────────────────────────────────────

    #[test]
    fn a_topic_with_no_marker_field_applies_everywhere() {
        let manual = Manual::from_sources(&[&source("current", "")]).expect("조건이 없다");
        let topic = manual.resolve(&id("current")).unwrap();
        assert!(topic.applies_when().is_empty());

        assert!(topic.applies_to(&ManualContext::outside()));
        assert!(topic.applies_to(&somewhere(None, WorldMark::Clean)));
        assert!(topic.applies_to(&somewhere(None, WorldMark::Unknown)));
    }

    #[test]
    fn an_empty_marker_map_is_a_mistake_not_a_meaning() {
        let err = Manual::from_sources(&[&source("current", "applies_when: {}\n")]).unwrap_err();
        assert_eq!(
            err,
            ManualError::BadMarker {
                source: WhenError::Empty
            }
        );
    }

    #[test]
    fn a_marker_this_gil_does_not_know_stops_the_index() {
        for (marker, expected) in [
            (
                "applies_when:\n  existence: X1\n",
                WhenError::UnknownKey {
                    key: "existence".to_string(),
                },
            ),
            (
                "applies_when:\n  world_state: messy\n",
                WhenError::UnknownValue {
                    key: "world_state".to_string(),
                    value: "messy".to_string(),
                },
            ),
        ] {
            assert_eq!(
                Manual::from_sources(&[&source("current", marker)]).unwrap_err(),
                ManualError::BadMarker { source: expected }
            );
        }
    }

    #[test]
    fn a_marker_value_that_is_not_text_stops_the_index() {
        // **truthiness 로 다루지 않는다.** 숫자도 참/거짓도 표지가 아니다.
        for marker in [
            "applies_when:\n  world_state: 3\n",
            "applies_when:\n  project: true\n",
            "applies_when:\n  step_kind:\n    - verify\n",
            "applies_when:\n  world_state: null\n",
        ] {
            let err = Manual::from_sources(&[&source("current", marker)]).unwrap_err();
            assert!(
                matches!(
                    err,
                    ManualError::BadMarker {
                        source: WhenError::NotText { .. }
                    }
                ),
                "{marker:?} 가 다른 이유로 거절됐다: {err}"
            );
        }
    }

    #[test]
    fn several_markers_are_all_required_not_any() {
        let manual = Manual::from_sources(&[&source(
            "artifact/dirty/non-verify",
            "applies_when:\n  project: present\n  world_state: dirty\n  artifact_confirmation: unavailable\n",
        )])
        .expect("세 조건");
        let topic = manual.resolve(&id("artifact/dirty/non-verify")).unwrap();
        assert_eq!(topic.applies_when().len(), 3);

        // 셋 다 맞을 때만 맞다.
        assert!(topic.applies_to(&somewhere(None, WorldMark::Dirty)));
        // 하나라도 어긋나면 아니다 — OR 이면 여기서 맞다고 한다.
        assert!(!topic.applies_to(&somewhere(None, WorldMark::Clean)));
        assert!(!topic.applies_to(&somewhere(
            Some((NodeKind::Verify, NodeStatus::Open)),
            WorldMark::Dirty
        )));
        assert!(!topic.applies_to(&ManualContext::outside()));
    }

    #[test]
    fn the_bundled_topics_are_chosen_in_a_fixed_order() {
        let manual = Manual::bundled().unwrap();
        let names = |here: &ManualContext| -> Vec<String> {
            select(&manual, here)
                .topics
                .iter()
                .map(|topic| topic.id.to_string())
                .collect()
        };

        // dirty Verify — 확정이 정상 경로이므로 그것이 먼저다.
        assert_eq!(
            names(&somewhere(
                Some((NodeKind::Verify, NodeStatus::Open)),
                WorldMark::Dirty
            )),
            vec!["step/verify/close", "artifact/restore", "current"]
        );
        // dirty 비-Verify — 되돌리는 것이 먼저다.
        assert_eq!(
            names(&somewhere(
                Some((NodeKind::Define, NodeStatus::Open)),
                WorldMark::Dirty
            )),
            vec!["artifact/dirty/non-verify", "artifact/restore", "current"]
        );
        // Step 이 없는 경계도 같다.
        assert_eq!(
            names(&somewhere(None, WorldMark::Dirty)),
            vec![
                "artifact/dirty/non-verify",
                "action/open-contract",
                "artifact/restore",
                "current"
            ]
        );
        // clean Verify.
        assert_eq!(
            names(&somewhere(
                Some((NodeKind::Verify, NodeStatus::Open)),
                WorldMark::Clean
            )),
            vec!["step/verify/close", "current"]
        );
        // clean 일반 — **채우지 않는다.**
        assert_eq!(
            names(&somewhere(
                Some((NodeKind::Define, NodeStatus::Open)),
                WorldMark::Clean
            )),
            vec!["current"]
        );
        // Experiment 의 **끝 경계** — 닫힌 Outcome 위에 서 있는 그 자리에서만.
        //
        // 여기서 적는 것이 Cycle Report 이고, 판정이 `failure` 면 되돌아갈 곳도 그때
        // 함께 확정된다. 그래서 두 Topic 이 같은 자리에 선다 — 조건 수가 같으므로
        // 주소 오름차순이 순서를 정한다.
        assert_eq!(
            names(&somewhere(
                Some((NodeKind::Outcome, NodeStatus::Closed)),
                WorldMark::Clean
            )),
            vec!["cycle/experiment/close", "cycle/revisit/target", "current"]
        );
        // 아직 아무것도 열지 않은 **시작 경계** — 여기서는 행동 계약이 다음 수다.
        assert_eq!(names(&somewhere(None, WorldMark::Clean)), vec!["action/open-contract", "current"]);
        // 세계를 못 봤으면 dirty 전용 Topic 이 나오지 않는다.
        assert_eq!(
            names(&somewhere(
                Some((NodeKind::Define, NodeStatus::Open)),
                WorldMark::Unknown
            )),
            vec!["current"]
        );
        // 프로젝트 밖.
        assert_eq!(names(&ManualContext::outside()), vec!["current"]);
    }

    #[test]
    fn the_list_is_cut_at_five_and_says_it_was_cut() {
        // 지금 Topic 이 넷이라 닿지 않는다. 그래도 규칙은 **결정적**이어야 한다.
        let many: Vec<String> = (0..8).map(|n| source(&format!("t{n}"), "")).collect();
        let borrowed: Vec<&str> = many.iter().map(String::as_str).collect();
        let manual = Manual::from_sources(&borrowed).expect("여덟 Topic");

        let chosen = select(&manual, &ManualContext::outside());
        assert_eq!(chosen.topics.len(), MOST);
        assert_eq!(chosen.hidden, 3);
        // 잘라 낸 자리도 주소 오름차순이다.
        let names: Vec<String> = chosen.topics.iter().map(|t| t.id.to_string()).collect();
        assert_eq!(names, vec!["t0", "t1", "t2", "t3", "t4"]);
        assert!(index(&chosen, None).contains("3 개 더"));
    }

    /// 프로젝트 안의 어떤 자리 하나.
    fn somewhere(
        step: Option<(NodeKind, NodeStatus)>,
        world: WorldMark,
    ) -> ManualContext {
        ManualContext::within(Inside {
            cycle_kind: CycleKind::Experiment,
            cycle_status: NodeStatus::Open,
            step,
            world,
            confirmation: match step {
                Some((NodeKind::Verify, NodeStatus::Open)) => Confirmation::Verify,
                _ => Confirmation::Unavailable,
            },
        })
    }

    #[test]
    fn choosing_topics_observes_the_project_exactly_once() {
        // **Topic 마다 다시 관측하지 않는다.** 네 Topic 에 네 번 폴더를 훑으면 도움말
        // 하나가 프로젝트를 네 번 읽는 명령이 된다.
        //
        // 관측기는 한 번의 `world_state()` 마다 두 번 훑는다(안정된 관측). 그러니 여기서
        // 재는 것은 「그 두 번이 정확히 한 벌」이라는 사실이다.
        let root = std::env::temp_dir().join("gil-manual-observe-once");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("a.txt"), "가").unwrap();

        let session = crate::ProjectSession::start(
            RuleSet::builtin().unwrap(),
            root.join(crate::STATE_PATH),
        )
        .expect("시작한다");
        session.commit().unwrap();

        let before = crate::artifact::scan_count::now();
        help_here(&session).expect("고른다");
        assert_eq!(
            crate::artifact::scan_count::now() - before,
            2,
            "Topic 을 고르며 프로젝트를 한 벌 넘게 훑었다"
        );
    }

    #[test]
    fn rendering_hides_the_front_matter() {
        let rules = RuleSet::builtin().expect("함께 실린 명세");
        let manual = Manual::bundled().unwrap();
        let topic = manual.resolve(&id("artifact/dirty/non-verify")).unwrap();
        let said = render(topic, &rules);

        for hidden in ["id:", "summary:", "applies_when", "related:", "---"] {
            assert!(!said.contains(hidden), "{hidden} 이 새어 나왔다:\n{said}");
        }
        assert!(said.starts_with(topic.title()), "{said}");
        assert!(said.contains(topic.summary()), "{said}");
    }
}
