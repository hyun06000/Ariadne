//! **지금 보고 있는 Project 하나만 지켜본다.**
//!
//! Host UI Model §8 이 정한 것은 하나다 — watcher 가 보내는 것은 「사실이 바뀌었을 수
//! 있으니 **완전한** View 를 다시 읽어라」뿐이다. 경로도, 사건의 종류도, 순서도, 바뀐
//! 내용도 화면으로 나가지 않고 설정에도 남지 않는다.
//!
//! ```text
//!   notify event → gil::watch_hints 가 `.gil` 잡음을 거른다 → hint 한 마디
//!                → Refresh 가 모은다(첫 hint 부터 debounce)
//!                → `gil://refresh` 한 번
//!                → 창이 기존 load_view(scope) 로 **완전한 View** 하나를 읽는다
//! ```
//!
//! # 무엇을 빌려 쓰는가
//!
//! 감시(`watch_hints`)도 모으는 규칙(`Refresh`)도 `gil monitor --serve` 와 **같은 것**이다.
//! 상태기계를 베껴 두 자리에서 따로 키우면, 한쪽의 debounce 만 고쳐지는 날이 온다.
//!
//! `Refresh` 가 「관측」이라 부르는 자리에서 이 파일이 하는 일은 **창에 알리는 것**뿐이다.
//! 진짜 관측은 창이 한다 — 그래야 View 가 기존 read-only 경로 하나로만 들어온다.
//!
//! # 무엇을 지켜보지 않는가
//!
//! 등록해 둔 다른 Project 는 보지 않는다. 창이 숨어 있어도 현재 Project 가 있으면 계속
//! 본다 — 창은 숨은 것이지 없어진 것이 아니다. Project 를 바꾸면 앞의 감시를 **완전히**
//! 끝내고 새 것 하나를 세운다.

use std::path::Path;
use std::sync::mpsc::{Receiver, RecvTimeoutError, SyncSender, sync_channel};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use gil::{Backoff, Moment, Observe, Pace, Refresh, Wake, watch_hints};
use tauri::{AppHandle, Emitter};

/// 창에 보내는 말. 이 한 줄이 전부다.
pub const HINT: &str = "gil://refresh";

/// 얼마나 모았다 보낼 것인가 — **Companion adapter 의 성능 parameter 이지 도메인이나
/// wire 계약이 아니다**(Monitor §8.3).
///
/// # 왜 `gil monitor --serve` 의 30초가 아니라 5분인가
///
/// `world_state()` 는 안정된 판정을 위해 Artifact 세계를 **두 번** 훑는다(Artifact §6).
/// Companion 은 사람이 며칠씩 띄워 두는 창이다. 아무 일도 없는 큰 Project 를 30초마다
/// 두 번씩 훑으면, 창을 열어 둔 것만으로 프로젝트 크기에 비례하는 비용이 계속 나간다.
///
/// 그래서 **아무 사건도 없을 때만** 5분이다. 사람이 기다리는 자리는 전부 그 앞에 있다.
///
/// ```text
///   notify hint      debounce(250ms) 뒤 곧바로     ← 실제 변화는 여기로 온다
///   수동 새로고침      곧바로
///   Project 선택      그 자리에서 완전한 View
///   창을 다시 봄       기존 수명 규칙
///   아무 일도 없음     최대 5분 — 놓친 event 를 위한 마지막 그물
/// ```
///
/// `gil monitor --serve` 는 [`Pace::default`] 의 30초를 그대로 쓴다. 그쪽은 사람이 보고
/// 있는 동안만 열려 있는 표면이라 사정이 다르다.
fn pace() -> Pace {
    Pace {
        debounce: Duration::from_millis(250),
        reconcile: Duration::from_secs(5 * 60),
        // 이 자리의 「실패」는 창에 알리지 못한 경우다 — 거의 나지 않는다. 창의 조회가
        // 실패했을 때의 재시도는 아래 [`RETRY`] 사다리가 따로 잰다.
        retry: Backoff::ladder(TELL_RETRY),
    }
}

const TELL_RETRY: &[Duration] = &[Duration::from_secs(2)];

/// **창의 완전 View 조회가 연속으로 실패할 때** 얼마나 기다렸다 다시 청할 것인가.
///
/// ```text
///   2초 → 4초 → 8초 → 16초 → 30초 → 60초 → 60초 → …
/// ```
///
/// 고정 2초로 두면, 오래 가는 실패(손상·권한) 앞에서 큰 Project 를 영원히 2초마다 다시
/// 훑는다. `world_state()` 가 Artifact 세계를 **두 번** 훑으므로 그 비용은 프로젝트 크기에
/// 비례해 계속 나간다. 그래서 상한을 둔다.
///
/// 곱셈이 아니라 글자로 적는 까닭은 둘이다 — 넘칠 자리가 없고, 상한이 눈에 보인다.
///
/// **성공하면 처음으로 돌아간다.** 한 번 통했다면 다음 실패는 새 사정이다.
const RETRY: &[Duration] = &[
    Duration::from_secs(2),
    Duration::from_secs(4),
    Duration::from_secs(8),
    Duration::from_secs(16),
    Duration::from_secs(30),
    Duration::from_secs(60),
];

/// 연속 실패 뒤 기다릴 시간. 사다리 끝에 닿으면 **그 자리에 머문다.**
fn retry_after(failures: usize) -> Duration {
    Backoff::ladder(RETRY).after(failures)
}

/// worker 에게 보내는 말.
enum Wish {
    /// 파일이 바뀌었을지 모른다.
    Hint,
    /// 창의 완전 View 조회가 **실패했다** — backoff 를 한 칸 올리고 기한을 잡는다.
    Failed,
    /// 창의 조회가 **성공했다** — 사다리를 처음으로 되돌린다.
    Worked,
    /// 그만 본다.
    Stop,
}

/// **관측이라 부르지만, 하는 일은 창에 알리는 것뿐이다.**
///
/// 진짜 사실은 창이 `load_view(scope)` 로 읽는다. 여기서 `.gil` 을 열지도, Artifact 를
/// 판정하지도 않는다 — 그러면 사실이 두 곳에서 나게 된다.
struct TellTheWindow {
    app: AppHandle,
}

impl Observe<()> for TellTheWindow {
    fn observe(&mut self) -> Result<(), String> {
        self.app.emit(HINT, ()).map_err(|err| err.to_string())
    }
}

/// 지금 지켜보고 있는 것 — **한 번에 하나뿐.**
pub struct Live {
    inner: Mutex<Option<Watch>>,
}

impl Default for Live {
    fn default() -> Live {
        Live { inner: Mutex::new(None) }
    }
}

struct Watch {
    scope: String,
    wishes: SyncSender<Wish>,
    worker: Option<std::thread::JoinHandle<()>>,
    /// 감시를 쥔 자리. 떨어뜨리면 감시가 멈춘다.
    ///
    /// **`None` 은 「이 Project 를 보고 있지만 눈이 없다」** 는 뜻이다. worker 는 돌고
    /// 있으므로 느린 기한은 오지만, 파일이 바뀌어도 곧바로 알지 못한다.
    watching: Option<gil::Watching>,
}

impl Watch {
    /// 이 자리에 **정말 눈이 붙어 있는가.**
    fn sees(&self) -> bool {
        self.watching.is_some()
    }
}

impl Live {
    /// 이 Project 를 지켜본다 — **앞의 것은 완전히 끝내고.**
    ///
    /// 같은 scope 를 다시 고르면 아무것도 하지 않는다. 다시 세우면 그 사이에 두 감시가
    /// 겹치고, 같은 변화가 두 번 hint 로 나간다.
    ///
    /// 감시를 세우지 못해도 **거절하지 않는다.** watcher 는 지연을 줄이는 가속기이지 사실의
    /// 공급원이 아니다(Monitor §8.6.1). 그 사실만 돌려주고, 창은 수동 새로고침으로 계속
    /// 쓸 수 있다.
    pub fn follow(&self, app: &AppHandle, scope: &str, root: &Path) -> Result<(), String> {
        let app = app.clone();
        self.follow_with(scope, root, move || Box::new(TellTheWindow { app }))
    }

    /// 창에 알리는 일을 **밖에서 받는** 판.
    ///
    /// 시험이 `AppHandle` 없이 같은 수명 규칙을 밟기 위한 이음매다 — 창을 띄우지 않고도
    /// 「눈이 없으면 다시 세운다」와 「파일 하나가 hint 한 번」을 잴 수 있다.
    fn follow_with(
        &self,
        scope: &str,
        root: &Path,
        teller: impl FnOnce() -> Box<dyn Observe<()> + Send>,
    ) -> Result<(), String> {
        let mut seat = self.inner.lock().expect("지켜보는 자리");

        // **scope 가 같다는 것만으로 넘어가지 않는다.**
        //
        // 앞서 감시를 세우지 못했다면 worker 만 도는 「눈 없는」 자리다. 같은 Project 를
        // 사람이 다시 고른 것은 **다시 해 보라는 뜻**이므로, 그 자리를 걷어내고 처음부터
        // 세운다. scope 만 보고 no-op 하면 그 Project 는 창이 살아 있는 동안 영영 자동
        // 갱신을 얻지 못한다.
        if seat.as_ref().is_some_and(|one| one.scope == scope && one.sees()) {
            return Ok(()); // 이미 이것을 제대로 보고 있다
        }
        if let Some(old) = seat.take() {
            old.stop();
        }

        let (wishes, hear) = sync_channel::<Wish>(8);
        let mut teller = teller();

        // **감시가 서지 못해도 worker 는 선다.** 그래야 느린 기한이 수렴을 맡는다.
        let watching = watch_hints(root, {
            let wishes = wishes.clone();
            // 가득 차면 버린다 — hint 는 백 개나 한 개나 뜻이 같다.
            move || {
                let _ = wishes.try_send(Wish::Hint);
            }
        });
        let (watching, trouble) = match watching {
            Ok(one) => (Some(one), None),
            Err(said) => (None, Some(said)),
        };

        let worker = std::thread::spawn(move || {
            let started = Instant::now();
            pump(hear, &mut *teller, pace(), move || {
                Moment::at(started.elapsed().as_millis() as u64)
            });
        });

        *seat = Some(Watch {
            scope: scope.to_string(),
            wishes,
            worker: Some(worker),
            watching,
        });
        match trouble {
            None => Ok(()),
            Some(said) => Err(said),
        }
    }

    /// 아무것도 보지 않는다 — Project 를 빼거나 앱이 끝날 때.
    pub fn stop(&self) {
        if let Some(old) = self.inner.lock().expect("지켜보는 자리").take() {
            old.stop();
        }
    }

    /// 창의 완전 View 조회가 **실패했다.**
    ///
    /// 지금 보고 있는 Project 의 것만 받는다 — 앞 Project 의 늦은 실패가 새 Project 의
    /// 사다리를 올리면 안 된다(계약 5).
    pub fn fetch_failed(&self, scope: &str) {
        self.tell(scope, Wish::Failed);
    }

    /// 창의 조회가 **성공했다** — 사다리를 처음으로.
    pub fn fetch_worked(&self, scope: &str) {
        self.tell(scope, Wish::Worked);
    }

    fn tell(&self, scope: &str, wish: Wish) {
        let seat = self.inner.lock().expect("지켜보는 자리");
        if let Some(one) = seat.as_ref()
            && one.scope == scope
        {
            let _ = one.wishes.try_send(wish);
        }
    }

    /// 지금 자리에 **눈이 붙어 있는가** — 자동 갱신이 실제로 도는지.
    pub fn sees(&self) -> bool {
        self.inner.lock().expect("지켜보는 자리").as_ref().is_some_and(|one| one.sees())
    }

    /// 지금 보고 있는 scope. 시험과 보고용이다.
    pub fn following(&self) -> Option<String> {
        self.inner.lock().expect("지켜보는 자리").as_ref().map(|one| one.scope.clone())
    }

}

impl Watch {
    /// **정말 멈출 때까지 기다린다.** 떨어뜨리기만 하면 갈래가 살아 있는 순간이 남는다.
    fn stop(mut self) {
        let _ = self.wishes.try_send(Wish::Stop);
        drop(self.watching.take());
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

/// **hint 를 모아 한 번으로 줄이는 고리** — 시계를 밖에서 받는다.
///
/// `Live::follow` 가 갈래 하나에서 이것을 돌린다. 시계와 관측을 인자로 받는 까닭은 하나다 —
/// 「백 개가 한 번으로 합쳐지는가」를 **실제 시간에 기대지 않고** 잴 수 있어야 한다.
///
/// ```text
///   Wish::Hint     → Wake::ChangeHint   첫 hint 부터 debounce 를 센다
///   시간이 다 됨    → Wake::Elapsed      hint 가 없어도 기한은 온다
///   Wish::Stop     → 끝                 통로가 닫혀도 같다
/// ```
fn pump(
    hear: Receiver<Wish>,
    teller: &mut (impl Observe<()> + ?Sized),
    pace: Pace,
    clock: impl Fn() -> Moment,
) {
    // **첫 관측은 하지 않는다.** 창은 이미 제 View 를 읽었다. 여기서 또 알리면
    // Project 를 고르자마자 두 번 읽는다.
    let mut engine = Refresh::start(pace, clock(), &mut Quiet);

    // 창의 조회가 연속으로 몇 번 실패했는가, 그리고 다시 청할 시각.
    //
    // `Refresh` 의 기한과 **따로** 센다. 실패한 것은 창의 조회이고, 그 사실은 창이 끝난
    // 뒤에야 안다 — `Refresh` 는 그 사이에 아무것도 하지 않는다.
    let mut failures = 0usize;
    let mut retry_at: Option<Moment> = None;

    loop {
        let now = clock();
        let waiting = match retry_at {
            // backoff 기한이 더 이르면 그때 깨어난다.
            Some(due) => engine.quiet_for(now).min(due.since_or_zero(now)),
            None => engine.quiet_for(now),
        };
        match hear.recv_timeout(waiting) {
            Ok(Wish::Hint) => {
                // **hint 는 backoff 를 기다리지 않는다.** 기존 debounce 로 곧 청한다.
                retry_at = None;
                engine.wake(clock(), Wake::ChangeHint, teller);
            }
            Ok(Wish::Failed) => {
                failures = failures.saturating_add(1);
                let now = clock();
                retry_at = Some(now.after(retry_after(failures)));
            }
            Ok(Wish::Worked) => {
                // **성공은 사다리를 처음으로 되돌린다.**
                failures = 0;
                retry_at = None;
            }
            Ok(Wish::Stop) | Err(RecvTimeoutError::Disconnected) => return,
            Err(RecvTimeoutError::Timeout) => {
                let now = clock();
                match retry_at {
                    Some(due) if due <= now => {
                        retry_at = None;
                        // 다시 청한다. 창이 기존 single-flight 로 완전한 View 를 읽는다.
                        let _ = teller.observe();
                    }
                    _ => {
                        engine.wake(now, Wake::Elapsed, teller);
                    }
                }
            }
        }
    }
}

/// [`Moment`] 에 없는 두 가지를 여기서만 쓴다 — 밖으로 내보내지 않는다.
trait Clockwork {
    fn after(self, span: Duration) -> Moment;
    fn since_or_zero(self, now: Moment) -> Duration;
}

impl Clockwork for Moment {
    fn after(self, span: Duration) -> Moment {
        Moment::at(self.millis().saturating_add(span.as_millis() as u64))
    }
    fn since_or_zero(self, now: Moment) -> Duration {
        Duration::from_millis(self.millis().saturating_sub(now.millis()))
    }
}

/// 첫 세움에만 쓰는, 아무 말도 하지 않는 관측.
struct Quiet;

impl Observe<()> for Quiet {
    fn observe(&mut self) -> Result<(), String> {
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Arc;
    use std::sync::atomic::{AtomicU64, Ordering};

    /// 몇 번 불렸는지 세는 관측 — **합치기를 횟수로 증명하는 자리.**
    #[derive(Default)]
    struct Counting(Arc<AtomicU64>);

    impl Observe<()> for Counting {
        fn observe(&mut self) -> Result<(), String> {
            self.0.fetch_add(1, Ordering::SeqCst);
            Ok(())
        }
    }

    /// 시험이 손으로 돌리는 시계. 실제 시간에 기대지 않는다.
    #[derive(Clone, Default)]
    struct Hand(Arc<AtomicU64>);

    impl Hand {
        fn now(&self) -> Moment {
            Moment::at(self.0.load(Ordering::SeqCst))
        }
        fn tick(&self, millis: u64) {
            self.0.fetch_add(millis, Ordering::SeqCst);
        }
    }

    fn quick() -> Pace {
        Pace {
            debounce: Duration::from_millis(250),
            // 이 시험들에서 기한이 끼어들지 않도록 멀리 둔다 — debounce 만 잰다.
            reconcile: Duration::from_secs(3600),
            retry: Backoff::ladder({
                const FAR: &[Duration] = &[Duration::from_secs(3600)];
                FAR
            }),
        }
    }

    /// `pump` 를 갈래 하나에서 돌리고, **시계는 시험이 쥔다.**
    ///
    /// 실제 시간에 기대지 않는다 — 조건이 될 때까지 값을 보고, 안 되면 시험이 실패한다.
    struct Bench {
        wishes: SyncSender<Wish>,
        counted: Arc<AtomicU64>,
        hand: Hand,
        worker: Option<std::thread::JoinHandle<()>>,
    }

    impl Bench {
        /// 시계가 **멈춰 있다** — 시험이 손으로만 돌린다.
        fn start() -> Bench {
            Bench::with_step(0)
        }

        /// 시계가 **깨어날 때마다** `step` 만큼 흐른다.
        ///
        /// 「일이 처리되는 동안 시간이 간다」는 상황을 실제 시간 없이 만든다. 기아 방지를
        /// 재려면 시계가 pump 쪽에서 움직여야 한다 — 시험 갈래에서 미리 돌려 두면 pump 가
        /// 따라잡기도 전에 시간이 다 지나 버린다.
        fn with_step(step: u64) -> Bench {
            let counted = Arc::new(AtomicU64::new(0));
            let hand = Hand::default();
            let (wishes, hear) = sync_channel::<Wish>(256);
            let mut teller = Counting(counted.clone());
            let ticking = hand.clone();
            let worker = std::thread::spawn(move || {
                pump(hear, &mut teller, quick(), move || {
                    if step > 0 {
                        ticking.tick(step);
                    }
                    ticking.now()
                });
            });
            Bench { wishes, counted, hand, worker: Some(worker) }
        }

        fn hint(&self) {
            self.wishes.send(Wish::Hint).expect("넣는다");
        }

        fn told(&self) -> u64 {
            self.counted.load(Ordering::SeqCst)
        }

        /// 값이 될 때까지 본다 — **기다리는 동안 논리 시각도 흐른다.**
        ///
        /// 시계를 멈춘 채로 기다리면, pump 가 hint 를 우리가 시각을 옮긴 **뒤에** 집었을
        /// 때 그 debounce 는 영영 차지 않는다. 기다림은 곧 시간이 흐르는 일이므로 여기서
        /// 함께 돌린다. 되지 않으면 **시험이 실패한다** — 막연히 자지 않는다.
        fn wait_until(&self, want: u64) -> u64 {
            let deadline = Instant::now() + Duration::from_secs(5);
            while self.told() < want {
                assert!(
                    Instant::now() < deadline,
                    "{want}번 알리기를 기다리다 지쳤다 (지금 {})",
                    self.told()
                );
                self.hand.tick(10);
                std::thread::yield_now();
            }
            self.hand.0.load(Ordering::SeqCst)
        }


        /// 잠잠한지 잠깐 지켜본다 — 「아직 알리면 안 된다」를 재는 자리.
        fn stays_quiet(&self) {
            let until = Instant::now() + Duration::from_millis(80);
            while Instant::now() < until {
                assert_eq!(self.told(), 0, "다 모으기 전에 알렸다");
                std::thread::yield_now();
            }
        }

        fn stop(mut self) -> u64 {
            let _ = self.wishes.try_send(Wish::Stop);
            drop(std::mem::replace(&mut self.wishes, sync_channel(1).0));
            if let Some(worker) = self.worker.take() {
                let _ = worker.join();
            }
            self.told()
        }
    }

    #[test]
    fn a_hundred_hints_become_one_telling() {
        let bench = Bench::start();
        // **시계가 멈춘 채로** 백 개가 쏟아진다 — 한 debounce 창 안의 일이다.
        for _ in 0..100 {
            bench.hint();
        }
        bench.stays_quiet();

        // 이제 시간이 지났다. 다음에 깨어날 때 기한이 온다.
        bench.hand.tick(300);
        bench.hint(); // 깨운다
        bench.wait_until(1);

        // 잠잠해진 뒤에도 한 번 그대로다.
        std::thread::sleep(Duration::from_millis(30));
        assert_eq!(bench.told(), 1, "백 개가 한 번으로 합쳐지지 않았다");
        assert_eq!(bench.stop(), 1);
    }

    #[test]
    fn hints_that_keep_coming_do_not_push_the_deadline_forever() {
        // hint 를 하나 볼 때마다 60ms 가 흐른다 — debounce(250ms)보다 짧다.
        //
        // 마지막 event 부터 다시 세면 이 고리에서 **영원히** 알리지 못한다. 첫 hint 를
        // 쥐고 있으므로 기다림에 상한이 생긴다.
        let bench = Bench::with_step(60);
        let feeding = std::thread::spawn({
            let wishes = bench.wishes.clone();
            move || {
                for _ in 0..200 {
                    if wishes.send(Wish::Hint).is_err() {
                        return;
                    }
                }
            }
        });
        bench.wait_until(1);
        let told = bench.stop();
        let _ = feeding.join();
        assert!(told >= 1, "편집이 이어지는 동안 한 번도 알리지 못했다");
    }

    #[test]
    fn nothing_is_told_before_the_debounce_is_up() {
        let bench = Bench::start();
        bench.hint();
        bench.hand.tick(50); // 아직 모으는 중
        bench.hint();
        bench.stays_quiet();
        assert_eq!(bench.stop(), 0, "다 모으기 전에 알렸다");
    }

    #[test]
    fn a_closed_channel_ends_the_loop() {
        let counted = Arc::new(AtomicU64::new(0));
        let (wishes, hear) = sync_channel::<Wish>(8);
        drop(wishes); // 통로가 닫혔다
        let mut teller = Counting(counted.clone());
        // 끝나지 않으면 이 시험이 멈춘다.
        pump(hear, &mut teller, quick(), || Moment::at(0));
        assert_eq!(counted.load(Ordering::SeqCst), 0);
    }

    // ── 정상 상태의 기한 ────────────────────────────────────────────
    //
    // 실제로 5분을 기다리지 않는다. `Refresh` 는 시계를 **밖에서** 받으므로 순간을 손으로
    // 건네면 된다 — 갈래도 잠도 없다.

    const MINUTE: u64 = 60_000;

    #[test]
    fn a_quiet_project_is_not_read_again_until_five_minutes() {
        let counted = Arc::new(AtomicU64::new(0));
        let mut teller = Counting(counted.clone());
        // **실제 pace 로** 세운다 — 시험용 값이 아니라 제품이 쓰는 값이다.
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut Quiet);

        // 아무 일도 없다. 4분 59초까지 한 번도 읽지 않는다.
        for at in [1_000, MINUTE, 2 * MINUTE, 3 * MINUTE, 4 * MINUTE, 5 * MINUTE - 1_000] {
            engine.wake(Moment::at(at), Wake::Elapsed, &mut teller);
            assert_eq!(
                counted.load(Ordering::SeqCst),
                0,
                "{at}ms 에 조용한 Project 를 다시 읽었다"
            );
        }
        // 5분에 **한 번.**
        engine.wake(Moment::at(5 * MINUTE), Wake::Elapsed, &mut teller);
        assert_eq!(counted.load(Ordering::SeqCst), 1, "5분에 읽지 않았다");

        // 그리고 그 뒤 또 5분이 지나야 한 번 더다.
        engine.wake(Moment::at(9 * MINUTE), Wake::Elapsed, &mut teller);
        assert_eq!(counted.load(Ordering::SeqCst), 1, "기한이 다시 서지 않았다");
        engine.wake(Moment::at(10 * MINUTE), Wake::Elapsed, &mut teller);
        assert_eq!(counted.load(Ordering::SeqCst), 2);
    }

    #[test]
    fn a_hint_does_not_wait_five_minutes() {
        let counted = Arc::new(AtomicU64::new(0));
        let mut teller = Counting(counted.clone());
        let mut engine = Refresh::start(pace(), Moment::at(0), &mut Quiet);

        // 파일이 바뀌었다. debounce 만 지나면 곧바로 읽는다 — 5분을 기다리지 않는다.
        engine.wake(Moment::at(1_000), Wake::ChangeHint, &mut teller);
        assert_eq!(counted.load(Ordering::SeqCst), 0, "모으기도 전에 읽었다");
        engine.wake(Moment::at(1_300), Wake::ChangeHint, &mut teller);
        assert_eq!(counted.load(Ordering::SeqCst), 1, "hint 가 5분을 기다렸다");
        // 1.3초다. 5분의 1/230 이다.
        assert!(1_300 < 5 * MINUTE);
    }

    /// **Companion 은 5분, `gil monitor --serve` 는 30초.** 서로 건드리지 않는다.
    #[test]
    fn the_companion_pace_is_five_minutes_and_serve_keeps_its_own() {
        assert_eq!(pace().reconcile, Duration::from_secs(300), "Companion 이 5분이 아니다");
        assert_eq!(
            Pace::default().reconcile,
            Duration::from_secs(30),
            "serve 의 기본값이 바뀌었다"
        );
        // debounce 는 둘 다 짧다 — 사람이 기다리는 자리이기 때문이다.
        assert_eq!(pace().debounce, Duration::from_millis(250));
    }

    // ── 실패가 이어질 때의 사다리 ────────────────────────────────────

    #[test]
    fn the_retry_ladder_climbs_and_then_stops_climbing() {
        // 연속 실패 1,2,3,… 번째 뒤에 기다리는 시간.
        let want = [2, 4, 8, 16, 30, 60];
        for (at, secs) in want.iter().enumerate() {
            assert_eq!(
                retry_after(at + 1),
                Duration::from_secs(*secs),
                "{}번째 연속 실패의 기한이 다르다",
                at + 1
            );
        }
        // **60초에서 멈춘다.** 더 실패해도 늘지 않는다.
        for failures in [7, 8, 20, 1_000, usize::MAX] {
            assert_eq!(
                retry_after(failures),
                Duration::from_secs(60),
                "{failures}번 실패에서 상한을 넘었다"
            );
        }
        // 실패한 적이 없으면 첫 칸이다 — 곱셈도 넘침도 없다.
        assert_eq!(retry_after(0), Duration::from_secs(2));
    }

    /// `Refresh` 가 **같은 사다리**로 기한을 잡는지 — 시계를 손으로 돌려 잰다.
    #[test]
    fn each_failed_look_waits_exactly_the_next_rung() {
        /// 언제나 실패하는 관측.
        struct Broken(Arc<AtomicU64>);
        impl Observe<()> for Broken {
            fn observe(&mut self) -> Result<(), String> {
                self.0.fetch_add(1, Ordering::SeqCst);
                Err("안 된다".to_string())
            }
        }

        let looked = Arc::new(AtomicU64::new(0));
        let mut broken = Broken(looked.clone());
        let climbing = Pace {
            debounce: Duration::from_millis(250),
            reconcile: Duration::from_secs(5 * 60),
            retry: Backoff::ladder(RETRY),
        };
        // 첫 관측이 실패한다 — 연속 1회.
        let mut engine = Refresh::start(climbing, Moment::at(0), &mut broken);
        assert_eq!(looked.load(Ordering::SeqCst), 1);

        let mut at = 0u64;
        for (step, secs) in [2u64, 4, 8, 16, 30, 60, 60, 60].iter().enumerate() {
            let before = looked.load(Ordering::SeqCst);
            // **기한 직전에는 보지 않는다.**
            engine.wake(Moment::at(at + secs * 1_000 - 1), Wake::Elapsed, &mut broken);
            assert_eq!(
                looked.load(Ordering::SeqCst),
                before,
                "{step}번째 칸({secs}초) 직전에 보았다"
            );
            // **기한에 딱 한 번 본다.**
            at += secs * 1_000;
            engine.wake(Moment::at(at), Wake::Elapsed, &mut broken);
            assert_eq!(
                looked.load(Ordering::SeqCst),
                before + 1,
                "{step}번째 칸({secs}초)에 한 번 보지 않았다"
            );
        }
    }

    #[test]
    fn one_success_puts_the_ladder_back_on_its_first_rung() {
        /// 시험이 성패를 정하는 관측.
        struct Moody {
            works: Arc<std::sync::atomic::AtomicBool>,
            looked: Arc<AtomicU64>,
        }
        impl Observe<()> for Moody {
            fn observe(&mut self) -> Result<(), String> {
                self.looked.fetch_add(1, Ordering::SeqCst);
                match self.works.load(Ordering::SeqCst) {
                    true => Ok(()),
                    false => Err("안 된다".to_string()),
                }
            }
        }

        let works = Arc::new(std::sync::atomic::AtomicBool::new(false));
        let looked = Arc::new(AtomicU64::new(0));
        let mut moody = Moody { works: works.clone(), looked: looked.clone() };
        let climbing = Pace {
            debounce: Duration::from_millis(250),
            reconcile: Duration::from_secs(5 * 60),
            retry: Backoff::ladder(RETRY),
        };
        let mut engine = Refresh::start(climbing, Moment::at(0), &mut moody);

        // 두 번 더 실패해 사다리를 올린다: 2초, 4초.
        engine.wake(Moment::at(2_000), Wake::Elapsed, &mut moody);
        engine.wake(Moment::at(6_000), Wake::Elapsed, &mut moody);
        assert_eq!(looked.load(Ordering::SeqCst), 3);

        // 이번엔 통한다 — 8초 뒤.
        works.store(true, Ordering::SeqCst);
        engine.wake(Moment::at(14_000), Wake::Elapsed, &mut moody);
        assert_eq!(looked.load(Ordering::SeqCst), 4);

        // **다음 실패는 다시 2초부터다.**
        works.store(false, Ordering::SeqCst);
        // 성공했으니 이제 기한은 reconciliation(5분)이다.
        engine.wake(Moment::at(14_000 + 5 * 60_000), Wake::Elapsed, &mut moody);
        assert_eq!(looked.load(Ordering::SeqCst), 5, "5분 기한에 보지 않았다");
        let after_fail = 14_000 + 5 * 60_000;
        // 사다리가 처음으로 돌아갔다면 2초 뒤에 본다.
        engine.wake(Moment::at(after_fail + 1_999), Wake::Elapsed, &mut moody);
        assert_eq!(looked.load(Ordering::SeqCst), 5, "2초 전에 보았다");
        engine.wake(Moment::at(after_fail + 2_000), Wake::Elapsed, &mut moody);
        assert_eq!(looked.load(Ordering::SeqCst), 6, "다음 실패가 2초로 돌아가지 않았다");
    }

    #[test]
    fn a_change_hint_does_not_wait_for_the_backoff_to_expire() {
        // 긴 backoff 중이다 — 여섯 번 실패해 60초를 기다리는 중.
        let bench = Bench::start();
        for _ in 0..6 {
            bench.wishes.send(Wish::Failed).expect("넣는다");
        }
        bench.stays_quiet();

        // **hint 가 온다.** 60초를 기다리지 않고 debounce 만 지나면 청한다.
        //
        // 재는 것은 **실제로 흐른 시간**이다. `quiet_for` 가 준 값이 그대로 잠드는 시간이
        // 되므로, backoff 를 기다렸다면 여기서 60초가 실제로 지나간다. `wait_until` 의
        // 5초 기한이 그것을 잡는다.
        let started = Instant::now();
        bench.hint();
        bench.wait_until(1);
        let waited = started.elapsed();
        assert_eq!(bench.stop(), 1, "hint 가 backoff 를 기다렸다");
        assert!(
            waited < Duration::from_secs(5),
            "hint 가 {waited:?} 나 기다렸다 — 사다리(60초)를 기다린 것이다"
        );
    }

    #[test]
    fn a_success_during_backoff_clears_it() {
        let bench = Bench::start();
        for _ in 0..3 {
            bench.wishes.send(Wish::Failed).expect("넣는다");
        }
        // 사람이 새로고침을 눌러 성공했다 — 창이 그 사실을 알린다.
        bench.wishes.send(Wish::Worked).expect("넣는다");
        bench.stays_quiet();
        // backoff 가 걷혔으므로 옛 기한이 와도 청하지 않는다.
        bench.hand.tick(120_000);
        std::thread::sleep(Duration::from_millis(60));
        assert_eq!(bench.stop(), 0, "걷힌 backoff 가 아직 청했다");
    }

    /// 실패 횟수는 **그 Project 의 것**이다 — 전환하면 0 부터다(계약 5).
    #[test]
    fn a_new_project_starts_its_failures_at_zero() {
        let live = Live::default();
        let first = scratch("fail-a");
        let second = scratch("fail-b");
        let a = Arc::new(AtomicU64::new(0));
        let b = Arc::new(AtomicU64::new(0));

        live.follow_with("project:A", &first, || Box::new(Counting(a.clone())))
            .expect("A");
        // A 가 여러 번 실패했다.
        for _ in 0..5 {
            live.fetch_failed("project:A");
        }
        // 앞 Project 의 늦은 보고는 새 Project 에 닿지 않는다.
        live.follow_with("project:B", &second, || Box::new(Counting(b.clone())))
            .expect("B");
        live.fetch_failed("project:A");
        live.fetch_worked("project:A");

        // B 의 자리는 A 의 사정을 모른다 — 파일 하나에 곧바로 알린다.
        std::fs::write(second.join("나.txt"), "나").expect("적는다");
        until("B 의 자동 갱신", || b.load(Ordering::SeqCst) >= 1);
        live.stop();
    }

    /// **`gil monitor --serve` 는 2초 그대로다.**
    #[test]
    fn serve_keeps_a_flat_two_second_retry() {
        let serve = Pace::default().retry;
        for failures in [0, 1, 2, 5, 50, usize::MAX] {
            assert_eq!(
                serve.after(failures),
                Duration::from_secs(2),
                "{failures}번 실패에서 serve 의 간격이 달라졌다"
            );
        }
        assert_eq!(serve.ceiling(), Duration::from_secs(2));
    }

    // ── 눈이 없는 자리 ──────────────────────────────────────────────

    #[test]
    fn a_seat_without_a_watcher_says_it_cannot_see() {
        let (wishes, hear) = sync_channel::<Wish>(8);
        let blind = Watch {
            scope: "project:하나".to_string(),
            wishes,
            worker: None,
            watching: None,
        };
        assert!(!blind.sees(), "눈이 없는데 본다고 한다");
        drop(hear);
    }

    /// 같은 scope 라도 **눈이 없으면 다시 세운다**(계약 2).
    #[test]
    fn reselecting_a_blind_project_retries_instead_of_doing_nothing() {
        let code = running();
        let at = code.find("fn follow_with").expect("따라붙는 자리");
        let body = &code[at..];
        // no-op 은 scope 가 같고 **그리고** 눈이 있을 때뿐이다.
        assert!(
            body.contains("one.scope == scope && one.sees()"),
            "scope 만 보고 넘어간다"
        );
        // 그 밖에는 앞의 자리를 걷어내고 처음부터 세운다.
        let noop = body.find("one.sees()").expect("판정");
        let tear = body.find("old.stop()").expect("걷어내는 자리");
        assert!(noop < tear, "판정보다 먼저 걷어낸다");
    }

    // ── 눈이 없다가 다시 얻는다 ──────────────────────────────────────

    fn scratch(label: &str) -> std::path::PathBuf {
        let dir = std::env::temp_dir().join(format!("gil-live-{label}"));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("자리를 만든다");
        dir
    }

    /// 조건이 될 때까지 본다. 되지 않으면 **시험이 실패한다.**
    fn until(what: &str, mut ready: impl FnMut() -> bool) {
        let deadline = Instant::now() + Duration::from_secs(10);
        while !ready() {
            assert!(Instant::now() < deadline, "{what} 를 기다리다 지쳤다");
            std::thread::yield_now();
        }
    }

    #[test]
    fn a_project_that_could_not_be_watched_is_watched_when_chosen_again() {
        let live = Live::default();
        let scope = "project:다시고른다";
        let counted = Arc::new(AtomicU64::new(0));
        let teller = || -> Box<dyn Observe<()> + Send> { Box::new(Counting(counted.clone())) };

        // ① **첫 시작이 실패한다** — 있지도 않은 자리를 보라고 한다.
        let gone = scratch("retry").join("없는-자리");
        let said = live.follow_with(scope, &gone, teller).expect_err("감시가 설 수 없다");
        assert!(!said.is_empty(), "왜 못 섰는지 말하지 않는다");
        // 그래도 자리는 잡혔다 — worker 는 돌고, 느린 기한이 수렴을 맡는다.
        assert_eq!(live.following().as_deref(), Some(scope), "자리를 잡지 못했다");
        assert!(!live.sees(), "눈이 없는데 있다고 한다");

        // ② **같은 Project 를 다시 고른다.** 이번엔 자리가 있다.
        let root = scratch("retry-real");
        live.follow_with(scope, &root, teller).expect("이번엔 선다");

        // ③ 눈이 생겼다.
        assert_eq!(live.following().as_deref(), Some(scope));
        assert!(live.sees(), "다시 골랐는데 눈이 생기지 않았다");

        // ④ 그리고 **파일 변화가 실제로 hint 를 낳는다.**
        std::fs::write(root.join("바뀐다.txt"), "가").expect("적는다");
        until("자동 갱신", || counted.load(Ordering::SeqCst) >= 1);
        let told = counted.load(Ordering::SeqCst);

        // ⑤ 눈이 생긴 뒤 같은 것을 또 고르면 **아무 일도 없다** — 겹치지 않는다.
        live.follow_with(scope, &root, teller).expect("이미 보고 있다");
        assert!(live.sees());
        std::thread::sleep(Duration::from_millis(120));
        assert_eq!(
            counted.load(Ordering::SeqCst),
            told,
            "다시 고르자 감시가 겹쳐 두 번 알렸다"
        );

        live.stop();
        assert_eq!(live.following(), None, "멈춘 뒤에도 자리가 남았다");
    }

    #[test]
    fn switching_projects_leaves_exactly_one_watcher() {
        let live = Live::default();
        let first = scratch("switch-a");
        let second = scratch("switch-b");
        let a = Arc::new(AtomicU64::new(0));
        let b = Arc::new(AtomicU64::new(0));

        live.follow_with("project:A", &first, || Box::new(Counting(a.clone())))
            .expect("A 를 본다");
        assert_eq!(live.following().as_deref(), Some("project:A"));

        live.follow_with("project:B", &second, || Box::new(Counting(b.clone())))
            .expect("B 를 본다");
        // **하나뿐이다.**
        assert_eq!(live.following().as_deref(), Some("project:B"));

        // B 를 건드리면 알린다.
        std::fs::write(second.join("나.txt"), "나").expect("적는다");
        until("B 의 자동 갱신", || b.load(Ordering::SeqCst) >= 1);

        // **A 를 건드려도 아무 일도 없다** — A 의 감시는 끝났다.
        let quiet = a.load(Ordering::SeqCst);
        for at in 0..5 {
            std::fs::write(first.join(format!("가-{at}.txt")), "가").expect("적는다");
        }
        std::thread::sleep(Duration::from_millis(500));
        assert_eq!(a.load(Ordering::SeqCst), quiet, "끝난 A 의 감시가 아직 산다");

        live.stop();
    }

    // ── 이 파일이 하지 않는 일 ──────────────────────────────────────

    fn running() -> String {
        let source = include_str!("live.rs");
        let body = source.split_once("#[cfg(test)]").map(|(one, _)| one).unwrap_or(source);
        body.lines()
            .filter(|line| !line.trim_start().starts_with("//"))
            .collect::<Vec<_>>()
            .join("\n")
    }

    /// **hint 는 사실을 나르지 않는다**(§8 · 계약 2·3).
    #[test]
    fn the_hint_carries_no_path_no_kind_no_content() {
        let code = running();
        // 창으로 나가는 것은 이름 하나뿐이고 payload 가 없다.
        assert!(code.contains(r#"emit(HINT, ())"#), "hint 에 무언가를 실었다");
        // 경로·사건 종류를 만지는 자리가 없다.
        for forbidden in ["event.paths", "EventKind", "notify::", "path.display", "to_string_lossy"] {
            assert!(!code.contains(forbidden), "hint 가 {forbidden} 를 만진다");
        }
        // 그리고 Project 를 열거나 판정하지 않는다.
        for forbidden in ["ProjectSession", "STATE_PATH", "view_of(", "detail_of(", "monitor_view_v1"] {
            assert!(!code.contains(forbidden), "watcher 가 {forbidden} 로 사실을 만든다");
        }
        // 설정에도 남기지 않는다.
        for forbidden in ["Desk", "settings::", "CompanionSettings"] {
            assert!(!code.contains(forbidden), "watcher 가 설정({forbidden})을 만진다");
        }
    }

    /// 지켜보는 것은 **하나뿐**이고, 바꿀 때는 앞의 것을 끝낸다(계약 1).
    #[test]
    fn only_one_project_is_watched_and_switching_ends_the_old_one() {
        let code = running();
        let body = {
            let at = code.find("fn follow_with").expect("따라붙는 자리");
            &code[at..]
        };
        // 같은 것을 다시 고르면 세우지 않는다 — **눈이 붙어 있을 때만.**
        assert!(
            body.contains("one.scope == scope && one.sees()"),
            "같은 scope 를 가려내지 않는다"
        );
        // 다른 것이면 앞의 것을 **끝낸다.**
        assert!(body.contains("old.stop()"), "앞의 감시를 끝내지 않는다");
        // 자리는 하나다.
        assert!(code.contains("Option<Watch>"), "여러 감시를 담는 자리가 있다");
        // 그리고 멈춤은 **기다린다** — 떨어뜨리기만 하면 갈래가 남는다.
        let stopping = {
            let at = code.find("fn stop(mut self)").expect("멈추는 자리");
            &code[at..]
        };
        assert!(stopping.contains("worker.join()"), "갈래가 멈추기를 기다리지 않는다");
    }

    /// 감시를 세우지 못해도 **거절하지 않는다**(계약 6 · Monitor §8.6.1).
    #[test]
    fn a_watcher_that_cannot_start_does_not_take_the_window_down() {
        let code = running();
        let at = code.find("fn follow_with").expect("따라붙는 자리");
        let body = &code[at..];
        // 실패해도 worker 는 선다 — 느린 기한이 수렴을 맡는다.
        let spawn = body.find("thread::spawn").expect("갈래를 세우는 자리");
        let watch = body.find("watch_hints").expect("감시를 세우는 자리");
        assert!(watch < spawn, "감시가 실패하면 갈래도 세우지 않는다");
        assert!(body.contains("Err(said) => (None, Some(said))"), "실패를 사실로 남기지 않는다");
        // 그리고 그 실패가 `Err` 로 나가 창이 한 번 말할 수 있다.
        assert!(body.contains("Some(said) => Err(said)"), "실패를 삼킨다");
    }
}
