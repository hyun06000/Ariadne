//! **비싼 관측을 언제 다시 할지 정하는 상태기계** — 그리고 마지막 사실을 잃지 않는 자리.
//!
//! server 도, watcher 도, thread 도 여기 없다. 이 파일이 아는 것은 셋뿐이다: 지금이 언제인가,
//! 무엇이 깨웠는가, 그리고 관측을 부르면 무엇이 돌아오는가.
//!
//! # 두 가지 주기를 가른다
//!
//! ```text
//! browser 가 화면을 다시 받는다   → 마지막으로 검증된 결과를 읽는다      값싸다
//! 파일이 바뀌었을지 모른다 / 기한  → ProjectSession → monitor() → 새 Snapshot   비싸다
//! ```
//!
//! `world_state()` 는 안정된 관측을 위해 Artifact 를 **두 번** 훑는다(Artifact Model §6).
//! 화면을 새로 받을 때마다 그것을 반복하면, 창을 열어 둔 것만으로 프로젝트 크기에 비례하는
//! 비용이 계속 나간다. 그래서 **화면을 읽는 일과 사실을 다시 재는 일을 분리한다.**
//!
//! # watcher event 는 사실이 아니다
//!
//! 경로도, 종류도, 순서도 저장하지 않는다. event 는 「다시 봐야 할지도 모른다」는 **hint**
//! 하나이고, 무엇이 참인지는 언제나 완전한 `monitor()` 조회가 정한다. 그래서 watcher 가
//! event 를 합치거나 놓쳐도 느린 기한 하나가 결국 수렴시킨다.
//!
//! # 실패는 사실을 지우지 않는다
//!
//! 관측이 실패해도 마지막으로 **성공한** Snapshot 은 그대로 남는다. 다만 그것을 지금 사실인
//! 것처럼 보이지 않게 상태가 `Stale` 로 바뀐다. 성공하면 이전 값을 **통째로** 새 Snapshot 으로
//! 갈아 끼운다 — 절마다 부분적으로 합치지 않는다. 합치면 화면의 두 칸이 서로 다른 시점을
//! 말하게 되고, 그것은 어느 시점의 사실도 아니다.
//!
//! # 시간은 밖에서 들어온다
//!
//! 이 파일에는 시계가 없다. 깨울 때마다 **그 순간 하나**를 받는다 — trait 로 시계를 주입하는
//! 것보다 강한 이음매다. 한 결정 안에서 시계를 두 번 물으면 두 값이 갈릴 수 있는데, 값 하나를
//! 받으면 그 일이 일어날 수 없다.
//!
//! # 아직 아무 명령도 이것을 부르지 않는다
//!
//! 이 조각(M5-A2a)은 **판정만** 짓는다. 그 판정을 실제로 깨울 loopback server 는 다음
//! 조각(A2b)이고, 파일 변화를 알려 줄 watcher 는 그 다음(A2c)이다. 셋이 다 서기 전에는
//! `gil monitor --serve` 를 열지 않는다 — 반쪽 기능을 표면에 내놓으면 사용자가 그것을
//! 믿게 되기 때문이다.
//!
//! 그래서 지금은 crate 안에서도 부르는 자리가 없고, 아래 `allow` 는 그 사실을 적어 둔
//! 것이다. **시험은 여기 있는 모든 것을 실제로 부른다** — 서지 않은 것은 표면뿐이다.
#![allow(dead_code)]

use std::time::Duration;

use super::MonitorSnapshot;
use super::html;

// ── 시간 ───────────────────────────────────────────────────────────────────

/// 단조 증가하는 논리적 시각.
///
/// 벽시계의 글자도, [`MonitorSnapshot::captured_at`] 도 아니다. 그 둘은 표시용이고, 여기서
/// 필요한 것은 **얼마나 지났는가**뿐이다.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord)]
pub(crate) struct Moment(Duration);

impl Moment {
    /// 시작점에서 이만큼 흐른 순간.
    pub(crate) fn at(millis: u64) -> Moment {
        Moment(Duration::from_millis(millis))
    }

    /// 그 사이에 흐른 시간. 뒤로 흐른 시각은 **0 으로 본다** — 시계가 뒤로 가더라도
    /// 기한이 영원히 오지 않는 일은 만들지 않는다.
    fn since(self, earlier: Moment) -> Duration {
        self.0.saturating_sub(earlier.0)
    }
}

/// 얼마나 자주 다시 볼 것인가 — **성능 parameter이지 도메인 계약이 아니다**(§8.3).
#[derive(Debug, Clone, Copy)]
pub(crate) struct Pace {
    /// 첫 hint 뒤 이만큼은 더 모았다가 한 번에 본다.
    pub(crate) debounce: Duration,
    /// hint 가 하나도 없어도 이만큼 지나면 다시 본다 — watcher 가 놓쳐도 수렴한다.
    pub(crate) reconcile: Duration,
    /// 실패한 뒤 이만큼 지나면 다시 본다 — 새 hint 가 없어도.
    pub(crate) retry: Duration,
}

impl Default for Pace {
    fn default() -> Pace {
        Pace {
            debounce: Duration::from_millis(200),
            reconcile: Duration::from_secs(30),
            retry: Duration::from_secs(2),
        }
    }
}

// ── 관측 ───────────────────────────────────────────────────────────────────

/// 비싼 관측 하나 — **시험이 대신 끼워 넣을 수 있는 자리.**
///
/// 실제 구현은 `ProjectSession::open` → `monitor()` → drop 을 지난다. 그 순서를 이 파일이
/// 알 필요는 없고, 알면 잠금과 파일이 이 상태기계로 새어 든다.
///
/// 오류를 글로 받는 까닭도 같다 — 이 계층은 무엇이 잘못됐는지 판정하지 않고, 화면에 그대로
/// 보일 **신뢰하지 않는 글** 하나로 다룬다.
pub(crate) trait Observe {
    /// 완전한 새 Snapshot 하나. **부분 결과를 돌려주지 않는다.**
    fn observe(&mut self) -> Result<MonitorSnapshot, String>;
}

/// 무엇이 깨웠는가.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum Wake {
    /// 파일 시스템이 무언가 바뀌었을지 모른다고 알렸다 — **사실이 아니라 hint 다.**
    ChangeHint,
    /// 시간이 흘렀다. 기한이 됐는지만 본다.
    Elapsed,
    /// browser 가 화면을 다시 받았다.
    ///
    /// **그 자체로는 재관측을 부르지 않는다.** 창을 열어 둔 것이 프로젝트를 계속 훑는
    /// 이유가 되어서는 안 된다.
    ScreenRead,
}

// ── 무엇을 쥐고 있는가 ─────────────────────────────────────────────────────

/// 마지막으로 검증된 것과, 그것이 지금 사실인지.
///
/// **진실 공급원이 아니다.** 화면 응답을 싸게 하려고 들고 있는 파생 값이고, Graph 에 쓰지
/// 않으며 다음 판정의 입력으로도 쓰지 않는다(§8.4).
#[derive(Debug, Clone)]
pub(crate) enum Cached {
    /// 마지막 관측이 성공했다.
    Current {
        snapshot: MonitorSnapshot,
        /// 그 관측이 성공한 시각.
        at: Moment,
    },
    /// 새 관측이 실패했다 — **지금 보이는 것은 그 전의 사실이다.**
    Stale {
        /// 마지막으로 **성공한** Snapshot. 실패가 이것을 고치지 않는다.
        snapshot: MonitorSnapshot,
        /// 그 Snapshot 이 성공한 시각.
        succeeded_at: Moment,
        /// 가장 최근 실패의 이유 — 신뢰하지 않는 글이다.
        error: String,
        failed_at: Moment,
    },
    /// 성공한 Snapshot 이 아직 하나도 없다.
    Unavailable { error: String, failed_at: Moment },
}

impl Cached {
    /// 지금 보여 줄 수 있는 Snapshot. `Unavailable` 이면 없다.
    pub(crate) fn snapshot(&self) -> Option<&MonitorSnapshot> {
        match self {
            Cached::Current { snapshot, .. } | Cached::Stale { snapshot, .. } => Some(snapshot),
            Cached::Unavailable { .. } => None,
        }
    }

    /// 지금 보이는 것이 최신인가.
    pub(crate) fn is_current(&self) -> bool {
        matches!(self, Cached::Current { .. })
    }
}

// ── 상태기계 ───────────────────────────────────────────────────────────────

/// 언제 다시 볼지 정하고, 마지막 사실을 지키는 자리.
#[derive(Debug)]
pub(crate) struct Refresh {
    pace: Pace,
    cached: Cached,
    /// 아직 합쳐지지 않은 hint 들 중 **첫 번째**가 온 시각.
    ///
    /// 매 hint 마다 다시 세지 않는다. 그렇게 하면 편집이 계속되는 동안 기한이 영원히
    /// 밀려 화면이 멈춘다. 첫 것을 쥐고 있으면 기다리는 시간에 상한이 생긴다.
    hinted: Option<Moment>,
    /// 마지막으로 관측을 **시도한** 시각. 성공이든 실패든 같다.
    looked: Moment,
}

impl Refresh {
    /// **첫 관측을 하고** 상태기계를 세운다.
    ///
    /// 「아직 아무것도 모른다」는 네 번째 상태를 만들지 않는다. 그런 자리를 두면 화면과
    /// 시험이 그것을 어떻게 그릴지 매번 물어야 하는데, 첫 관측의 답은 이미 셋 중 하나다.
    pub(crate) fn start(pace: Pace, now: Moment, observer: &mut (impl Observe + ?Sized)) -> Refresh {
        let cached = match observer.observe() {
            Ok(snapshot) => Cached::Current { snapshot, at: now },
            Err(error) => Cached::Unavailable {
                error,
                failed_at: now,
            },
        };
        Refresh {
            pace,
            cached,
            hinted: None,
            looked: now,
        }
    }

    pub(crate) fn cached(&self) -> &Cached {
        &self.cached
    }

    /// **깨어나서, 다시 볼 때가 됐으면 본다.**
    ///
    /// 무엇이 깨웠든 판정은 하나다 — [`Refresh::due`]. 깨운 이유마다 다른 규칙을 두면
    /// 「hint 로 깨면 보는데 시간으로 깨면 안 본다」 같은 자리가 생기고, 그러면 watcher 가
    /// 조용한 프로젝트에서 화면이 영원히 낡는다.
    pub(crate) fn wake(
        &mut self,
        now: Moment,
        why: Wake,
        observer: &mut (impl Observe + ?Sized),
    ) -> &Cached {
        if why == Wake::ChangeHint {
            // 첫 hint 만 시각을 남긴다 — 뒤따르는 것들은 여기에 합쳐진다.
            self.hinted.get_or_insert(now);
        }
        if self.due(now) {
            self.look(now, observer);
        }
        &self.cached
    }

    /// 지금 다시 볼 때가 됐는가.
    ///
    /// **화면을 읽었다는 사실은 여기 없다.** 그것이 이 상태기계의 요점이다.
    /// **다음 기한까지 얼마나 조용해도 되는가.**
    ///
    /// worker 는 이 값만큼만 잠들었다 깨어난다. 짧은 고정 주기로 되풀이 깨우는 대신 정확한
    /// 기한을 물어보는 까닭은 두 가지다 — 아무 일도 없는 구간에서 헛되이 깨지 않고,
    /// debounce 가 끝나는 순간을 놓치지도 않는다.
    ///
    /// `0` 은 「지금 이미 기한이다」라는 뜻이다.
    pub(crate) fn quiet_for(&self, now: Moment) -> Duration {
        // hint 를 모으는 중이면 그 기한이 언제나 더 이르다.
        let by_hint = self
            .hinted
            .map(|first| self.pace.debounce.saturating_sub(now.since(first)));
        let deadline = match self.cached.is_current() {
            true => self.pace.reconcile,
            false => self.pace.retry,
        };
        let by_deadline = deadline.saturating_sub(now.since(self.looked));
        match by_hint {
            Some(by_hint) => by_hint.min(by_deadline),
            None => by_deadline,
        }
    }

    fn due(&self, now: Moment) -> bool {
        // ① 모아 둔 hint 가 있고, 더 모을 만큼 모았다.
        if let Some(first) = self.hinted
            && now.since(first) >= self.pace.debounce
        {
            return true;
        }
        // ② hint 가 없어도 기한은 온다. 어느 기한인지는 지금 상태가 정한다 —
        //    성공해서 쉬는 중이면 느린 reconciliation, 실패해서 낡았으면 빠른 retry.
        let deadline = match self.cached.is_current() {
            true => self.pace.reconcile,
            false => self.pace.retry,
        };
        now.since(self.looked) >= deadline
    }

    /// **한 번 본다.** 성공하면 통째로 갈고, 실패해도 사실을 버리지 않는다.
    fn look(&mut self, now: Moment, observer: &mut (impl Observe + ?Sized)) {
        // 보기로 한 순간 hint 는 소진된다 — 보는 도중에 온 것은 다음 몫이다.
        self.hinted = None;
        self.looked = now;

        match observer.observe() {
            // **통째로 갈아 끼운다.** 절마다 합치면 화면의 두 칸이 다른 시점을 말한다.
            // 옛 오류도 여기서 함께 사라진다 — 지나간 실패를 현재처럼 보이지 않게.
            Ok(snapshot) => self.cached = Cached::Current { snapshot, at: now },
            Err(error) => {
                self.cached = match std::mem::replace(
                    &mut self.cached,
                    Cached::Unavailable {
                        error: String::new(),
                        failed_at: now,
                    },
                ) {
                    // 마지막으로 **성공한** 것을 그대로 들고 낡았다고만 말한다.
                    Cached::Current { snapshot, at } => Cached::Stale {
                        snapshot,
                        succeeded_at: at,
                        error,
                        failed_at: now,
                    },
                    // 이미 낡았다면 그 Snapshot 과 성공 시각은 그대로 두고 이유만 새로.
                    Cached::Stale {
                        snapshot,
                        succeeded_at,
                        ..
                    } => Cached::Stale {
                        snapshot,
                        succeeded_at,
                        error,
                        failed_at: now,
                    },
                    Cached::Unavailable { .. } => Cached::Unavailable {
                        error,
                        failed_at: now,
                    },
                };
            }
        }
    }
}

// ── 화면 ───────────────────────────────────────────────────────────────────

/// 지금 쥐고 있는 것을 한 문서로 — **낡았으면 낡았다고 맨 위에서 말한다.**
///
/// `Current` 일 때는 standalone `gil monitor --html` 과 **같은 문서**다. 자동 갱신 표지도,
/// 시각도 붙이지 않는다 — 그것이 두 표현이 갈리지 않는다는 뜻이고, 시험이 그것을 잰다.
pub(crate) fn render_cached_html(cached: &Cached) -> String {
    render_cached_page(cached, None, None)
}

/// 같은 화면 — 다만 server 가 제 주소로 스스로를 다시 받아오게 할 수 있다.
///
/// **표지는 사실 영역을 한 글자도 바꾸지 않는다.** 붙는 자리는 문서의 머리뿐이고, 그 아래
/// 절들은 표지가 있든 없든 같다.
pub(crate) fn render_cached_page(
    cached: &Cached,
    refresh: Option<(u64, &str)>,
    blind: Option<&str>,
) -> String {
    let mut out = html::open_document_refreshing(refresh);
    // **눈이 멀었으면 먼저 말한다.** 자동으로 따라오는 척하는 화면이 가장 위험하다 —
    // 사람은 바뀐 것이 없다고 읽는데 실은 보지 못하고 있는 것이다.
    if let Some(said) = blind {
        html::banner(
            &mut out,
            "변화를 스스로 알아채지 못한다",
            "이 실행에서는 파일 감시를 시작하지 못했다. 아래의 사실은 느린 주기로 다시 \
             관측될 뿐, 무언가를 고친 직후에 곧바로 따라오지 않는다.",
            &[("감시가 서지 못한 까닭", said.to_string())],
        );
    }
    match cached {
        Cached::Current { snapshot, .. } => html::facts(&mut out, snapshot),
        Cached::Stale {
            snapshot,
            succeeded_at,
            error,
            failed_at,
        } => {
            html::banner(
                &mut out,
                "이 내용은 최신이 아니다",
                "새 관측이 실패해 마지막으로 성공한 결과를 보이고 있다. \
                 아래의 모든 절은 그때의 사실이며 지금의 사실이 아니다.",
                &[
                    ("마지막 성공 관측", elapsed(*succeeded_at)),
                    ("실패한 시각", elapsed(*failed_at)),
                    ("실패한 까닭", error.clone()),
                ],
            );
            html::facts(&mut out, snapshot);
        }
        Cached::Unavailable { error, failed_at } => {
            html::banner(
                &mut out,
                "아직 보여 줄 것이 없다",
                "관측에 실패했고, 성공한 Snapshot 이 아직 하나도 없다. \
                 그래서 이 화면에는 GIL 의 사실이 하나도 실려 있지 않다.",
                &[
                    ("실패한 시각", elapsed(*failed_at)),
                    ("실패한 까닭", error.clone()),
                ],
            );
        }
    }
    html::close_document(&mut out);
    out
}

/// 논리적 시각을 사람이 읽는 글로.
///
/// 벽시계를 지어내지 않는다 — 이 상태기계는 지금이 몇 시인지 모르고, 알 필요도 없다.
/// 사람에게 필요한 것은 **얼마나 된 값인가**이지 그 값이 몇 시에 생겼는지가 아니다.
fn elapsed(moment: Moment) -> String {
    format!("시작으로부터 {}ms", moment.0.as_millis())
}

// ── 시험 ───────────────────────────────────────────────────────────────────
//
// 이 상태기계는 crate 안에만 있으므로 시험도 여기 산다. 재는 것은 넷이다.
//
// 1. **언제 보는가** — 화면을 읽는 것과 사실을 다시 재는 것이 갈리는가.
// 2. **무엇을 지키는가** — 실패가 마지막 사실을 건드리지 않는가.
// 3. **무엇을 버리는가** — 성공이 옛 오류를 남기지 않는가.
// 4. **어떻게 보이는가** — 낡은 것이 최신처럼 보이지 않는가.

#[cfg(test)]
mod tests {
    use super::*;
    use crate::rules::RuleSet;

    /// 시험이 대신 답하는 관측기 — **몇 번 불렸는지 세고, 정해 둔 답을 차례로 준다.**
    struct Fake {
        /// 부를 때마다 앞에서 하나씩 꺼낸다. 비면 마지막 답을 되풀이한다.
        answers: Vec<Result<MonitorSnapshot, String>>,
        /// 지금까지 몇 번 불렸는가.
        calls: usize,
    }

    impl Fake {
        fn new(answers: Vec<Result<MonitorSnapshot, String>>) -> Fake {
            Fake { answers, calls: 0 }
        }

        /// 언제나 성공하는 관측기.
        fn always_ok(label: &str) -> Fake {
            Fake::new(vec![Ok(a_snapshot(label))])
        }
    }

    impl Observe for Fake {
        fn observe(&mut self) -> Result<MonitorSnapshot, String> {
            self.calls += 1;
            match self.answers.len() {
                0 => panic!("시험이 정하지 않은 관측이 일어났다"),
                1 => self.answers[0].clone(),
                _ => self.answers.remove(0),
            }
        }
    }

    /// 진짜 Snapshot 하나 — 지어낸 값이 아니라 실제 조회가 만든 것이다.
    ///
    /// **시험마다 제 자리를 쓴다.** 하나를 나눠 쓰면 나란히 도는 시험들이 같은 프로젝트
    /// 잠금을 다투다 이유 없이 깜빡인다.
    fn a_snapshot(label: &str) -> MonitorSnapshot {
        let root = project(label);
        // **언제 불러도 같은 세계에서 시작한다.** 앞선 실행이 남긴 자국이 있으면 이 값이
        // 조용히 dirty 가 되고, 그러면 이 fixture 를 쓰는 시험이 재려던 것을 못 잰다.
        if root.join(crate::STATE_PATH).exists() {
            std::fs::write(root.join("a.txt"), "가").expect("기준 세계로 되돌린다");
        }
        if !root.join(crate::STATE_PATH).exists() {
            let _ = std::fs::remove_dir_all(&root);
            std::fs::create_dir_all(&root).expect("시험이 쓸 자리를 만든다");
            std::fs::write(root.join("a.txt"), "가").expect("세계를 하나 둔다");
            let session = crate::ProjectSession::start(
                RuleSet::builtin().expect("함께 실린 명세"),
                root.join(crate::STATE_PATH),
            )
            .expect("시작한다");
            session.commit().expect("눕힌다");
        }
        let session = crate::ProjectSession::open(
            RuleSet::builtin().expect("함께 실린 명세"),
            root.join(crate::STATE_PATH),
        )
        .expect("되살린다");
        session.monitor().expect("Snapshot 을 만든다")
    }

    /// **다른 세계**를 본 Snapshot 하나 — 부분 병합을 잴 수 있게 사실이 실제로 갈린다.
    ///
    /// 같은 프로젝트에서 두 번 찍으면 두 Snapshot 이 똑같아, 절을 옛 값으로 덮어도 아무도
    /// 모른다. 그래서 세계를 흔들어 `clean` 과 `dirty` 를 갈라 놓는다.
    fn a_changed_snapshot(label: &str) -> MonitorSnapshot {
        let root = project(label);
        let _ = a_snapshot(label); // 자리를 세운다.
        std::fs::write(root.join("a.txt"), "손으로 바꿔 놓았다").expect("세계를 흔든다");
        let session = crate::ProjectSession::open(
            RuleSet::builtin().expect("함께 실린 명세"),
            root.join(crate::STATE_PATH),
        )
        .expect("되살린다");
        let seen = session.monitor().expect("Snapshot 을 만든다");
        assert_eq!(seen.world.state, crate::WorldMark::Dirty, "세계가 갈리지 않았다");
        seen
    }

    fn project(label: &str) -> std::path::PathBuf {
        std::env::temp_dir().join(format!("gil-refresh-{label}"))
    }

    /// 시험이 쓰는 박자 — 읽기 쉬운 눈금으로.
    fn pace() -> Pace {
        Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_millis(1000),
            retry: Duration::from_millis(300),
        }
    }

    // ── ① 처음 서는 자리 ──────────────────────────────────────────────────

    #[test]
    fn a_first_look_that_succeeds_is_current() {
        const LABEL: &str = "a-first-look-that-succeeds-is-current";
        let mut watcher = Fake::always_ok(LABEL);
        let engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        assert_eq!(watcher.calls, 1);
        assert!(engine.cached().is_current());
        assert!(engine.cached().snapshot().is_some());
    }

    #[test]
    fn a_first_look_that_fails_has_nothing_to_show() {
        const LABEL: &str = "a-first-look-that-fails-has-nothing-to-show";
        let mut watcher = Fake::new(vec![Err("창고를 읽지 못했다".into())]);
        let engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        assert_eq!(watcher.calls, 1);
        assert!(!engine.cached().is_current());
        assert!(
            engine.cached().snapshot().is_none(),
            "성공한 적이 없는데 보여 줄 Snapshot 이 생겼다"
        );
        match engine.cached() {
            Cached::Unavailable { error, failed_at } => {
                assert_eq!(error, "창고를 읽지 못했다");
                assert_eq!(*failed_at, Moment::at(0));
            }
            other => panic!("다른 상태가 됐다: {other:?}"),
        }
    }

    // ── ② 화면을 읽는 것은 사실을 재는 것이 아니다 ────────────────────────

    #[test]
    fn reading_the_screen_does_not_look_at_the_project() {
        const LABEL: &str = "reading-the-screen-does-not-look-at-the-project";
        // **이 조각의 요점.** 창을 열어 둔 것이 프로젝트를 계속 훑는 이유가 되어서는 안 된다.
        let mut watcher = Fake::always_ok(LABEL);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        assert_eq!(watcher.calls, 1, "첫 관측 하나");

        // reconciliation 기한 안에서 화면을 여러 번 읽는다.
        for tick in [10, 50, 120, 300, 700, 999] {
            engine.wake(Moment::at(tick), Wake::ScreenRead, &mut watcher);
        }
        assert_eq!(watcher.calls, 1, "화면을 읽었다고 다시 관측했다");
        assert!(engine.cached().is_current());
    }

    #[test]
    fn many_hints_become_one_look() {
        const LABEL: &str = "many-hints-become-one-look";
        let mut watcher = Fake::always_ok(LABEL);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        // 편집이 이어진다 — debounce 구간 안이라 아직 보지 않는다.
        for tick in [10, 20, 30, 40, 50] {
            engine.wake(Moment::at(tick), Wake::ChangeHint, &mut watcher);
        }
        assert_eq!(watcher.calls, 1, "hint 마다 관측했다");

        // 첫 hint 로부터 debounce 가 지나면 **한 번** 본다.
        engine.wake(Moment::at(110), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 2, "합쳐진 hint 를 한 번에 보지 않았다");

        // 그리고 소진됐다 — 같은 hint 로 두 번 보지 않는다.
        engine.wake(Moment::at(120), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 2);
    }

    #[test]
    fn the_wait_for_a_hint_has_a_ceiling() {
        const LABEL: &str = "the-wait-for-a-hint-has-a-ceiling";
        // 매 hint 마다 기한을 다시 세면 편집이 이어지는 동안 화면이 영원히 멈춘다.
        let mut watcher = Fake::always_ok(LABEL);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        // 90ms 마다 hint 가 계속 온다 — debounce(100ms)보다 촘촘하다.
        for tick in [10, 100, 190, 280] {
            engine.wake(Moment::at(tick), Wake::ChangeHint, &mut watcher);
        }
        assert!(
            watcher.calls >= 2,
            "hint 가 이어지는 동안 한 번도 보지 않았다 — 기다림에 상한이 없다"
        );
    }

    #[test]
    fn a_quiet_project_is_still_looked_at_eventually() {
        const LABEL: &str = "a-quiet-project-is-still-looked-at-eventually";
        // watcher 가 event 를 놓치거나 합쳐도 느린 기한 하나가 수렴시킨다.
        let mut watcher = Fake::always_ok(LABEL);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        engine.wake(Moment::at(999), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 1, "기한 전에 봤다");

        engine.wake(Moment::at(1000), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 2, "hint 가 없다고 영원히 보지 않았다");
    }

    // ── ③ 실패가 사실을 지우지 않는다 ────────────────────────────────────

    #[test]
    fn a_failure_keeps_the_last_fact_and_says_it_is_old() {
        const LABEL: &str = "a-failure-keeps-the-last-fact-and-says-it-is-old";
        let good = a_snapshot(LABEL);
        let mut watcher = Fake::new(vec![Ok(good.clone()), Err("잠금을 얻지 못했다".into())]);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        engine.wake(Moment::at(1000), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 2);

        match engine.cached() {
            Cached::Stale {
                snapshot,
                succeeded_at,
                error,
                failed_at,
            } => {
                // **마지막으로 성공한 것이 한 글자도 바뀌지 않았다.**
                assert_eq!(snapshot.current_cycle, good.current_cycle);
                assert_eq!(snapshot.active_lineage, good.active_lineage);
                assert_eq!(snapshot.world, good.world);
                assert_eq!(snapshot.next_actions, good.next_actions);
                // 그리고 두 시각이 갈린다 — 언제의 사실이고 언제 실패했는가.
                assert_eq!(*succeeded_at, Moment::at(0));
                assert_eq!(*failed_at, Moment::at(1000));
                assert_eq!(error, "잠금을 얻지 못했다");
            }
            other => panic!("실패가 사실을 버렸다: {other:?}"),
        }
        assert!(!engine.cached().is_current(), "낡은 것을 최신이라 했다");
    }

    #[test]
    fn a_second_failure_keeps_the_first_success() {
        const LABEL: &str = "a-second-failure-keeps-the-first-success";
        let good = a_snapshot(LABEL);
        let mut watcher = Fake::new(vec![
            Ok(good.clone()),
            Err("한 번째 실패".into()),
            Err("두 번째 실패".into()),
        ]);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        engine.wake(Moment::at(1000), Wake::Elapsed, &mut watcher);
        engine.wake(Moment::at(1300), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 3);

        match engine.cached() {
            Cached::Stale {
                snapshot,
                succeeded_at,
                error,
                failed_at,
            } => {
                assert_eq!(snapshot.current_cycle, good.current_cycle);
                assert_eq!(*succeeded_at, Moment::at(0), "성공 시각이 실패로 밀렸다");
                assert_eq!(error, "두 번째 실패", "가장 최근 까닭이 아니다");
                assert_eq!(*failed_at, Moment::at(1300));
            }
            other => panic!("{other:?}"),
        }
    }

    #[test]
    fn a_stale_screen_is_retried_without_any_hint() {
        const LABEL: &str = "a-stale-screen-is-retried-without-any-hint";
        let mut watcher = Fake::new(vec![Ok(a_snapshot(LABEL)), Err("일시적 실패".into())]);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        engine.wake(Moment::at(1000), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 2);

        // retry 기한 전에는 화면을 읽어도 보지 않는다.
        engine.wake(Moment::at(1200), Wake::ScreenRead, &mut watcher);
        assert_eq!(watcher.calls, 2, "기한 전에 다시 봤다");

        // 기한이 지나면 **hint 하나 없이도** 다시 본다.
        engine.wake(Moment::at(1300), Wake::ScreenRead, &mut watcher);
        assert_eq!(watcher.calls, 3, "낡은 채로 영원히 머물렀다");
    }

    #[test]
    fn an_unavailable_screen_is_retried_too() {
        const LABEL: &str = "an-unavailable-screen-is-retried-too";
        let mut watcher = Fake::new(vec![Err("첫 실패".into()), Err("둘째 실패".into())]);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        assert_eq!(watcher.calls, 1);

        engine.wake(Moment::at(299), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 1, "기한 전에 다시 봤다");
        engine.wake(Moment::at(300), Wake::Elapsed, &mut watcher);
        assert_eq!(watcher.calls, 2);
        assert!(engine.cached().snapshot().is_none());
    }

    // ── ④ 성공은 통째로 갈아 끼운다 ──────────────────────────────────────

    #[test]
    fn a_success_replaces_everything_and_leaves_no_old_error() {
        const LABEL: &str = "a-success-replaces-everything-and-leaves-no-old-error";
        // 두 Snapshot 이 **실제로 다른 세계**를 본다 — 그래야 절을 옛 값으로 덮는 구현이
        // 여기서 걸린다.
        let old = a_snapshot(LABEL);
        let fresh = a_changed_snapshot(LABEL);
        assert_ne!(old.world, fresh.world, "두 Snapshot 이 같아 병합을 잴 수 없다");
        assert_ne!(old.next_actions, fresh.next_actions);
        let mut watcher = Fake::new(vec![
            Ok(old.clone()),
            Err("<script>alert(1)</script>".into()),
            Ok(fresh.clone()),
        ]);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        engine.wake(Moment::at(1000), Wake::Elapsed, &mut watcher);
        assert!(!engine.cached().is_current());

        engine.wake(Moment::at(1300), Wake::Elapsed, &mut watcher);
        match engine.cached() {
            Cached::Current { snapshot, at } => {
                assert_eq!(snapshot.current_cycle, fresh.current_cycle);
                // **통째로 갈렸다.** 절 하나라도 옛 값이 남으면 화면의 두 칸이 서로 다른
                // 시점을 말하게 되고, 그것은 어느 시점의 사실도 아니다.
                assert_eq!(snapshot.world, fresh.world, "세계 절이 옛 값으로 남았다");
                assert_eq!(
                    snapshot.next_actions, fresh.next_actions,
                    "다음 행동 절이 옛 값으로 남았다"
                );
                assert_ne!(snapshot.world, old.world);
                assert_eq!(*at, Moment::at(1300));
            }
            other => panic!("성공했는데 낡은 상태로 남았다: {other:?}"),
        }
        // **옛 오류가 남지 않는다** — 화면에도, 상태에도.
        let html = render_cached_html(engine.cached());
        assert!(!html.contains("alert"), "지나간 실패가 화면에 남았다");
        assert!(!html.contains("최신이 아니다"), "성공했는데 낡았다고 말한다");
    }

    // ── ⑤ 화면 ────────────────────────────────────────────────────────────

    #[test]
    fn a_current_screen_is_the_standalone_document() {
        const LABEL: &str = "a-current-screen-is-the-standalone-document";
        // 두 표현이 갈리지 않는다는 증거 — 자동 갱신 표지도 시각도 붙이지 않는다.
        let seen = a_snapshot(LABEL);
        let mut watcher = Fake::new(vec![Ok(seen.clone())]);
        let engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        assert_eq!(
            render_cached_html(engine.cached()),
            super::super::render_monitor_html(&seen),
            "Current 화면이 standalone 문서와 갈렸다"
        );
    }

    #[test]
    fn a_stale_screen_says_so_at_the_very_top() {
        const LABEL: &str = "a-stale-screen-says-so-at-the-very-top";
        let mut watcher = Fake::new(vec![Ok(a_snapshot(LABEL)), Err("창고가 잠겨 있다".into())]);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        engine.wake(Moment::at(1000), Wake::Elapsed, &mut watcher);

        let html = render_cached_html(engine.cached());
        // 맨 위에서 말한다 — 사실 절보다 **먼저**.
        let warned = html.find("최신이 아니다").expect("낡았다고 말하지 않는다");
        let first_fact = html.find("<h2>현재").expect("사실 절이 있다");
        assert!(warned < first_fact, "경고가 사실 아래에 묻혔다");

        // 색이 아니라 **글**로 갈린다.
        assert!(html.contains("<h2>이 내용은 최신이 아니다</h2>"), "{html}");
        assert!(html.contains("마지막 성공 관측"), "{html}");
        assert!(html.contains("실패한 시각"), "{html}");
        assert!(html.contains("창고가 잠겨 있다"), "까닭을 잃었다");
        // 그리고 그때의 사실은 그대로 실린다.
        assert!(html.contains("<h2>현재 인터뷰</h2>"), "{html}");
    }

    #[test]
    fn an_unavailable_screen_carries_no_gil_fact() {
        const LABEL: &str = "an-unavailable-screen-carries-no-gil-fact";
        let mut watcher = Fake::new(vec![Err("프로젝트를 찾지 못했다".into())]);
        let engine = Refresh::start(pace(), Moment::at(0), &mut watcher);

        let html = render_cached_html(engine.cached());
        assert!(html.contains("<h2>아직 보여 줄 것이 없다</h2>"), "{html}");
        assert!(html.contains("프로젝트를 찾지 못했다"), "{html}");
        // 없는 사실을 지어내지 않는다.
        for section in ["현재 인터뷰", "현재 실험", "활성 경로", "현재 세계", "다음 행동"] {
            assert!(!html.contains(section), "{section} 절을 지어냈다:\n{html}");
        }
        // 그래도 완전한 문서다.
        assert!(html.starts_with("<!doctype html>"), "{html}");
        assert!(html.contains("Content-Security-Policy"), "{html}");
        assert!(html.trim_end().ends_with("</html>"), "{html}");
    }

    #[test]
    fn a_nasty_error_string_never_becomes_markup() {
        const LABEL: &str = "a-nasty-error-string-never-becomes-markup";
        // 오류 글은 사람이 쓴 것이 아니어도 **신뢰하지 않는 입력**이다 — 프로젝트 경로나
        // Report 조각이 섞여 들어올 수 있다.
        let nasty = "<img src=x onerror=alert(1)> & \"quoted\" 'single' <script>bad()</script>";
        let mut watcher = Fake::new(vec![Ok(a_snapshot(LABEL)), Err(nasty.into())]);
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        engine.wake(Moment::at(1000), Wake::Elapsed, &mut watcher);

        let html = render_cached_html(engine.cached());
        for forbidden in ["<img", "<script"] {
            assert!(!html.contains(forbidden), "{forbidden:?} 가 요소가 됐다");
        }
        // **글자로 남았는지가 아니라 요소가 됐는지를 잰다.** `onerror=` 는 escape 된 글
        // 안에 그대로 있어야 하고, 진짜 태그 안에는 하나도 없어야 한다.
        assert!(no_tag_carries(&html, "onerror"), "event handler 가 태그에 붙었다");
        assert!(no_tag_carries(&html, "src="), "바깥을 가리키는 태그가 생겼다");
        // 그러나 글자로는 남는다 — 사라지면 사람이 무엇이 잘못됐는지 모른다.
        assert!(html.contains("&lt;img src=x onerror=alert(1)&gt;"), "{html}");
        assert!(html.contains("&amp; &quot;quoted&quot; &#39;single&#39;"), "{html}");
        assert!(!html.contains("&amp;lt;"), "escape 를 두 번 걸었다");

        // 같은 것을 Unavailable 에서도 잰다.
        let mut watcher = Fake::new(vec![Err(nasty.into())]);
        let engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        let html = render_cached_html(engine.cached());
        assert!(!html.contains("<img") && !html.contains("<script"), "{html}");
        assert!(no_tag_carries(&html, "onerror"), "event handler 가 태그에 붙었다");
        assert!(html.contains("&lt;img src=x"), "{html}");
    }

    /// **진짜 태그 안**에 그 글자가 하나도 없는가.
    ///
    /// escape 된 글 속의 `&lt;` 는 태그를 열지 않으므로 여기 걸리지 않는다. 그것이 요점이다 —
    /// 같은 글자가 텍스트로 남는 것과 태그가 되는 것은 전혀 다른 일이다.
    fn no_tag_carries(html: &str, needle: &str) -> bool {
        let mut rest = html;
        while let Some(at) = rest.find('<') {
            rest = &rest[at + 1..];
            let Some(end) = rest.find('>') else {
                break;
            };
            if rest[..end].contains(needle) {
                return false;
            }
            rest = &rest[end + 1..];
        }
        true
    }

    #[test]
    fn rendering_changes_neither_the_engine_nor_the_project() {
        const LABEL: &str = "rendering-changes-neither-the-engine-nor-the-project";
        // **이 시험의 fixture 가 세운 자리를 읽는다.** 예전에는 남의 이름을 적어 두어,
        // 다른 시험이 우연히 만들어 둔 폴더에 기대고 있었다.
        let dir = project(LABEL);
        let mut watcher = Fake::always_ok(LABEL);
        let engine = Refresh::start(pace(), Moment::at(0), &mut watcher);
        let before = std::fs::read(dir.join(crate::STATE_PATH)).expect("상태를 읽는다");

        let once = render_cached_html(engine.cached());
        for _ in 0..3 {
            assert_eq!(render_cached_html(engine.cached()), once, "그릴 때마다 달라졌다");
        }

        // 그리는 것은 관측이 아니다.
        assert_eq!(watcher.calls, 1, "그리다가 프로젝트를 봤다");
        assert!(engine.cached().is_current());
        assert_eq!(
            std::fs::read(dir.join(crate::STATE_PATH)).expect("상태를 읽는다"),
            before,
            "그리다가 프로젝트를 바꿨다"
        );
    }
}
