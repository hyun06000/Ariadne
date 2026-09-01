//! **loopback 하나에만 열리는 작은 창** — 마지막으로 검증된 화면을 내보내는 자리.
//!
//! 범용 HTTP server 가 아니다. 이 파일이 아는 문법은 **한 종류의 요청**뿐이고, 그 밖의
//! 모든 것은 거절한다. 관대하게 해석하지 않는 것이 여기서는 기능이다 — 넓게 읽을수록
//! 이 창으로 들어올 수 있는 모양이 늘어난다.
//!
//! # 무엇으로 지키는가
//!
//! ```text
//! 127.0.0.1 에만 bind          LAN 도 IPv6 wildcard 도 아니다
//! OS 가 고른 port              고정 port 를 예측당하지 않는다
//! 매 실행마다 새 capability     OS CSPRNG 256bit · 프로세스 메모리에만 산다
//! exact Host 검사              DNS rebinding 이 이 창을 겨누지 못하게
//! exact path 검사              정규화도, percent-decoding 도, query 도 없다
//! GET · HEAD 만                상태를 바꾸는 method 가 닿을 자리가 없다
//! 좁은 상한과 timeout          한 연결이 이 창을 붙들지 못하게
//! ```
//!
//! 다섯 가지가 **전부 맞을 때만** 화면이 나간다. 하나라도 어긋나면 프로젝트의 사실이 한
//! 글자도 실리지 않은 응답이 돌아간다.
//!
//! # 잠금은 관측하는 동안만
//!
//! 이 파일의 어떤 구조체도 [`ProjectSession`] 도, 잠금 guard 도, 파일 handle 도 들고 있지
//! 않는다. 잠금은 [`Observe::observe`] 안에서 잡혔다가 그 함수가 값을 돌려주기 전에 풀린다.
//! browser 창이 열려 있다는 이유로 다른 GIL 명령이 막히지 않는다.
//!
//! # 아직 표면에 없다
//!
//! `gil monitor --serve` 는 A2c 의 watcher 와 실사용 검증이 끝난 뒤에 연다. 그때까지 이
//! 창은 crate 안에서만 열리고, 아래 `allow` 는 그 사실을 적어 둔 것이다.
#![allow(dead_code)]

use std::io::{self, BufReader, Read, Write};
use std::net::{Ipv4Addr, SocketAddr, SocketAddrV4, TcpListener, TcpStream};
use std::path::Path;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::mpsc::{Receiver, RecvTimeoutError, SyncSender, sync_channel};
use std::sync::Arc;
use std::thread::JoinHandle;
use std::time::{Duration, Instant};

use super::refresh::{Moment, Observe, Pace, Refresh, Wake, render_cached_page};

// ── 좁은 문 ────────────────────────────────────────────────────────────────

/// 요청 첫 줄이 이보다 길면 읽지 않는다.
const REQUEST_LINE_MAX: usize = 2048;
/// header 전체가 이보다 크면 읽지 않는다.
const HEADERS_BYTES_MAX: usize = 8192;
/// header 가 이보다 많으면 읽지 않는다.
const HEADERS_MAX: usize = 64;
/// 한 연결에서 요청을 다 읽기까지 기다리는 시간.
const READ_TIMEOUT: Duration = Duration::from_secs(2);
/// 화면이 스스로를 다시 받아오는 주기.
const REFRESH_SECONDS: u64 = 2;

/// 사건 통로가 담아 두는 최대 개수.
///
/// **넘치면 버린다.** hint 는 「다시 보라」는 말 한 마디라서 백 개나 한 개나 뜻이 같고,
/// 쌓아 두면 그것이 곧 무제한으로 자라는 대기열이 된다.
const EVENTS_MAX: usize = 64;

/// worker 가 화면 한 장을 건네주기까지 기다리는 시간의 상한.
///
/// worker 가 관측 중이면 잠깐 늦는다. 그러나 **영원히 기다리지는 않는다** — 그러면 느린
/// 관측 하나가 연결 하나를 붙들어 두게 된다.
const SCREEN_WAIT: Duration = Duration::from_secs(10);

/// **문서 안의 자물쇠를 문서 밖에도 건다.**
///
/// renderer 의 meta CSP 와 뜻이 같되 두 가지를 더 적는다. `frame-ancestors` 는 meta 로는
/// 아예 무시되는 지시어라 header 에서만 힘을 갖고, `media-src` 는 `default-src 'none'` 에
/// 이미 덮이지만 소리 없이 덮인 것보다 적힌 편이 낫다.
///
/// **오류 응답에도 똑같이 붙는다.** 정상 화면만 지키면 지키지 않은 쪽이 길이 된다.
///
/// 두 자리에 적힌 값이라 한쪽이 낡을 수 있다 — 그래서 시험이 둘을 지시어 단위로 맞춰 본다
/// (`the_header_csp_says_the_same_as_the_meta_csp`).
const CSP: &str = "Content-Security-Policy: default-src 'none'; style-src 'unsafe-inline'; \
img-src 'none'; media-src 'none'; font-src 'none'; connect-src 'none'; script-src 'none'; \
object-src 'none'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'\r\n";

// ── 자물쇠 ─────────────────────────────────────────────────────────────────

/// 이 실행에서만 사는 **capability** — 이 글자를 아는 요청만 화면을 받는다.
///
/// 시각도 PID 도 프로세스 안의 의사난수도 쓰지 않는다. 그런 값은 밖에서 좁힐 수 있고,
/// 좁힐 수 있는 자물쇠는 자물쇠가 아니다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Capability(String);

/// OS 가 주는 난수의 자리.
///
/// std 에는 CSPRNG 이 없다. 새 crate 를 들이는 대신 **운영체제가 직접 주는 통로**를 읽는다 —
/// 이것이 `getrandom` 류 crate 가 Unix 에서 하는 일과 같은 일이다.
const ENTROPY: &str = "/dev/urandom";

/// capability 한 개의 바이트 수 — 256bit. 명세가 요구하는 최소의 두 배다.
const TOKEN_BYTES: usize = 32;

impl Capability {
    /// **OS 에게 물어서** 하나 만든다.
    ///
    /// 난수를 안전하게 얻지 못하면 만들지 않는다(Monitor Model §8.2). 약한 값으로 물러서는
    /// 길을 두지 않는 까닭은 하나다 — 그 길은 실패한 날에만 쓰이고, 실패한 날에 가장
    /// 위험하다.
    pub(crate) fn new() -> Result<Capability, ServeError> {
        Capability::from_source(ENTROPY)
    }

    /// 난수의 출처를 시험이 바꿔 낄 수 있는 자리.
    fn from_source(source: &str) -> Result<Capability, ServeError> {
        let mut bytes = [0u8; TOKEN_BYTES];
        let mut file = std::fs::File::open(source).map_err(|source| ServeError::NoEntropy {
            said: source.to_string(),
        })?;
        // **짧게 읽힌 것을 그대로 쓰지 않는다.** 채워지지 않은 뒤쪽은 0 이고, 그러면
        // 자물쇠의 절반이 상수가 된다.
        file.read_exact(&mut bytes)
            .map_err(|source| ServeError::NoEntropy {
                said: source.to_string(),
            })?;

        // 소문자 hex — canonical 하고 URL 에서 그대로 쓸 수 있다. 창고 주소가 쓰는 것과
        // 같은 표기라 새 인코더를 짓지 않는다.
        let mut token = String::with_capacity(TOKEN_BYTES * 2);
        for byte in bytes {
            let _ = write!(token, "{byte:02x}");
        }
        Ok(Capability(token))
    }

    /// 이 창의 유일한 주소.
    fn path(&self) -> String {
        format!("/{}", self.0)
    }
}

use std::fmt::Write as _;

// ── 창 ─────────────────────────────────────────────────────────────────────

/// 열려 있는 창 하나. **떨어지면 닫힌다.**
pub(crate) struct Monitor {
    address: SocketAddr,
    path: String,
    stop: Arc<AtomicBool>,
    /// 사건 통로의 보내는 끝 — 닫을 때 `Stop` 을 넣는 자리이기도 하다.
    wishes: SyncSender<Wish>,
    /// 연결을 받아 요청을 읽고 답을 쓰는 갈래.
    greeter: Option<JoinHandle<()>>,
    /// `Refresh` 를 소유하고 세 사건을 한 자리에서 처리하는 갈래.
    worker: Option<JoinHandle<()>>,
    /// 파일 감시. **떨어지면 감시도 끝난다** — 그래서 값으로 들고 있는다.
    ///
    /// 감시가 서지 못했으면 그 까닭이 여기 남고, 화면이 그것을 말한다.
    watcher: Option<Box<dyn std::any::Any + Send>>,
    blind: Option<String>,
}

impl std::fmt::Debug for Monitor {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // **token 을 적지 않는다.** 사람이 무심코 이 값을 로그에 흘리는 자리다.
        f.debug_struct("Monitor")
            .field("address", &self.address)
            .field("watching", &self.blind.is_none())
            .finish_non_exhaustive()
    }
}

impl Monitor {
    /// 사람이 브라우저에 붙여 넣을 주소 하나.
    pub(crate) fn url(&self) -> String {
        format!("http://{}{}", self.address, self.path)
    }

    pub(crate) fn address(&self) -> SocketAddr {
        self.address
    }

    /// 이 창의 capability path. **token 자체를 따로 내보이지 않는다.**
    pub(crate) fn path(&self) -> &str {
        &self.path
    }

    /// 시험이 감시를 흉내 내어 hint 하나를 넣는 자리.
    ///
    /// 진짜 파일 사건과 **같은 통로로** 들어간다 — 그래야 debounce 와 합침을 재는 것이
    /// 실제로 도는 길을 재는 것이 된다.
    #[cfg(test)]
    fn hint(&self) {
        let _ = self.wishes.try_send(Wish::Hint);
    }

    /// 감시가 서지 못했으면 그 까닭.
    pub(crate) fn blind(&self) -> Option<&str> {
        self.blind.as_deref()
    }

    /// **확실히 닫는다.** 셋을 모두 끝내고 join 한다.
    ///
    /// 순서가 있다. ① 감시를 먼저 떨어뜨려 새 hint 가 더 오지 않게 하고, ② 두 갈래에게
    /// 그만두라고 알린 뒤, ③ 잠들어 있는 accept 를 스스로 두드려 깨운다. 그러고 나서
    /// 기다린다.
    ///
    /// 두 번 불러도 안전하다. 값이 떨어질 때도 같은 일이 일어난다.
    pub(crate) fn close(&mut self) {
        // ① 감시부터 떨어뜨린다.
        drop(self.watcher.take());
        // ② 두 갈래에게 알린다.
        self.stop.store(true, Ordering::SeqCst);
        let _ = self.wishes.try_send(Wish::Stop);
        // ③ accept 는 연결이 올 때까지 잠들어 있다. 스스로에게 한 번 두드려 깨운다 —
        //    짧은 주기로 깨어나 확인하는 것보다 정확하고, 도는 동안 아무 일도 하지 않는다.
        let _ = TcpStream::connect(self.address);
        if let Some(greeter) = self.greeter.take() {
            let _ = greeter.join();
        }
        if let Some(worker) = self.worker.take() {
            let _ = worker.join();
        }
    }
}

impl Drop for Monitor {
    fn drop(&mut self) {
        self.close();
    }
}

/// 창을 열 수 없는 이유.
#[derive(Debug)]
pub(crate) enum ServeError {
    /// 난수를 안전하게 얻지 못했다 — 그래서 열지 않는다.
    NoEntropy { said: String },
    /// loopback 에 자리를 얻지 못했다.
    NoAddress { said: String },
}

impl std::fmt::Display for ServeError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ServeError::NoEntropy { said } => write!(
                f,
                "안전한 난수를 얻지 못해 Monitor 창을 열지 않았다 — {said}"
            ),
            ServeError::NoAddress { said } => {
                write!(f, "127.0.0.1 에 자리를 얻지 못했다 — {said}")
            }
        }
    }
}

impl std::error::Error for ServeError {}

/// 지금 몇 눈금인가 — 시험이 대신 답할 수 있는 자리.
pub(crate) type Clock = Box<dyn Fn() -> Moment + Send>;

// ── 사건 하나 ──────────────────────────────────────────────────────────────

/// worker 가 처리하는 **세 가지 사건, 그리고 그만두라는 말.**
///
/// 셋을 한 통로로 모으는 까닭은 하나다 — `Refresh` 를 한 갈래만 소유하면 잠금도, 경합도,
/// 「지금 상태가 무엇인가」를 둘이 다르게 보는 순간도 없다.
enum Wish {
    /// 화면 한 장 주세요 — 답은 이 통로로.
    Screen(SyncSender<String>),
    /// 무언가 바뀌었을지도 모른다. **그뿐이다.**
    Hint,
    /// 그만.
    Stop,
}

/// **창을 연다.**
///
/// `127.0.0.1` 에만, OS 가 고른 port 로. 여는 데 성공하면 곧바로 한 번 관측해 화면을
/// 준비한다 — 첫 요청이 오기 전에 상태가 셋 중 하나로 정해져 있게.
///
/// # 갈래가 둘인 까닭
///
/// ```text
/// greeter   연결을 받아 요청을 읽고 답을 쓴다      바깥의 속도에 매인다
/// worker    Refresh 를 소유하고 세 사건을 처리한다  바깥의 속도에 매이지 않는다
/// ```
///
/// 한 갈래에 둘을 함께 두면 **느린 client 하나가 시계를 멈춘다** — 요청을 읽느라 기다리는
/// 동안 debounce 도 reconciliation 도 오지 않는다. 갈래를 갈라 두면 greeter 가 아무리
/// 오래 기다려도 worker 는 제 기한대로 깨어난다.
///
/// `watch` 가 `Some` 이면 그 자리를 감시한다. 감시가 서지 못해도 창은 연다 — 까닭은
/// [`Monitor::blind`] 를 보라.
pub(crate) fn serve(
    mut observer: Box<dyn Observe + Send>,
    pace: Pace,
    clock: Clock,
    watch: Option<&Path>,
) -> Result<Monitor, ServeError> {
    let capability = Capability::new()?;
    let path = capability.path();

    // **loopback 하나에만.** `0.0.0.0` 도, `::` 도, LAN 주소도 아니다. port 0 은
    // 「네가 골라라」라는 뜻이고, 그래서 이 창의 자리는 미리 알 수 없다.
    let listener = TcpListener::bind(SocketAddrV4::new(Ipv4Addr::LOCALHOST, 0)).map_err(
        |said| ServeError::NoAddress {
            said: said.to_string(),
        },
    )?;
    let address = listener.local_addr().map_err(|said| ServeError::NoAddress {
        said: said.to_string(),
    })?;

    let engine = Refresh::start(pace, clock(), &mut *observer);
    let stop = Arc::new(AtomicBool::new(false));
    // **상한이 있는 통로.** 넘치면 hint 를 버린다 — 뜻이 같은 말을 쌓아 둘 이유가 없다.
    let (wishes, incoming) = sync_channel(EVENTS_MAX);

    let (watcher, blind) = match watch {
        Some(root) => match watch_project(root, wishes.clone()) {
            Ok(watcher) => (Some(watcher), None),
            // **감시 실패를 숨기지 않는다.** 창은 열되 화면이 그렇다고 말한다.
            Err(said) => (None, Some(said)),
        },
        None => (None, None),
    };
    let blind_for_worker = blind.clone();

    let worker = std::thread::spawn({
        let path = path.clone();
        move || tend(incoming, engine, observer, clock, path, blind_for_worker)
    });

    let greeter = std::thread::spawn({
        let stop = Arc::clone(&stop);
        let wishes = wishes.clone();
        let path = path.clone();
        let host = address.to_string();
        move || greet(listener, stop, wishes, path, host)
    });

    Ok(Monitor {
        address,
        path,
        stop,
        wishes,
        greeter: Some(greeter),
        worker: Some(worker),
        watcher,
        blind,
    })
}

/// **한 번에 한 연결.** thread 를 요청마다 만들지 않는다.
///
/// 요청을 읽고 답을 쓰는 일만 한다. 무엇을 그릴지는 알지 못하고 worker 에게 묻는다.
fn greet(
    listener: TcpListener,
    stop: Arc<AtomicBool>,
    wishes: SyncSender<Wish>,
    path: String,
    host: String,
) {
    for stream in listener.incoming() {
        if stop.load(Ordering::SeqCst) {
            return;
        }
        let Ok(mut stream) = stream else {
            continue;
        };
        let _ = stream.set_read_timeout(Some(READ_TIMEOUT));
        let _ = stream.set_write_timeout(Some(READ_TIMEOUT));

        let answer = match read_request(&mut stream, &host, &path) {
            Ok(asked) => match ask_for_screen(&wishes) {
                Some(page) => Answer::page(asked, page),
                // worker 가 제때 답하지 못했다. 프로젝트의 사실을 지어내지 않는다.
                None => Refused::Malformed.answer(),
            },
            Err(refused) => refused.answer(),
        };
        let _ = answer.write_to(&mut stream);
        // **한 요청 뒤 닫는다.** 오래 사는 연결을 만들지 않는다.
        //
        // 읽는 쪽까지 함께 닫지 않는다. 닫아 두면 상대가 보내는 FIN 이 RST 가 되고, RST 는
        // **아직 나가지 않은 응답을 버린다** — 실측으로 6KB 화면이 2.5KB 에서 잘렸다.
        // 쓰는 쪽만 닫아 FIN 을 보내고, 값이 떨어질 때 나머지가 닫힌다.
        let _ = stream.shutdown(std::net::Shutdown::Write);
    }
}

/// worker 에게 화면 한 장을 청한다 — **상한을 두고 기다린다.**
fn ask_for_screen(wishes: &SyncSender<Wish>) -> Option<String> {
    let (reply, answer) = sync_channel(1);
    wishes.try_send(Wish::Screen(reply)).ok()?;
    answer.recv_timeout(SCREEN_WAIT).ok()
}

/// **세 사건을 한 자리에서 처리한다.** `Refresh` 를 소유한 유일한 갈래.
///
/// ```text
/// Wish::Screen   → Wake::ScreenRead   기한 전이면 관측하지 않는다
/// Wish::Hint     → Wake::ChangeHint   debounce 를 시작한다(이미 시작했으면 합쳐진다)
/// 시간이 다 됨   → Wake::Elapsed      browser 가 없어도 기한은 온다
/// ```
///
/// 잠드는 시간은 [`Refresh::quiet_for`] 가 정한다 — 다음 기한까지 정확히 그만큼. 그래서
/// 아무 일도 없는 구간에서 헛되이 깨지 않고, debounce 가 끝나는 순간도 놓치지 않는다.
fn tend(
    incoming: Receiver<Wish>,
    mut engine: Refresh,
    mut observer: Box<dyn Observe + Send>,
    clock: Clock,
    path: String,
    blind: Option<String>,
) {
    loop {
        // **한 사건 처리에 시각 한 번.** 판정과 그리기가 같은 순간을 본다.
        let quiet = engine.quiet_for(clock());
        let wish = incoming.recv_timeout(quiet);
        let now = clock();
        match wish {
            Ok(Wish::Screen(reply)) => {
                let cached = engine.wake(now, Wake::ScreenRead, &mut *observer);
                let page = render_cached_page(
                    cached,
                    Some((REFRESH_SECONDS, &path)),
                    blind.as_deref(),
                );
                // 받을 사람이 이미 떠났어도 그것뿐이다.
                let _ = reply.try_send(page);
            }
            // hint 는 **모으기만 한다.** 여기서 관측하지 않는 것이 debounce 다.
            Ok(Wish::Hint) => {
                engine.wake(now, Wake::ChangeHint, &mut *observer);
            }
            Ok(Wish::Stop) => return,
            // 기한이 왔다 — browser 가 한 번도 오지 않았어도.
            Err(RecvTimeoutError::Timeout) => {
                engine.wake(now, Wake::Elapsed, &mut *observer);
            }
            // 보내는 끝이 모두 사라졌다. 더 올 사건이 없다.
            Err(RecvTimeoutError::Disconnected) => return,
        }
    }
}

// ── 요청 ───────────────────────────────────────────────────────────────────

/// 이 창이 아는 요청 — **오직 이 하나.**
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Asked {
    /// 화면 전체를 달라.
    Get,
    /// 머리만 달라 — 같은 status 와 header, 그러나 본문은 없다.
    Head,
}

/// 요청을 받아들일 수 없는 이유. **어느 것도 프로젝트의 사실을 담지 않는다.**
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum Refused {
    /// 문법이 이 창이 아는 것이 아니다 — 길이·모양·중복·본문·upgrade.
    Malformed,
    /// GET 도 HEAD 도 아니다.
    Method,
    /// 이 창의 주소가 아니다. **틀린 token 과 없는 path 를 가르지 않는다.**
    Elsewhere,
}

impl Refused {
    fn answer(self) -> Answer {
        match self {
            Refused::Malformed => Answer::refusal(400, "Bad Request"),
            Refused::Method => Answer::refusal(405, "Method Not Allowed"),
            Refused::Elsewhere => Answer::refusal(404, "Not Found"),
        }
    }
}

/// **좁게 읽는다.** 아는 모양 하나를 확인하고, 그 밖의 모든 것을 거절한다.
///
/// 검사 순서가 중요하다 — Host 를 path 보다 **먼저** 본다. 그래야 Host 가 틀린 탐색이
/// path 가 맞았는지 아닌지를 알아내는 통로가 되지 않는다.
fn read_request(stream: &mut TcpStream, host: &str, path: &str) -> Result<Asked, Refused> {
    let mut reader = BufReader::new(stream);

    // ── 첫 줄 ────────────────────────────────────────────────────────────
    let line = read_line(&mut reader, REQUEST_LINE_MAX)?;
    let mut parts = line.split(' ');
    let (method, target, version) = match (parts.next(), parts.next(), parts.next(), parts.next()) {
        (Some(method), Some(target), Some(version), None) => (method, target, version),
        // 칸이 셋이 아니면 이 창이 아는 모양이 아니다. 빈 칸이 섞인 target 도 여기서 걸린다.
        _ => return Err(Refused::Malformed),
    };
    // **`HTTP/1.1` 하나뿐이다.** 1.0 은 `Host` 를 요구하지 않는 규약이라, 받아 주면
    // Host 검사를 우회하려는 요청에게 「그 검사가 없던 시절」이라는 이름표를 내주게 된다.
    if version != "HTTP/1.1" {
        return Err(Refused::Malformed);
    }
    let asked = match method {
        "GET" => Asked::Get,
        "HEAD" => Asked::Head,
        _ => return Err(Refused::Method),
    };
    // **origin-form 하나만.** absolute-form(`http://…`)도 authority-form(`host:port`)도
    // asterisk-form(`*`)도 받지 않는다 — proxy 로 쓰이는 모양들이다.
    if !target.starts_with('/') {
        return Err(Refused::Malformed);
    }
    // query 도 fragment 도 별칭이다. 정규화하지도, percent-decoding 하지도 않는다 —
    // 해석을 늘리면 같은 자리를 가리키는 글자가 늘어난다.
    if target.contains('?') || target.contains('#') || target.contains('%') {
        return Err(Refused::Malformed);
    }

    // ── header ───────────────────────────────────────────────────────────
    let mut hosts = 0usize;
    let mut host_matches = false;
    let mut lengths = 0usize;
    let mut bytes = 0usize;
    let mut count = 0usize;
    loop {
        let line = read_line(&mut reader, REQUEST_LINE_MAX)?;
        if line.is_empty() {
            break;
        }
        bytes += line.len();
        count += 1;
        if bytes > HEADERS_BYTES_MAX || count > HEADERS_MAX {
            return Err(Refused::Malformed);
        }
        // **obs-fold 를 받지 않는다.** 공백으로 시작하는 줄은 「앞 header 의 이어짐」이라는
        // 옛 문법이고, 앞뒤를 다르게 읽는 두 해석기 사이에 header 를 밀어 넣는 통로다.
        if line.starts_with(' ') || line.starts_with('\t') {
            return Err(Refused::Malformed);
        }
        let Some((name, value)) = line.split_once(':') else {
            return Err(Refused::Malformed);
        };
        // 이름은 HTTP token 문법뿐이다 — 앞뒤 공백도, 안의 공백·탭도, 빈 이름도,
        // 제어 문자도, ASCII 밖의 글자도 이 검사에서 함께 걸린다.
        if !is_token(name) {
            return Err(Refused::Malformed);
        }
        let name = name.to_ascii_lowercase();
        // 값의 양옆 공백은 SP 와 HTAB 뿐이다(OWS).
        let value = value.trim_matches(|c| c == ' ' || c == '\t');
        match name.as_str() {
            "host" => {
                hosts += 1;
                // **정확히 같아야 한다.** 이름으로 온 것도, port 를 뺀 것도 아니다.
                host_matches = value == host;
            }
            // 본문도, 연결 승격도 받지 않는다.
            "transfer-encoding" | "upgrade" | "expect" => return Err(Refused::Malformed),
            "content-length" => {
                lengths += 1;
                // 없거나, 정확히 하나의 `0` 이거나. 둘이면 그 자체로 거절이다 —
                // 값이 같아도 마찬가지다.
                if value != "0" || lengths > 1 {
                    return Err(Refused::Malformed);
                }
            }
            // 문법이 맞는 모르는 header 는 뜻을 주지 않고 지나친다.
            _ => {}
        }
    }
    // 하나도 없거나 둘 이상이면 거절한다 — 둘이면 어느 쪽을 믿을지 정해야 하는데,
    // 그 선택 자체가 우회로가 된다. 대소문자가 달라도 같은 이름으로 센다.
    if hosts != 1 || !host_matches {
        return Err(Refused::Malformed);
    }

    // ── 주소 ─────────────────────────────────────────────────────────────
    //
    // **바이트가 같아야 한다.** 앞부분만 맞는 것도, 뒤에 무언가 붙은 것도 남이다.
    match target == path {
        true => Ok(asked),
        false => Err(Refused::Elsewhere),
    }
}

/// 한 줄을 읽는다 — **정확히 `\r\n` 으로 끝나야 하고, 상한을 넘으면 멈춘다.**
///
/// LF 하나로 끝나는 줄을 줄로 쳐 주지 않는다. 관대한 해석기와 엄격한 해석기가 같은
/// 바이트를 다르게 자르는 것이 request smuggling 의 재료이고, 여기서 관대한 쪽이 되지
/// 않는 가장 싼 방법은 **한 가지 끝만 아는 것**이다.
fn read_line(reader: &mut BufReader<&mut TcpStream>, limit: usize) -> Result<String, Refused> {
    let mut raw = Vec::new();
    let mut taken = 0usize;
    loop {
        let mut byte = [0u8; 1];
        match reader.read(&mut byte) {
            Ok(0) => return Err(Refused::Malformed), // 끊겼다
            Ok(_) => {}
            // timeout 도 여기로 온다 — 부분 요청은 기다리다 끝난다.
            Err(_) => return Err(Refused::Malformed),
        }
        taken += 1;
        if taken > limit {
            return Err(Refused::Malformed);
        }
        match byte[0] {
            b'\n' => {
                // 바로 앞이 CR 이 아니면 이 줄은 끝난 적이 없다.
                if raw.pop() != Some(b'\r') {
                    return Err(Refused::Malformed);
                }
                break;
            }
            // CR 은 일단 담는다 — 다음이 LF 일 때만 위에서 지워진다. 아니면 아래
            // 「중간 CR」 검사에 남아 걸린다.
            b'\r' => raw.push(b'\r'),
            // HTAB 하나만 예외다. 값의 양옆 공백으로 정당하게 쓰인다.
            b'\t' => raw.push(b'\t'),
            // NUL 을 포함한 그 밖의 C0 제어 문자와 DEL 은 요청에 들어올 자리가 없다.
            b if b < 0x20 || b == 0x7f => return Err(Refused::Malformed),
            b => raw.push(b),
        }
    }
    // 줄 한가운데의 CR — `\r\n` 으로 끝나지 못한 CR 이 여기 남는다.
    if raw.contains(&b'\r') {
        return Err(Refused::Malformed);
    }
    String::from_utf8(raw).map_err(|_| Refused::Malformed)
}

/// HTTP token 문법인가 — header 이름이 지나야 하는 유일한 문.
///
/// RFC 9110 의 `tchar` 그대로다. 빈 이름, 앞뒤·안의 공백과 탭, 제어 문자, ASCII 밖의
/// 글자가 **하나의 검사**로 함께 걸린다.
fn is_token(name: &str) -> bool {
    !name.is_empty()
        && name
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || b"!#$%&'*+-.^_`|~".contains(&b))
}

// ── 응답 ───────────────────────────────────────────────────────────────────

/// 내보낼 한 통.
struct Answer {
    status: u16,
    reason: &'static str,
    body: String,
    /// HEAD 면 본문을 보내지 않는다 — status 와 header 는 GET 과 같다.
    with_body: bool,
    allow: bool,
}

impl Answer {
    fn page(asked: Asked, body: String) -> Answer {
        Answer {
            status: 200,
            reason: "OK",
            body,
            with_body: asked == Asked::Get,
            allow: false,
        }
    }

    /// 거절 한 통 — **프로젝트의 사실을 한 글자도 담지 않는다.**
    ///
    /// 어느 부분이 틀렸는지도 말하지 않는다. 틀린 곳을 알려 주면 그것이 곧 맞히는 방법이다.
    fn refusal(status: u16, reason: &'static str) -> Answer {
        Answer {
            status,
            reason,
            body: String::from(
                "<!doctype html>\n<html lang=\"ko\">\n<head>\n<meta charset=\"utf-8\">\n\
                 <title>GIL Monitor</title>\n</head>\n<body>\n\
                 <p>이 주소에는 아무것도 없다.</p>\n</body>\n</html>\n",
            ),
            with_body: true,
            allow: status == 405,
        }
    }

    fn write_to(&self, stream: &mut TcpStream) -> io::Result<()> {
        let mut out = String::new();
        let _ = write!(out, "HTTP/1.1 {} {}\r\n", self.status, self.reason);
        // **정상도 거절도 같은 자물쇠를 쓴다.** 하나만 지키면 지키지 않은 쪽이 길이 된다.
        out.push_str("Content-Type: text/html; charset=utf-8\r\n");
        out.push_str("Cache-Control: no-store\r\n");
        out.push_str("X-Content-Type-Options: nosniff\r\n");
        out.push_str("Referrer-Policy: no-referrer\r\n");
        out.push_str("X-Frame-Options: DENY\r\n");
        out.push_str("Cross-Origin-Resource-Policy: same-origin\r\n");
        out.push_str(CSP);
        out.push_str("Connection: close\r\n");
        if self.allow {
            out.push_str("Allow: GET, HEAD\r\n");
        }
        // 길이는 **GET 이었다면 보냈을 본문**의 것이다 — HEAD 가 같은 header 를 받는다.
        let _ = write!(out, "Content-Length: {}\r\n\r\n", self.body.len());
        stream.write_all(out.as_bytes())?;
        if self.with_body {
            stream.write_all(self.body.as_bytes())?;
        }
        stream.flush()
    }
}

// ── 감시 ───────────────────────────────────────────────────────────────────

/// 루트 `.gil/` 안에서 **유일하게 뜻이 있는** 파일.
///
/// Graph 의 논리 상태 전부가 한 번의 교체로 여기서 확정된다(Storage Model §2). 그래서
/// 이 하나만 보면 되고, 나머지는 보아서는 안 된다.
const GRAPH_FILE: &str = "state.yaml";

/// 프로젝트를 감시한다 — **한 가지 말만 전한다.**
///
/// callback 이 하는 일은 걸러서 [`Wish::Hint`] 한 마디를 넣는 것뿐이다. 경로도, 사건의
/// 종류도, 순서도, 바뀐 파일의 목록도 전하지 않고 어디에도 남기지 않는다. **여기서
/// 프로젝트의 사실을 판정하지 않는다** — 사실은 언제나 다음 전체 조회가 정한다.
///
/// callback 은 프로젝트를 열지 않는다. 잠금을 얻으려 하지도 않는다. 감시 갈래가 잠금을
/// 기다리기 시작하면 그 순간 감시는 프로젝트를 붙드는 쪽이 된다.
fn watch_project(root: &Path, wishes: SyncSender<Wish>) -> Result<Box<dyn Any + Send>, String> {
    use notify::{RecursiveMode, Watcher};

    let gil = root.join(crate::artifact::GIL_DIR);
    let mut watcher = notify::recommended_watcher(move |event: notify::Result<notify::Event>| {
        let Ok(event) = event else {
            // 감시가 흘린 사건은 hint 로 만들지 않는다 — 무엇을 놓쳤는지 모르는 채로
            // 관측을 부르는 것이 되고, 그래도 reconciliation 기한이 수렴을 맡는다.
            return;
        };
        if !event.paths.iter().any(|path| worth_looking(path, &gil)) {
            return;
        }
        // **가득 차면 버린다.** hint 는 백 개나 한 개나 뜻이 같다.
        let _ = wishes.try_send(Wish::Hint);
    })
    .map_err(|said| said.to_string())?;
    watcher
        .watch(root, RecursiveMode::Recursive)
        .map_err(|said| said.to_string())?;
    Ok(Box::new(watcher))
}

use std::any::Any;

/// 이 경로의 변화가 **다시 볼 만한 것인가.**
///
/// ```text
/// <root>/.gil/state.yaml        예 — Graph 의 논리 상태가 여기서 확정된다
/// <root>/.gil/ 그 밖의 모든 것   아니오 — 잠금·tmp·object store·restore 임시
/// <root>/ 의 일반 파일           예 — Artifact 세계
/// 더 깊은 곳의 .gil/            예 — 중첩 GIL 경계다. **거르지 않는다.**
/// ```
///
/// # 왜 루트 `.gil/` 만 조용한가
///
/// 관측 자체가 그 안을 만진다 — 잠금을 걸고, 필요하면 중단 복구를 한다. 그것을 hint 로
/// 되받으면 **관측이 관측을 부르는 고리**가 된다.
///
/// ```text
/// 관측 → .gil 사건 → hint → 관측 → .gil 사건 → …     ← 이 고리를 끊는다
/// ```
///
/// # 왜 더 깊은 `.gil` 은 거르지 않는가
///
/// Artifact Model §3.4 에서 그것은 제외 대상이 아니라 **관측 거절 사유**다. 걸러 버리면
/// 사람이 중첩 GIL 을 만들어 둔 사실이 화면에 영영 나타나지 않는다. 걸러 내지 않으므로
/// 다음 조회가 거절하고, 화면이 그 거절을 보인다.
///
/// **이 filter 는 사실을 판정하지 않는다.** 「다시 볼 필요조차 없는 Monitor 자신의 잡음」
/// 하나만 덜어낸다.
fn worth_looking(path: &Path, gil: &Path) -> bool {
    match path.strip_prefix(gil) {
        // 루트 `.gil/` 밖 — Artifact 세계다.
        Err(_) => true,
        // 루트 `.gil/` 자신(빈 나머지)도, 그 안의 다른 무엇도 아니다.
        Ok(rest) => rest == Path::new(GRAPH_FILE),
    }
}

/// 벽시계에서 논리 눈금을 얻는 기본 시계.
pub(crate) fn wall_clock() -> Clock {
    let start = Instant::now();
    Box::new(move || Moment::at(start.elapsed().as_millis() as u64))
}

// ── 바깥으로 나가는 문 하나 ────────────────────────────────────────────────

/// 실행 중인 Monitor 창 — `gil monitor --serve` 가 손에 쥐는 것.
///
/// 안쪽 구조를 내보이지 않는다. 바깥이 알아야 하는 것은 **어디로 가면 되는가**, **눈이
/// 멀었는가**, **언제까지 도는가** 셋뿐이다.
#[derive(Debug)]
pub struct MonitorServer(Monitor);

impl MonitorServer {
    /// 사람이 browser 에 붙여 넣을 주소 하나.
    ///
    /// **token 은 이 안에만 있다.** 따로 다시 내보이지 않는다 — 두 자리에 적히면 한 자리는
    /// 사람이 지우기를 잊는 자리가 된다.
    pub fn url(&self) -> String {
        self.0.url()
    }

    /// 파일 감시가 서지 못했으면 그 까닭.
    ///
    /// `Some` 이면 자동 갱신이 **느린 주기로만** 일어난다. 그 사실은 화면에도 적힌다.
    pub fn blind(&self) -> Option<&str> {
        self.0.blind()
    }

    /// 사람이 끝낼 때까지 앞에서 돌고, **끝나면 스스로 정리한다.**
    ///
    /// # 왜 신호를 받아 두는가
    ///
    /// 받지 않아도 안전하기는 하다 — 잠금은 열린 handle 에 걸린 advisory lock 이라
    /// 프로세스가 죽으면 커널이 풀고, Monitor 는 어디에도 쓰지 않으므로 되돌릴 쓰기가 없다.
    ///
    /// 그러나 받지 않으면 **사람이 실제로 밟는 길과 시험이 밟는 길이 갈린다.** 시험은
    /// [`Monitor::close`] 로 listener 를 닫고 감시를 떨어뜨리고 두 갈래를 join 하는데,
    /// 실행 중인 명령은 그 길을 한 번도 지나지 않게 된다. 두 자리에 적힌 것은 한쪽이
    /// 낡는다. 그래서 Ctrl-C 도 같은 `close()` 로 들어온다.
    ///
    /// # 빌린 것은 돌려준다
    ///
    /// 신호는 **process 전체의 것**이다. GIL 을 라이브러리로 부르는 host 가 제 신호 정책을
    /// 갖고 있을 수 있고, 그것을 말없이 덮어쓴 채 돌려주지 않으면 이 함수 하나가 그
    /// program 의 Ctrl-C 를 영영 바꿔 놓는다. 그래서 빌리고, 쓰고, 돌려준다.
    ///
    /// ```text
    /// ① 차례를 잡는다        이미 누가 기다리고 있으면 거절한다 — 말없이 뺏지 않는다
    /// ② 지난 신호를 지운다    앞 실행의 Ctrl-C 가 이번 실행을 즉시 끝내지 않게
    /// ③ 옛 action 을 챙기고 새 것을 건다
    /// ④ 기다린다
    /// ⑤ close()
    /// ⑥ SIGTERM · SIGINT 를 챙겨 둔 것으로 되돌린다
    /// ⑦ 지난 신호를 지우고 차례를 놓는다
    /// ```
    ///
    /// ③ 이후의 모든 되돌리기는 [`Restore`] 와 [`Turn`] 의 `Drop` 이 한다. 그래서 중간에
    /// 무엇이 실패하든, panic 으로 풀려 나가든 순서가 빠지지 않는다.
    pub fn wait(&mut self) -> Result<(), String> {
        // ① 신호를 소유할 수 있는 것은 한 번에 하나뿐이다.
        let _turn = Turn::take().ok_or_else(|| {
            "이 프로세스에서 이미 다른 Monitor 가 신호를 기다리고 있다".to_string()
        })?;
        // ② 앞 실행이 남긴 값이 이번 기다림을 즉시 끝내지 않게.
        INTERRUPTED.store(false, Ordering::SeqCst);
        // ③ 두 번째 설치가 실패하면 `_first` 가 떨어지며 첫 번째도 즉시 되돌아간다.
        let (_first, _second) = arm(libc::SIGINT, libc::SIGTERM)?;

        // ④ 신호가 올 때까지. `park_timeout` 인 까닭은 신호가 park 을 깨워 주는 것에
        //    기대지 않기 위해서다 — 그것은 플랫폼마다 다르다.
        while !INTERRUPTED.load(Ordering::SeqCst) {
            std::thread::park_timeout(Duration::from_millis(200));
        }
        // ⑤ 사람이 밟는 길과 시험이 밟는 길이 여기서 만난다.
        self.0.close();
        Ok(())
        // ⑥⑦ 은 `Drop` 이 한다 — 선언의 역순이라 SIGTERM · SIGINT 차례로 돌아간다.
    }
}

/// 사람이 그만두라고 말했다.
static INTERRUPTED: AtomicBool = AtomicBool::new(false);

/// 지금 신호를 소유한 `wait` 가 있는가.
static WAITING: AtomicBool = AtomicBool::new(false);

/// **신호를 소유한 차례.** 떨어지면 놓는다.
struct Turn;

impl Turn {
    /// 아무도 잡고 있지 않을 때만 잡는다.
    fn take() -> Option<Turn> {
        WAITING
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .ok()
            .map(|_| Turn)
    }
}

impl Drop for Turn {
    fn drop(&mut self) {
        // 다음 기다림이 앞선 값을 물려받지 않게 여기서도 지운다.
        INTERRUPTED.store(false, Ordering::SeqCst);
        WAITING.store(false, Ordering::SeqCst);
    }
}

/// **빌린 action 하나.** 떨어지면 돌려준다.
struct Restore {
    signal: libc::c_int,
    old: libc::sigaction,
}

impl Drop for Restore {
    fn drop(&mut self) {
        // SAFETY: `old` 는 바로 이 신호에서 `sigaction` 이 채워 준 값이다.
        unsafe {
            libc::sigaction(self.signal, &self.old, std::ptr::null_mut());
        }
    }
}

/// 두 신호를 같은 자리로 모은다 — **하나라도 실패하면 아무것도 바꾸지 않은 셈이 된다.**
fn arm(first: libc::c_int, second: libc::c_int) -> Result<(Restore, Restore), String> {
    let first = install(first)?;
    // 여기서 실패하면 `first` 가 이 함수를 빠져나가며 떨어지고, 첫 신호는 곧바로 제자리로
    // 돌아간다. 되돌리는 코드를 따로 적지 않는 까닭이다.
    let second = install(second)?;
    Ok((first, second))
}

/// 신호 하나에 처리기를 걸고 **옛 action 을 손에 쥔다.**
///
/// `signal()` 이 아니라 `sigaction()` 을 쓰는 까닭은 두 가지다. 옛 action 을 온전히
/// 돌려받을 수 있고, 성공했는지 물어볼 수 있다.
fn install(signal: libc::c_int) -> Result<Restore, String> {
    // SAFETY: 두 구조체 모두 이 호출이 채운다. 실패하면 `old` 를 쓰지 않는다.
    unsafe {
        let mut new: libc::sigaction = std::mem::zeroed();
        new.sa_sigaction = note_interrupt as extern "C" fn(libc::c_int) as libc::sighandler_t;
        libc::sigemptyset(&mut new.sa_mask);
        new.sa_flags = libc::SA_RESTART;
        let mut old: libc::sigaction = std::mem::zeroed();
        match libc::sigaction(signal, &new, &mut old) {
            0 => Ok(Restore { signal, old }),
            _ => Err(format!(
                "신호 {signal} 을 받아 둘 수 없었다: {}",
                std::io::Error::last_os_error()
            )),
        }
    }
}

/// **신호 안에서 하는 일의 전부.**
///
/// 자리를 잡지 않고, 잠그지 않고, 보내지 않고, 글자를 만들지 않는다 — 신호 처리기 안에서
/// 해도 되는 일의 목록은 짧고, 그 목록에 있는 것만 한다.
///
/// # 플랫폼 전제
///
/// 이것이 async-signal-safe 인 것은 **`AtomicBool` 의 store 가 lock-free 로 내려가는
/// target 에서**다. 잠금으로 흉내 내는 target 이라면 처리기 안에서 잠금을 잡는 셈이 된다.
/// 지금 짓는 자리(x86-64 · aarch64)에서는 한 낱말 원자 store 라 그렇지 않다. 그렇지 않은
/// target 을 지원하게 되는 날에는 self-pipe 로 바꾼다.
extern "C" fn note_interrupt(_signal: libc::c_int) {
    INTERRUPTED.store(true, Ordering::SeqCst);
}

/// **창을 연다** — 프로젝트 하나를 감시하면서.
///
/// 첫 Snapshot 을 만들고, 감시를 세우고, loopback 에 자리를 얻는다. 감시가 서지 못해도
/// 창은 연다([`MonitorServer::blind`]).
pub fn serve_monitor(
    rules: crate::rules::RuleSet,
    state_path: &Path,
) -> Result<MonitorServer, String> {
    // 프로젝트 루트 — `<root>/.gil/state.yaml` 에서 두 칸 위.
    let root = state_path
        .parent()
        .and_then(Path::parent)
        .ok_or_else(|| "프로젝트 루트를 찾지 못했다".to_string())?
        .to_path_buf();
    let observer = Box::new(ProjectObserver::new(rules, state_path));
    let window = serve(observer, Pace::default(), wall_clock(), Some(&root))
        .map_err(|said| said.to_string())?;
    Ok(MonitorServer(window))
}

/// 실제 프로젝트를 여는 관측기 — **잠금은 이 함수 안에서만 산다.**
pub(crate) struct ProjectObserver {
    rules: crate::rules::RuleSet,
    state_path: std::path::PathBuf,
}

impl ProjectObserver {
    pub(crate) fn new(
        rules: crate::rules::RuleSet,
        state_path: impl Into<std::path::PathBuf>,
    ) -> ProjectObserver {
        ProjectObserver {
            rules,
            state_path: state_path.into(),
        }
    }
}

impl Observe for ProjectObserver {
    fn observe(&mut self) -> Result<super::MonitorSnapshot, String> {
        // **블록이 경계다.** 값이 밖으로 나가기 전에 session 이 떨어지고 잠금이 풀린다.
        let seen = {
            let session = crate::ProjectSession::open(self.rules.clone(), &self.state_path)
                .map_err(|said| said.to_string())?;
            session.monitor().map_err(|said| said.to_string())
        }?;
        Ok(seen)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;
    use std::sync::atomic::AtomicU64;

    // ── 시험이 쓰는 것들 ──────────────────────────────────────────────────

    /// 몇 번 관측했는지 **밖에서 셀 수 있는** 관측기.
    struct Counted {
        answers: Arc<Mutex<Vec<Result<super::super::MonitorSnapshot, String>>>>,
        calls: Arc<std::sync::atomic::AtomicUsize>,
        /// 관측하는 동안 잠금을 실제로 잡는가 — 잡아 두는 시간을 흉내 낸다.
        hold: Option<Arc<AtomicBool>>,
    }

    impl Observe for Counted {
        fn observe(&mut self) -> Result<super::super::MonitorSnapshot, String> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            if let Some(held) = &self.hold {
                held.store(true, Ordering::SeqCst);
            }
            let mut answers = self.answers.lock().expect("시험이 정한 답");
            let answer = match answers.len() {
                0 => panic!("시험이 정하지 않은 관측이 일어났다"),
                1 => answers[0].clone(),
                _ => answers.remove(0),
            };
            if let Some(held) = &self.hold {
                held.store(false, Ordering::SeqCst);
            }
            answer
        }
    }

    /// 관측기 하나와, 그것을 밖에서 들여다보는 손잡이.
    struct Watched {
        calls: Arc<std::sync::atomic::AtomicUsize>,
        answers: Arc<Mutex<Vec<Result<super::super::MonitorSnapshot, String>>>>,
        holding: Arc<AtomicBool>,
    }

    fn watched(answers: Vec<Result<super::super::MonitorSnapshot, String>>) -> (Box<Counted>, Watched) {
        let calls = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let answers = Arc::new(Mutex::new(answers));
        let holding = Arc::new(AtomicBool::new(false));
        let observer = Box::new(Counted {
            answers: Arc::clone(&answers),
            calls: Arc::clone(&calls),
            hold: Some(Arc::clone(&holding)),
        });
        (
            observer,
            Watched {
                calls,
                answers,
                holding,
            },
        )
    }

    /// 시험이 손으로 돌리는 시계.
    fn hand_clock() -> (Clock, Arc<AtomicU64>) {
        let hand = Arc::new(AtomicU64::new(0));
        let read = Arc::clone(&hand);
        (
            Box::new(move || Moment::at(read.load(Ordering::SeqCst))),
            hand,
        )
    }

    fn pace() -> Pace {
        Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_millis(1000),
            retry: Duration::from_millis(300),
        }
    }

    /// 진짜 Snapshot 하나 — 시험마다 제 자리에서.
    fn a_snapshot(label: &str) -> super::super::MonitorSnapshot {
        let root = std::env::temp_dir().join(format!("gil-serve-{label}"));
        if !root.join(crate::STATE_PATH).exists() {
            let _ = std::fs::remove_dir_all(&root);
            std::fs::create_dir_all(&root).expect("시험이 쓸 자리를 만든다");
            std::fs::write(root.join("a.txt"), "가").expect("세계를 하나 둔다");
            let session = crate::ProjectSession::start(
                crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
                root.join(crate::STATE_PATH),
            )
            .expect("시작한다");
            session.commit().expect("눕힌다");
        }
        let session = crate::ProjectSession::open(
            crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
            root.join(crate::STATE_PATH),
        )
        .expect("되살린다");
        session.monitor().expect("Snapshot 을 만든다")
    }

    /// 창 하나를 열고, 그 관측기를 들여다보는 손잡이와 시계를 함께 준다.
    fn open(label: &str) -> (Monitor, Watched, Arc<AtomicU64>) {
        let (observer, watch) = watched(vec![Ok(a_snapshot(label))]);
        let (clock, hand) = hand_clock();
        let window = serve(observer, pace(), clock, None).expect("창을 연다");
        (window, watch, hand)
    }

    /// **날 것 그대로** 한 통 보내고 받는다 — 관대한 client 뒤에 숨지 않으려고.
    fn ask(window: &Monitor, request: &str) -> String {
        let mut stream = TcpStream::connect(window.address()).expect("붙는다");
        stream
            .set_read_timeout(Some(Duration::from_secs(5)))
            .expect("기다릴 시간을 준다");
        stream.write_all(request.as_bytes()).expect("보낸다");
        let mut got = Vec::new();
        let _ = stream.read_to_end(&mut got);
        String::from_utf8_lossy(&got).into_owned()
    }

    /// 올바른 요청 한 통.
    fn proper(window: &Monitor, method: &str) -> String {
        ask(
            window,
            &format!(
                "{method} {} HTTP/1.1\r\nHost: {}\r\n\r\n",
                window.path(),
                window.address()
            ),
        )
    }

    fn status(answer: &str) -> String {
        answer.lines().next().unwrap_or_default().to_string()
    }

    fn body(answer: &str) -> String {
        match answer.split_once("\r\n\r\n") {
            Some((_, body)) => body.to_string(),
            None => String::new(),
        }
    }

    // ── ① 주소 ───────────────────────────────────────────────────────────

    #[test]
    fn the_window_opens_on_loopback_only() {
        let (window, _watch, _hand) = open("loopback-only");
        assert_eq!(
            window.address().ip(),
            std::net::IpAddr::V4(Ipv4Addr::LOCALHOST),
            "loopback 이 아닌 곳에 열렸다"
        );
        assert!(window.address().is_ipv4(), "IPv4 가 아니다");
    }

    #[test]
    fn the_port_is_the_one_the_os_chose() {
        let (window, _watch, _hand) = open("os-port");
        assert_ne!(window.address().port(), 0, "port 를 배정받지 못했다");
        // 두 창이 같은 자리를 쓰지 않는다 — 고정 port 였다면 둘째가 열리지 못한다.
        let (other, _w, _h) = open("os-port-second");
        assert_ne!(
            window.address().port(),
            other.address().port(),
            "port 가 고정되어 있다"
        );
    }

    #[test]
    fn every_start_makes_a_new_capability_path() {
        let (first, _w1, _h1) = open("new-capability-a");
        let (second, _w2, _h2) = open("new-capability-b");
        assert_ne!(first.path(), second.path(), "capability 가 되풀이됐다");
        // 앞선 창의 주소로는 뒤의 창에 들어갈 수 없다.
        let answer = ask(
            &second,
            &format!(
                "GET {} HTTP/1.1\r\nHost: {}\r\n\r\n",
                first.path(),
                second.address()
            ),
        );
        assert!(status(&answer).contains("404"), "옛 주소가 통했다: {answer}");
    }

    #[test]
    fn the_token_comes_from_the_os_random_source() {
        // 출처가 OS 의 통로다 — 시각도 PID 도 프로세스 안의 셈도 아니다.
        assert_eq!(ENTROPY, "/dev/urandom");
        assert!(
            std::path::Path::new(ENTROPY).exists(),
            "OS 난수 통로가 없다"
        );
        assert_eq!(TOKEN_BYTES * 8, 256, "128bit 아래로 내려갔다");

        let mut seen = std::collections::HashSet::new();
        for _ in 0..64 {
            let one = Capability::new().expect("OS 가 준다");
            assert_eq!(one.0.len(), TOKEN_BYTES * 2, "길이가 다르다");
            assert!(
                one.0.chars().all(|c| c.is_ascii_hexdigit() && !c.is_uppercase()),
                "URL 에 그대로 쓸 수 없는 글자다: {}",
                one.0
            );
            assert!(seen.insert(one.0), "같은 token 이 두 번 나왔다");
        }
    }

    #[test]
    fn without_os_entropy_the_window_does_not_open() {
        // 약한 값으로 물러서는 길이 없다 — 못 얻으면 열지 않는다.
        let refused = Capability::from_source("/nonexistent/entropy/source");
        assert!(
            matches!(refused, Err(ServeError::NoEntropy { .. })),
            "난수 없이도 자물쇠를 만들었다"
        );
    }

    // ── ② 들어올 수 있는 것 ───────────────────────────────────────────────

    #[test]
    fn a_proper_get_receives_the_screen() {
        let (window, _watch, _hand) = open("proper-get");
        let answer = proper(&window, "GET");
        assert!(status(&answer).contains("200 OK"), "{answer}");
        assert!(body(&answer).contains("<!doctype html>"), "화면이 아니다");
        assert!(body(&answer).contains("활성 경로"), "사실이 없다");
    }

    #[test]
    fn head_gets_the_same_headers_and_no_body() {
        let (window, _watch, _hand) = open("head-empty");
        let with = proper(&window, "GET");
        let without = proper(&window, "HEAD");
        assert_eq!(status(&with), status(&without), "status 가 다르다");
        let (head_of_get, _) = with.split_once("\r\n\r\n").expect("머리와 몸");
        let (head_of_head, _) = without.split_once("\r\n\r\n").expect("머리와 몸");
        assert_eq!(head_of_get, head_of_head, "header 가 다르다");
        assert!(body(&without).is_empty(), "HEAD 가 본문을 보냈다: {without}");
        assert!(
            head_of_head.contains(&format!("Content-Length: {}", body(&with).len())),
            "HEAD 의 길이가 GET 과 다르다"
        );
    }

    // ── ③ 들어올 수 없는 것 ───────────────────────────────────────────────

    #[test]
    fn a_wrong_token_and_a_missing_path_look_the_same() {
        let (window, _watch, _hand) = open("indistinguishable");
        let host = window.address().to_string();
        let wrong_token = ask(
            &window,
            &format!("GET /{} HTTP/1.1\r\nHost: {host}\r\n\r\n", "0".repeat(64)),
        );
        let no_path = ask(&window, &format!("GET /nothing HTTP/1.1\r\nHost: {host}\r\n\r\n"));
        let guess_project = ask(
            &window,
            &format!("GET /project/a.txt HTTP/1.1\r\nHost: {host}\r\n\r\n"),
        );
        let guess_gil = ask(
            &window,
            &format!("GET /.gil/state.yaml HTTP/1.1\r\nHost: {host}\r\n\r\n"),
        );
        for answer in [&wrong_token, &no_path, &guess_project, &guess_gil] {
            assert_eq!(answer, &wrong_token, "응답이 서로 갈린다: {answer}");
            assert!(status(answer).contains("404"), "{answer}");
        }
    }

    #[test]
    fn a_partial_token_is_not_enough() {
        let (window, _watch, _hand) = open("partial-token");
        let host = window.address().to_string();
        let full = window.path().to_string();
        for target in [
            &full[..full.len() - 1],          // 앞부분만
            &format!("{full}a"),              // 뒤에 붙였다
            &format!("{full}/"),              // 빗금 하나
            &format!("/x{}", &full[1..]),     // 한 글자 틀렸다
        ] {
            let answer = ask(
                &window,
                &format!("GET {target} HTTP/1.1\r\nHost: {host}\r\n\r\n"),
            );
            assert!(status(&answer).contains("404"), "{target} 이 통했다: {answer}");
        }
    }

    #[test]
    fn a_wrong_or_missing_or_doubled_host_is_refused() {
        let (window, _watch, _hand) = open("host-check");
        let path = window.path().to_string();
        let real = window.address().to_string();
        let port = window.address().port();
        for headers in [
            String::new(),                                      // 없다
            format!("Host: evil.example\r\n"),                  // 남의 이름
            format!("Host: localhost:{port}\r\n"),              // 이름으로 온 loopback
            format!("Host: 127.0.0.1\r\n"),                     // port 가 없다
            format!("Host: {real}\r\nHost: {real}\r\n"),        // 둘
            format!("Host: {real}\r\nHost: evil.example\r\n"),  // 진짜 뒤에 가짜
            format!("Host: evil.example\r\nHost: {real}\r\n"),  // 가짜 뒤에 진짜
        ] {
            let answer = ask(&window, &format!("GET {path} HTTP/1.1\r\n{headers}\r\n"));
            assert!(
                !status(&answer).contains("200"),
                "Host 검사를 통과했다: {headers:?} → {answer}"
            );
        }
    }

    #[test]
    fn only_get_and_head_are_answered() {
        let (window, _watch, _hand) = open("method-check");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for method in ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "CONNECT", "TRACE"] {
            let answer = ask(
                &window,
                &format!("{method} {path} HTTP/1.1\r\nHost: {host}\r\n\r\n"),
            );
            assert!(
                status(&answer).contains("405"),
                "{method} 가 통했다: {answer}"
            );
            assert!(!body(&answer).contains("활성 경로"), "사실이 샜다");
        }
    }

    #[test]
    fn a_query_or_an_absolute_target_is_refused() {
        let (window, _watch, _hand) = open("target-shape");
        let path = window.path().to_string();
        let host = window.address().to_string();
        let port = window.address().port();
        for target in [
            format!("{path}?"),
            format!("{path}?x=1"),
            format!("{path}#frag"),
            format!("http://127.0.0.1:{port}{path}"),
            format!("//127.0.0.1{path}"),
            format!("127.0.0.1:{port}"),
            "*".to_string(),
            // percent-decoding 별칭 — 마지막 글자를 hex 로 적었다.
            format!("{}%{:02x}", &path[..path.len() - 1], path.as_bytes()[path.len() - 1]),
            format!("/.{path}"),
            format!("/..{path}"),
        ] {
            let answer = ask(
                &window,
                &format!("GET {target} HTTP/1.1\r\nHost: {host}\r\n\r\n"),
            );
            assert!(
                !status(&answer).contains("200"),
                "{target} 이 통했다: {answer}"
            );
        }
    }

    #[test]
    fn oversized_requests_are_refused() {
        let (window, _watch, _hand) = open("too-big");
        let path = window.path().to_string();
        let host = window.address().to_string();

        let long_line = ask(
            &window,
            &format!("GET /{} HTTP/1.1\r\nHost: {host}\r\n\r\n", "a".repeat(REQUEST_LINE_MAX + 10)),
        );
        assert!(status(&long_line).contains("400"), "긴 첫 줄이 통했다");

        let long_header = ask(
            &window,
            &format!(
                "GET {path} HTTP/1.1\r\nHost: {host}\r\nX-Big: {}\r\n\r\n",
                "a".repeat(REQUEST_LINE_MAX + 10)
            ),
        );
        assert!(status(&long_header).contains("400"), "긴 header 가 통했다");

        let many: String = (0..HEADERS_MAX + 5)
            .map(|i| format!("X-{i}: a\r\n"))
            .collect();
        let too_many = ask(
            &window,
            &format!("GET {path} HTTP/1.1\r\nHost: {host}\r\n{many}\r\n"),
        );
        assert!(status(&too_many).contains("400"), "header 가 너무 많은데 통했다");

        let fat: String = (0..HEADERS_MAX - 4)
            .map(|i| format!("X-{i}: {}\r\n", "a".repeat(400)))
            .collect();
        let too_fat = ask(
            &window,
            &format!("GET {path} HTTP/1.1\r\nHost: {host}\r\n{fat}\r\n"),
        );
        assert!(status(&too_fat).contains("400"), "header 가 너무 큰데 통했다");
    }

    #[test]
    fn a_body_or_an_upgrade_is_refused() {
        let (window, _watch, _hand) = open("no-body");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for extra in [
            "Transfer-Encoding: chunked\r\n",
            "Content-Length: 12\r\n",
            "Upgrade: websocket\r\nConnection: Upgrade\r\n",
            "Expect: 100-continue\r\n",
        ] {
            let answer = ask(
                &window,
                &format!("GET {path} HTTP/1.1\r\nHost: {host}\r\n{extra}\r\n"),
            );
            assert!(
                status(&answer).contains("400"),
                "{extra:?} 가 통했다: {answer}"
            );
        }
    }

    #[test]
    fn a_partial_request_ends_at_the_timeout() {
        let (window, _watch, _hand) = open("timeout");
        let mut stream = TcpStream::connect(window.address()).expect("붙는다");
        // 첫 줄만 보내고 침묵한다 — 창이 이 연결에 매달려 있으면 안 된다.
        stream
            .write_all(format!("GET {} HTTP/1.1\r\n", window.path()).as_bytes())
            .expect("반만 보낸다");
        stream
            .set_read_timeout(Some(READ_TIMEOUT * 4))
            .expect("넉넉히 기다린다");
        let mut got = Vec::new();
        // **끝을 본다.** `Ok` 는 창이 스스로 연결을 끝냈다는 뜻이고, `Err` 는 이쪽이 먼저
        // 지쳤다는 뜻이다 — 후자면 창은 아직도 이 침묵을 기다리고 있다.
        let ended = stream.read_to_end(&mut got);
        assert!(
            ended.is_ok(),
            "부분 요청이 끝나지 않았다 — 창이 아직 기다린다: {ended:?}"
        );
        assert!(
            String::from_utf8_lossy(&got).contains("400") || got.is_empty(),
            "부분 요청에 화면이 나갔다"
        );
        // 그리고 창은 여전히 다음 요청을 받는다.
        assert!(status(&proper(&window, "GET")).contains("200"), "창이 막혔다");
    }

    // ── ④ 응답의 자물쇠 ───────────────────────────────────────────────────

    #[test]
    fn every_answer_carries_the_same_security_headers() {
        let (window, _watch, _hand) = open("security-headers");
        let host = window.address().to_string();
        let good = proper(&window, "GET");
        let missing = ask(&window, &format!("GET /nope HTTP/1.1\r\nHost: {host}\r\n\r\n"));
        let wrong_method = ask(
            &window,
            &format!("POST {} HTTP/1.1\r\nHost: {host}\r\n\r\n", window.path()),
        );
        for answer in [&good, &missing, &wrong_method] {
            for header in [
                "Content-Type: text/html; charset=utf-8",
                "Cache-Control: no-store",
                "X-Content-Type-Options: nosniff",
                "Referrer-Policy: no-referrer",
                "X-Frame-Options: DENY",
                "Cross-Origin-Resource-Policy: same-origin",
                "Connection: close",
            ] {
                assert!(answer.contains(header), "{header} 가 없다: {answer}");
            }
        }
    }

    #[test]
    fn the_screen_keeps_the_renderers_csp() {
        let (window, _watch, _hand) = open("csp-intact");
        let served = body(&proper(&window, "GET"));
        let standalone = super::super::render_monitor_html(&a_snapshot("csp-intact"));
        let line = |page: &str| {
            page.lines()
                .find(|line| line.contains("Content-Security-Policy"))
                .map(str::to_string)
                .unwrap_or_default()
        };
        assert!(!line(&served).is_empty(), "CSP 가 사라졌다");
        assert_eq!(line(&served), line(&standalone), "CSP 가 약해졌다");
    }

    #[test]
    fn a_refusal_says_nothing_about_the_project() {
        let (window, _watch, _hand) = open("refusal-says-nothing");
        let host = window.address().to_string();
        let token = window.path().trim_start_matches('/').to_string();
        let refused = ask(&window, &format!("GET /nope HTTP/1.1\r\nHost: {host}\r\n\r\n"));
        for secret in [
            token.as_str(),
            "gil-serve-",
            ".gil",
            "state.yaml",
            "Cycle",
            "Step",
            &host,
        ] {
            assert!(
                !refused.contains(secret),
                "거절이 {secret:?} 를 흘렸다: {refused}"
            );
        }
    }

    // ── ⑤ 상태기계와의 연결 ───────────────────────────────────────────────

    #[test]
    fn reading_the_screen_before_the_deadline_does_not_observe() {
        let (window, watch, _hand) = open("no-observe-before-deadline");
        assert_eq!(watch.calls.load(Ordering::SeqCst), 1, "첫 관측이 없다");
        for _ in 0..5 {
            assert!(status(&proper(&window, "GET")).contains("200"));
        }
        assert_eq!(
            watch.calls.load(Ordering::SeqCst),
            1,
            "화면을 읽었다는 이유로 프로젝트를 열었다"
        );
    }

    #[test]
    fn after_the_retry_deadline_a_read_can_recover() {
        let label = "recover-after-retry";
        let (observer, watch) = watched(vec![
            Err("잠깐 못 봤다".to_string()),
            Ok(a_snapshot(label)),
        ]);
        let (clock, hand) = hand_clock();
        let window = serve(observer, pace(), clock, None).expect("창을 연다");

        // 첫 관측이 실패했으니 지금은 Unavailable 이다.
        let broken = body(&proper(&window, "GET"));
        assert!(broken.contains("아직 보여 줄 것이 없다"), "{broken}");
        assert_eq!(watch.calls.load(Ordering::SeqCst), 1);

        // 기한 전에는 아무리 읽어도 관측하지 않는다.
        hand.store(200, Ordering::SeqCst);
        let _ = proper(&window, "GET");
        assert_eq!(watch.calls.load(Ordering::SeqCst), 1, "기한 전에 열었다");

        // retry 기한이 지나면 화면을 읽는 일이 상태기계를 깨운다.
        hand.store(400, Ordering::SeqCst);
        let healed = body(&proper(&window, "GET"));
        assert_eq!(watch.calls.load(Ordering::SeqCst), 2, "기한 뒤에도 안 열었다");
        assert!(healed.contains("활성 경로"), "회복하지 못했다: {healed}");
        assert!(
            !healed.contains("아직 보여 줄 것이 없다"),
            "회복했는데 경고가 남았다"
        );
    }

    #[test]
    fn a_failed_observation_becomes_a_screen_not_a_server_error() {
        let label = "failure-is-a-screen";
        let (observer, _watch) = watched(vec![
            Ok(a_snapshot(label)),
            Err("<script>alert(1)</script> & 잠금을 얻지 못했다".to_string()),
        ]);
        let (clock, hand) = hand_clock();
        let window = serve(observer, pace(), clock, None).expect("창을 연다");

        hand.store(2000, Ordering::SeqCst); // reconcile 기한을 넘긴다
        let answer = proper(&window, "GET");
        // HTTP 는 여전히 성공이다 — 실패는 화면 안에서 말한다.
        assert!(status(&answer).contains("200 OK"), "{answer}");
        let page = body(&answer);
        assert!(page.contains("이 내용은 최신이 아니다"), "{page}");
        // 그리고 마지막으로 검증된 사실이 그대로 남아 있다.
        assert!(page.contains("활성 경로"), "사실이 사라졌다");
        // 악의적인 글자는 글자로만 실렸다.
        assert!(!page.contains("<script>"), "오류 문자열이 태그가 됐다: {page}");
        assert!(page.contains("&lt;script&gt;"), "탈출되지 않았다");
    }

    #[test]
    fn the_lock_is_held_only_while_observing() {
        let label = "lock-only-while-observing";
        let (observer, watch) = watched(vec![Ok(a_snapshot(label))]);
        let (clock, _hand) = hand_clock();
        let window = serve(observer, pace(), clock, None).expect("창을 연다");
        // 응답을 주고받는 동안 관측기는 잠금을 놓고 있다.
        assert!(!watch.holding.load(Ordering::SeqCst), "열자마자 붙들고 있다");
        let _ = proper(&window, "GET");
        assert!(!watch.holding.load(Ordering::SeqCst), "응답 중에 붙들고 있다");
        assert_eq!(watch.calls.load(Ordering::SeqCst), 1);
        let _ = &watch.answers; // 손잡이를 살려 둔다
    }

    #[test]
    fn the_real_observer_releases_the_project_between_looks() {
        let root = std::env::temp_dir().join("gil-serve-real-observer");
        let _ = a_snapshot("real-observer");
        let mut observer = ProjectObserver::new(
            crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
            root.join(crate::STATE_PATH),
        );
        let seen = observer.observe().expect("관측한다");
        assert!(!seen.current_cycle.steps.is_empty() || seen.current_cycle.steps.is_empty());
        // 관측이 끝난 뒤에는 다른 자리가 곧바로 잠금을 얻는다.
        let other = crate::ProjectSession::open(
            crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
            root.join(crate::STATE_PATH),
        );
        assert!(other.is_ok(), "관측이 잠금을 붙들고 있다");
    }

    // ── ⑤-2 좁은 문법 ────────────────────────────────────────────────────

    /// 첫 줄 하나만 바꿔 보내고, 화면이 나가지 않았는지 본다.
    fn line_refused(window: &Monitor, line: &str) -> String {
        ask(
            window,
            &format!("{line}\r\nHost: {}\r\n\r\n", window.address()),
        )
    }

    #[test]
    fn only_http_1_1_is_spoken() {
        let (window, _watch, _hand) = open("only-http-11");
        let path = window.path().to_string();
        for line in [
            format!("GET {path} HTTP/1.0"),
            format!("GET {path} HTTP/2"),
            format!("GET {path} HTTP/2.0"),
            format!("GET {path} HTTP/1.1 "),   // 뒤에 칸 하나
            format!("GET  {path} HTTP/1.1"),   // 칸이 둘
            format!("GET\t{path} HTTP/1.1"),   // 탭으로 갈랐다
            format!("GET {path}\tHTTP/1.1"),
            format!(" GET {path} HTTP/1.1"),   // 앞에 칸
            format!("GET {path}"),             // 규약이 없다
            format!("GET {path} HTTP/1.1 extra"),
        ] {
            let answer = line_refused(&window, &line);
            assert!(
                status(&answer).contains("400"),
                "{line:?} 가 통했다: {answer}"
            );
        }
        // 그리고 정확한 한 줄은 여전히 통과한다.
        assert!(status(&proper(&window, "GET")).contains("200"));
    }

    #[test]
    fn a_line_that_ends_without_crlf_is_refused() {
        let (window, _watch, _hand) = open("crlf-required");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for request in [
            // ① 전부 LF 뿐이다
            format!("GET {path} HTTP/1.1\nHost: {host}\n\n"),
            // ② 첫 줄만 CRLF, header 는 LF
            format!("GET {path} HTTP/1.1\r\nHost: {host}\n\r\n"),
            // ③ header 는 CRLF, 끝맺음만 LF
            format!("GET {path} HTTP/1.1\r\nHost: {host}\r\n\n"),
            // ④ 홀로 선 CR
            format!("GET {path} HTTP/1.1\rHost: {host}\r\n\r\n"),
            // ⑤ 줄 한가운데의 CR
            format!("GET {path}\rx HTTP/1.1\r\nHost: {host}\r\n\r\n"),
            format!("GET {path} HTTP/1.1\r\nHo\rst: {host}\r\n\r\n"),
        ] {
            let answer = ask(&window, &request);
            assert!(
                !status(&answer).contains("200"),
                "{request:?} 가 통했다: {answer}"
            );
        }
    }

    #[test]
    fn a_header_name_must_be_a_token() {
        let (window, _watch, _hand) = open("header-name-token");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for header in [
            " X-A: b",       // 이름 앞 공백 (obs-fold 이기도 하다)
            "\tX-A: b",      // 이름 앞 탭
            "X A: b",        // 이름 안 공백
            "X\tA: b",       // 이름 안 탭
            "X-A : b",       // 이름 뒤 공백
            ": b",           // 빈 이름
            "X-\u{ac00}: b", // ASCII 밖
            "X-A b",         // 콜론이 없다
        ] {
            let answer = ask(
                &window,
                &format!("GET {path} HTTP/1.1\r\nHost: {host}\r\n{header}\r\n\r\n"),
            );
            assert!(
                status(&answer).contains("400"),
                "{header:?} 가 통했다: {answer}"
            );
        }
    }

    #[test]
    fn an_obs_fold_continuation_is_refused() {
        let (window, _watch, _hand) = open("obs-fold");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for fold in [" 뒤에 붙였다", "\t뒤에 붙였다", " Host: evil.example"] {
            let answer = ask(
                &window,
                &format!("GET {path} HTTP/1.1\r\nHost: {host}\r\nX-A: b\r\n{fold}\r\n\r\n"),
            );
            assert!(status(&answer).contains("400"), "{fold:?} 가 통했다: {answer}");
        }
    }

    #[test]
    fn a_nul_or_a_control_character_is_refused() {
        let (window, _watch, _hand) = open("control-chars");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for bad in ['\u{0}', '\u{1}', '\u{b}', '\u{c}', '\u{1b}', '\u{7f}'] {
            for request in [
                format!("GET {path}{bad} HTTP/1.1\r\nHost: {host}\r\n\r\n"),
                format!("GET {path} HTTP/1.1\r\nHost: {host}\r\nX-A: b{bad}c\r\n\r\n"),
                format!("GET {path} HTTP/1.1\r\nHost: {host}\r\nX{bad}A: b\r\n\r\n"),
            ] {
                let answer = ask(&window, &request);
                assert!(
                    status(&answer).contains("400"),
                    "{:?} 가 통했다: {answer}",
                    bad as u32
                );
            }
        }
    }

    #[test]
    fn a_second_content_length_is_refused_even_when_both_are_zero() {
        let (window, _watch, _hand) = open("doubled-length");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for headers in [
            "Content-Length: 0\r\nContent-Length: 0\r\n",
            "Content-Length: 0\r\ncontent-length: 0\r\n",
            "Content-Length: 0\r\nCONTENT-LENGTH: 0\r\n",
            "Content-Length: 0\r\nContent-Length: 12\r\n",
        ] {
            let answer = ask(
                &window,
                &format!("GET {path} HTTP/1.1\r\nHost: {host}\r\n{headers}\r\n"),
            );
            assert!(
                status(&answer).contains("400"),
                "{headers:?} 가 통했다: {answer}"
            );
        }
        // 하나의 `0` 은 받는다.
        let single = ask(
            &window,
            &format!("GET {path} HTTP/1.1\r\nHost: {host}\r\nContent-Length: 0\r\n\r\n"),
        );
        assert!(status(&single).contains("200"), "{single}");
    }

    #[test]
    fn a_doubled_host_counts_as_two_whatever_the_case() {
        let (window, _watch, _hand) = open("doubled-host-case");
        let path = window.path().to_string();
        let host = window.address().to_string();
        for headers in [
            format!("Host: {host}\r\nhost: {host}\r\n"),
            format!("HOST: {host}\r\nHost: {host}\r\n"),
            format!("hOsT: {host}\r\nHost: evil.example\r\n"),
        ] {
            let answer = ask(&window, &format!("GET {path} HTTP/1.1\r\n{headers}\r\n"));
            assert!(
                status(&answer).contains("400"),
                "{headers:?} 가 통했다: {answer}"
            );
        }
        // 소문자 하나만 온 것은 같은 이름으로 알아본다.
        let lower = ask(
            &window,
            &format!("GET {path} HTTP/1.1\r\nhost: {host}\r\n\r\n"),
        );
        assert!(status(&lower).contains("200"), "{lower}");
    }

    #[test]
    fn a_well_formed_unknown_header_is_simply_skipped() {
        let (window, _watch, _hand) = open("unknown-header-ok");
        let path = window.path().to_string();
        let host = window.address().to_string();
        let answer = ask(
            &window,
            &format!(
                "GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: Mozilla/5.0\r\nAccept: text/html,application/xhtml+xml\r\nAccept-Language: ko-KR,ko;q=0.9\r\nX-Odd_Name.1!~:\tvalue with spaces\t\r\n\r\n"
            ),
        );
        assert!(status(&answer).contains("200 OK"), "{answer}");
        assert!(body(&answer).contains("활성 경로"), "화면이 나오지 않았다");
    }

    // ── ⑤-3 문서 밖의 자물쇠 ──────────────────────────────────────────────

    /// CSP 한 줄을 지시어 → 값의 짝으로 가른다.
    fn directives(policy: &str) -> Vec<(String, String)> {
        policy
            .split(';')
            .map(str::trim)
            .filter(|one| !one.is_empty())
            .map(|one| match one.split_once(' ') {
                Some((name, value)) => (name.trim().to_string(), value.trim().to_string()),
                None => (one.to_string(), String::new()),
            })
            .collect()
    }

    #[test]
    fn every_answer_carries_the_same_csp_header() {
        let (window, _watch, _hand) = open("csp-on-every-answer");
        let host = window.address().to_string();
        let path = window.path().to_string();
        let expected = CSP.trim_end_matches("\r\n");
        let answers = [
            proper(&window, "GET"),                                              // 200
            proper(&window, "HEAD"),                                             // 200
            ask(&window, &format!("GET /nope HTTP/1.1\r\nHost: {host}\r\n\r\n")), // 404
            ask(&window, &format!("POST {path} HTTP/1.1\r\nHost: {host}\r\n\r\n")), // 405
            ask(&window, &format!("GET {path} HTTP/1.0\r\nHost: {host}\r\n\r\n")),  // 400
        ];
        for (code, answer) in ["200", "200", "404", "405", "400"].iter().zip(&answers) {
            assert!(status(answer).contains(code), "{code} 가 아니다: {answer}");
            assert!(
                answer.contains(expected),
                "{code} 응답에 CSP header 가 없다: {answer}"
            );
        }
    }

    #[test]
    fn the_header_csp_says_the_same_as_the_meta_csp() {
        // 두 자리에 적힌 값이라, 한쪽이 낡으면 여기서 걸린다.
        let (window, _watch, _hand) = open("csp-two-places-agree");
        let page = body(&proper(&window, "GET"));
        let meta = page
            .lines()
            .find(|line| line.contains("Content-Security-Policy"))
            .and_then(|line| line.split_once("content=\"").map(|(_, rest)| rest))
            .and_then(|rest| rest.split_once('"').map(|(value, _)| value))
            .expect("meta CSP 를 찾지 못했다")
            .to_string();
        let header = CSP
            .trim_end_matches("\r\n")
            .trim_start_matches("Content-Security-Policy:")
            .to_string();

        let in_header = directives(&header);
        for (name, value) in directives(&meta) {
            let found = in_header.iter().find(|(theirs, _)| theirs == &name);
            assert_eq!(
                found.map(|(_, value)| value.as_str()),
                Some(value.as_str()),
                "{name} 이 두 자리에서 다르다"
            );
        }
        // header 쪽이 더 적을 수는 없다.
        assert!(
            in_header.len() >= directives(&meta).len(),
            "header CSP 가 meta 보다 느슨하다"
        );
        // meta 로는 무시되는 지시어는 header 에만 있다.
        assert!(
            in_header.iter().any(|(name, _)| name == "frame-ancestors"),
            "frame-ancestors 가 header 에 없다"
        );
    }

    // ── ⑥ 스스로를 다시 받아오는 표지 ─────────────────────────────────────

    #[test]
    fn the_served_screen_refreshes_to_its_own_capability_path() {
        let (window, _watch, _hand) = open("refresh-to-self");
        let page = body(&proper(&window, "GET"));
        let marker = format!(
            "<meta http-equiv=\"refresh\" content=\"{REFRESH_SECONDS}; url={}\">",
            window.path()
        );
        assert!(page.contains(&marker), "표지가 없거나 다른 곳을 본다: {page}");
        // 표지는 하나뿐이고, 다른 URL 로 보내지 않는다.
        assert_eq!(page.matches("http-equiv=\"refresh\"").count(), 1);
        assert!(!page.contains("http://"), "바깥으로 나가는 주소가 생겼다");
        assert!(!page.contains("<script"), "JavaScript 가 들어왔다");
    }

    #[test]
    fn the_standalone_screen_has_no_refresh_marker() {
        let standalone = super::super::render_monitor_html(&a_snapshot("standalone-no-refresh"));
        assert!(
            !standalone.contains("http-equiv=\"refresh\""),
            "저장해 여는 문서가 없는 주소를 두드린다"
        );
    }

    #[test]
    fn the_refresh_marker_does_not_touch_the_facts() {
        let label = "marker-does-not-touch-facts";
        let (window, _watch, _hand) = open(label);
        let served = body(&proper(&window, "GET"));
        let standalone = super::super::render_monitor_html(&a_snapshot(label));
        // 표지 한 줄을 빼면 두 문서가 같다.
        let stripped: String = served
            .lines()
            .filter(|line| !line.contains("http-equiv=\"refresh\""))
            .collect::<Vec<_>>()
            .join("\n");
        assert_eq!(
            stripped.trim(),
            standalone.trim(),
            "표지가 사실 영역을 바꿨다"
        );
    }

    // ── ⑦ 닫기 ───────────────────────────────────────────────────────────

    #[test]
    fn closing_ends_the_worker_and_leaves_nothing_behind() {
        let label = "closing-leaves-nothing";
        let root = std::env::temp_dir().join(format!("gil-serve-{label}"));
        let (mut window, _watch, _hand) = open(label);
        let address = window.address();
        let before = std::fs::read(root.join("a.txt")).expect("세계를 읽는다");
        let state_before = std::fs::read(root.join(crate::STATE_PATH)).expect("상태를 읽는다");

        window.close();

        // 창이 닫혔다 — 더는 붙을 수 없다.
        let mut still_open = false;
        for _ in 0..20 {
            match TcpStream::connect_timeout(&address, Duration::from_millis(100)) {
                Ok(mut stream) => {
                    // 아직 socket 이 살아 있을 수 있다 — 답이 오는지로 가른다.
                    let _ = stream.write_all(b"GET / HTTP/1.1\r\n\r\n");
                    let mut got = Vec::new();
                    let _ = stream.set_read_timeout(Some(Duration::from_millis(200)));
                    let _ = stream.read_to_end(&mut got);
                    if !got.is_empty() {
                        still_open = true;
                    }
                    break;
                }
                Err(_) => break,
            }
        }
        assert!(!still_open, "닫았는데 아직 답한다");

        // 프로젝트도 작업 파일도 그대로다.
        assert_eq!(before, std::fs::read(root.join("a.txt")).expect("다시 읽는다"));
        assert_eq!(
            state_before,
            std::fs::read(root.join(crate::STATE_PATH)).expect("다시 읽는다")
        );
        // 그리고 다음 명령이 곧바로 잠금을 얻는다.
        let after = crate::ProjectSession::open(
            crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
            root.join(crate::STATE_PATH),
        );
        assert!(after.is_ok(), "닫은 뒤에도 잠금이 남았다");
    }

    #[test]
    fn nothing_about_the_window_reaches_the_disk() {
        let label = "nothing-on-disk";
        let root = std::env::temp_dir().join(format!("gil-serve-{label}"));
        let (mut window, _watch, _hand) = open(label);
        let token = window.path().trim_start_matches('/').to_string();
        let port = window.address().port().to_string();
        let _ = proper(&window, "GET");
        window.close();

        let mut checked = 0usize;
        for entry in walk(&root) {
            let Ok(bytes) = std::fs::read(&entry) else {
                continue;
            };
            let text = String::from_utf8_lossy(&bytes);
            assert!(!text.contains(&token), "token 이 {entry:?} 에 남았다");
            assert!(
                !text.contains("127.0.0.1"),
                "내부 주소가 {entry:?} 에 남았다"
            );
            assert!(
                !entry.to_string_lossy().contains(&token),
                "token 이 파일 이름에 남았다"
            );
            let _ = &port;
            checked += 1;
        }
        assert!(checked > 0, "아무 파일도 보지 못했다");
    }

    /// 한 자리 아래 모든 파일.
    fn walk(root: &std::path::Path) -> Vec<std::path::PathBuf> {
        let mut found = Vec::new();
        let Ok(entries) = std::fs::read_dir(root) else {
            return found;
        };
        for entry in entries.flatten() {
            let path = entry.path();
            match path.is_dir() {
                true => found.extend(walk(&path)),
                false => found.push(path),
            }
        }
        found
    }

    // ── ⑧ 진짜 세계를 지켜본다 ────────────────────────────────────────────
    //
    // 여기서부터는 가짜 관측기도 가짜 시계도 쓰지 않는다. 진짜 프로젝트, 진짜 파일 감시,
    // 진짜 단조 시각이다 — 재려는 것이 「연결이 실제로 도는가」이기 때문이다.

    /// 관측 횟수를 세면서 진짜 프로젝트를 여는 관측기.
    struct Counting(ProjectObserver, Arc<std::sync::atomic::AtomicUsize>);

    impl Observe for Counting {
        fn observe(&mut self) -> Result<super::super::MonitorSnapshot, String> {
            self.1.fetch_add(1, Ordering::SeqCst);
            self.0.observe()
        }
    }

    /// 사람이 쓰는 것과 같은 박자를, 시험이 기다릴 만한 눈금으로 줄인 것.
    fn brisk() -> Pace {
        Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_millis(3000),
            retry: Duration::from_millis(400),
        }
    }

    /// **감시 말고는 아무도 제때 알려 줄 수 없는 박자.**
    ///
    /// reconciliation 을 시험이 기다리는 시간 밖으로 밀어낸다. 이렇게 하지 않으면 감시가
    /// 죽어 있어도 느린 기한이 대신 통과시켜, 「감시가 도는가」를 묻는 시험이 실은
    /// 「기한이 오는가」를 묻게 된다.
    fn only_the_watcher() -> Pace {
        Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_secs(600),
            retry: Duration::from_secs(600),
        }
    }

    /// 진짜 프로젝트 하나를 세우고 그 위에 창을 연다.
    fn live(
        label: &str,
        pace: Pace,
    ) -> (
        Monitor,
        std::path::PathBuf,
        Arc<std::sync::atomic::AtomicUsize>,
    ) {
        let root = std::env::temp_dir().join(format!("gil-live-{label}"));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).expect("자리를 만든다");
        std::fs::write(root.join("a.txt"), "가").expect("세계를 하나 둔다");
        let rules = crate::rules::RuleSet::builtin().expect("함께 실린 명세");
        let state = root.join(crate::STATE_PATH);
        crate::ProjectSession::start(rules.clone(), &state)
            .expect("시작한다")
            .commit()
            .expect("눕힌다");

        let looks = Arc::new(std::sync::atomic::AtomicUsize::new(0));
        let observer = Box::new(Counting(
            ProjectObserver::new(rules, &state),
            Arc::clone(&looks),
        ));
        let window = serve(observer, pace, wall_clock(), Some(&root)).expect("창을 연다");
        (window, root, looks)
    }

    /// **창이 조용해질 때까지 기다린다.**
    ///
    /// fixture 가 프로젝트를 세우는 쓰기는 감시가 서기 직전에 일어난다. macOS 의 FSEvents 는
    /// 그 직전 사건 하나를 시작 직후에 흘려 줄 수 있고, 그러면 관측이 한 번 더 일어난다.
    /// **시작의 잡음이지 고리가 아니다** — 고리라면 debounce 마다 끝없이 늘어난다.
    ///
    /// 그래서 재기 전에 조용해지기를 기다린다. 여기서 기다리지 않으면 시험이 재려는 것이
    /// 아니라 fixture 가 남긴 자국을 재게 된다.
    fn settle(looks: &Arc<std::sync::atomic::AtomicUsize>) -> usize {
        let mut last = looks.load(Ordering::SeqCst);
        let start = Instant::now();
        while start.elapsed() < Duration::from_secs(2) {
            std::thread::sleep(Duration::from_millis(250));
            let now = looks.load(Ordering::SeqCst);
            if now == last {
                return now;
            }
            last = now;
        }
        last
    }

    /// 지금 화면 한 장.
    fn screen(window: &Monitor) -> String {
        body(&proper(window, "GET"))
    }

    /// 화면이 말하는 세계의 상태.
    fn world_says(window: &Monitor) -> String {
        let page = screen(window);
        for mark in ["clean", "dirty", "unknown"] {
            if page.contains(&format!("<dd>{mark} —")) {
                return mark.to_string();
            }
        }
        panic!("화면이 세계를 말하지 않는다: {page}")
    }

    /// 조건이 될 때까지 짧게 되물으며 기다린다 — 고정된 잠으로 재지 않으려고.
    fn until(limit: Duration, mut ready: impl FnMut() -> bool) -> bool {
        let start = Instant::now();
        while start.elapsed() < limit {
            if ready() {
                return true;
            }
            std::thread::sleep(Duration::from_millis(20));
        }
        ready()
    }

    #[test]
    fn an_artifact_change_reaches_the_screen() {
        let (window, root, _looks) = live("artifact-change", only_the_watcher());
        assert_eq!(world_says(&window), "clean", "처음이 깨끗하지 않다");

        // ③ 일반 파일 하나를 만든다 → ④ 감시 → ⑤ debounce 뒤 전체 조회 → ⑥ dirty
        std::fs::write(root.join("b.txt"), "새 파일").expect("세계를 흔든다");
        assert!(
            until(Duration::from_secs(5), || world_says(&window) == "dirty"),
            "파일을 만들었는데 화면이 따라오지 않았다"
        );

        // ⑦ 되돌린다 → ⑧ 다시 clean
        {
            let session = crate::ProjectSession::open(
                crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
                root.join(crate::STATE_PATH),
            )
            .expect("되살린다");
            session.restore().expect("되돌린다");
        }
        assert!(
            until(Duration::from_secs(5), || world_says(&window) == "clean"),
            "되돌렸는데 화면이 따라오지 않았다"
        );
    }

    #[test]
    fn a_graph_change_reaches_the_screen() {
        let (window, root, _looks) = live("graph-change", only_the_watcher());
        assert!(
            screen(&window).contains("아직 아무것도 열지 않았다"),
            "처음부터 무언가 열려 있다"
        );

        // 별도의 세션이 state.yaml 을 바꾼다 — Monitor 가 아니라.
        {
            let mut session = crate::ProjectSession::open(
                crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
                root.join(crate::STATE_PATH),
            )
            .expect("되살린다");
            session
                .open_action_step(
                    crate::NodeKind::Question,
                    crate::ActionContract::new(
                        "무엇이 문제인지 밝힌다",
                        "실패한 시험 하나를 읽는다",
                        "원인 한 줄을 적을 수 있다",
                    ),
                )
                .expect("연다");
            session.commit().expect("눕힌다");
        }
        assert!(
            until(Duration::from_secs(5), || screen(&window)
                .contains("step:C1/S1")),
            "state.yaml 이 바뀌었는데 화면이 따라오지 않았다"
        );
    }

    #[test]
    fn a_missed_hint_still_converges() {
        // 감시를 아예 세우지 않는다 — 사건이 하나도 오지 않는 세계다.
        let root = std::env::temp_dir().join("gil-live-missed-hint");
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).expect("자리를 만든다");
        std::fs::write(root.join("a.txt"), "가").expect("세계를 하나 둔다");
        let rules = crate::rules::RuleSet::builtin().expect("함께 실린 명세");
        let state = root.join(crate::STATE_PATH);
        crate::ProjectSession::start(rules.clone(), &state)
            .expect("시작한다")
            .commit()
            .expect("눕힌다");
        let pace = Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_millis(700),
            retry: Duration::from_millis(400),
        };
        let window = serve(
            Box::new(ProjectObserver::new(rules, &state)),
            pace,
            wall_clock(),
            None, // ← 감시 없음
        )
        .expect("창을 연다");
        assert_eq!(world_says(&window), "clean");

        std::fs::write(root.join("b.txt"), "아무도 알려 주지 않는다").expect("세계를 흔든다");
        // hint 는 영영 오지 않는다. 그래도 reconciliation 기한이 수렴시킨다.
        assert!(
            until(Duration::from_secs(5), || world_says(&window) == "dirty"),
            "사건이 없으면 영영 낡은 채로 남는다"
        );
    }

    #[test]
    fn a_hundred_hints_become_one_look() {
        let (window, _root, looks) = live("hints-coalesce", only_the_watcher());
        let before = settle(&looks);
        for _ in 0..100 {
            window.hint();
        }
        // debounce 가 끝나면 딱 한 번 본다.
        assert!(
            until(Duration::from_secs(3), || looks.load(Ordering::SeqCst)
                > before),
            "hint 백 개가 아무것도 부르지 않았다"
        );
        std::thread::sleep(Duration::from_millis(400));
        assert_eq!(
            looks.load(Ordering::SeqCst) - before,
            1,
            "hint 백 개가 관측 한 번으로 합쳐지지 않았다"
        );
    }

    #[test]
    fn twenty_refreshes_before_the_deadline_do_not_look_again() {
        let (window, _root, looks) = live("twenty-refreshes", brisk());
        let before = settle(&looks);
        for _ in 0..20 {
            assert!(status(&proper(&window, "GET")).contains("200"));
        }
        assert_eq!(
            looks.load(Ordering::SeqCst),
            before,
            "화면을 스무 번 읽었다는 이유로 프로젝트를 다시 열었다"
        );
    }

    #[test]
    fn looking_does_not_make_more_hints() {
        // **이 시험이 없으면 고리를 못 본다.** 관측이 `.gil` 을 만지고, 그 사건이 hint 가
        // 되고, hint 가 관측을 부르면 창은 영원히 프로젝트를 다시 연다.
        let (_window, _root, looks) = live("no-self-loop", brisk());
        // 시작의 잡음이 가라앉기를 기다린 뒤에 잰다.
        let quiet = settle(&looks);
        // reconciliation(3초) 이 오기 전까지 조용해야 한다. 고리가 있으면 debounce(100ms)
        // 마다 한 번씩 늘어나 열다섯 번쯤이 된다.
        std::thread::sleep(Duration::from_millis(1500));
        assert_eq!(
            looks.load(Ordering::SeqCst),
            quiet,
            "관측이 스스로를 다시 불렀다 — .gil 사건이 hint 로 새고 있다"
        );
    }

    #[test]
    fn an_idle_stretch_only_reconciles() {
        let pace = Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_millis(500),
            retry: Duration::from_millis(400),
        };
        let (_window, _root, looks) = live("idle-reconciles", pace);
        let before = looks.load(Ordering::SeqCst);
        std::thread::sleep(Duration::from_millis(1600));
        let taken = looks.load(Ordering::SeqCst) - before;
        // 1.6초 동안 500ms 기한이면 세 번쯤이다. 두 배로 늘어나면 무언가가 더 부르고 있다.
        assert!(
            (2..=4).contains(&taken),
            "변화가 없는 구간에서 {taken}번 관측했다 — 기한만큼이 아니다"
        );
    }

    #[test]
    fn a_stalled_request_does_not_stop_the_timers() {
        let (window, _root, looks) = live("stalled-request", brisk());
        let _ = settle(&looks);
        // 반만 보내고 침묵하는 연결 하나를 걸어 둔다. greeter 는 여기 묶인다.
        let mut stalled = TcpStream::connect(window.address()).expect("붙는다");
        stalled
            .write_all(format!("GET {} HTTP/1.1\r\n", window.path()).as_bytes())
            .expect("반만 보낸다");

        // 그 사이에도 worker 는 제 기한대로 깨어난다.
        let before = looks.load(Ordering::SeqCst);
        window.hint();
        assert!(
            until(Duration::from_secs(3), || looks.load(Ordering::SeqCst)
                > before),
            "느린 연결 하나가 갱신을 멈춰 세웠다"
        );
        drop(stalled);
    }

    #[test]
    fn a_stale_screen_recovers_with_no_browser_and_no_event() {
        // 첫 관측만 성공하고 그 다음이 실패했다가 다시 성공하는 관측기.
        let label = "stale-recovers-alone";
        let (observer, watch) = watched(vec![
            Ok(a_snapshot(label)),
            Err("잠금을 얻지 못했다".to_string()),
            Ok(a_snapshot(label)),
        ]);
        let pace = Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_millis(300),
            retry: Duration::from_millis(300),
        };
        let window = serve(observer, pace, wall_clock(), None).expect("창을 연다");

        // ①② 기한이 와서 두 번째 관측이 실패한다 → Stale
        assert!(
            until(Duration::from_secs(3), || watch.calls.load(Ordering::SeqCst) >= 2),
            "기한이 왔는데 다시 보지 않았다"
        );
        // ③④ 사건도 browser 도 없이 retry 기한만으로 회복한다.
        assert!(
            until(Duration::from_secs(3), || watch.calls.load(Ordering::SeqCst) >= 3),
            "실패한 뒤 스스로 다시 시도하지 않았다"
        );
        let page = screen(&window);
        assert!(page.contains("활성 경로"), "회복하지 못했다");
        assert!(!page.contains("이 내용은 최신이 아니다"), "낡은 채로 남았다: {page}");
    }

    // ── ⑨ 무엇을 보고 무엇을 못 본 척하는가 ───────────────────────────────

    #[test]
    fn the_filter_is_deaf_only_to_gils_own_noise() {
        let root = Path::new("/p");
        let gil = root.join(crate::artifact::GIL_DIR);
        // 다시 볼 만한 것.
        for path in [
            "/p/a.txt",
            "/p/깊은/자리/b.rs",
            "/p/.gil/state.yaml",
            // 더 깊은 곳의 `.gil` — 제외 대상이 아니라 **관측 거절 사유**다(Artifact §3.4).
            "/p/안쪽/.gil",
            "/p/안쪽/.gil/state.yaml",
            // `.gil` 이라는 이름의 일반 파일은 중첩 저장소가 아니다.
            "/p/.gilignore",
        ] {
            assert!(
                worth_looking(Path::new(path), &gil),
                "{path} 을 못 본 척했다"
            );
        }
        // Monitor 자신의 잡음.
        for path in [
            "/p/.gil",
            "/p/.gil/project.lock",
            "/p/.gil/artifacts/tmp/무언가",
            "/p/.gil/artifacts/blobs/sha256/ab/cdef",
            "/p/.gil/artifacts/manifests/sha256/ab/cdef",
            "/p/.gil/restore/active/PLAN",
            "/p/.gil/restore/preparing-1234-x/backup/0",
            "/p/.gil/state.yaml.tmp",
        ] {
            assert!(
                !worth_looking(Path::new(path), &gil),
                "{path} 을 다시 볼 만하다고 했다"
            );
        }
    }

    #[test]
    fn a_watcher_that_cannot_start_leaves_the_window_open_and_says_so() {
        // 있지도 않은 자리를 감시하라고 한다.
        let label = "blind-window";
        let (observer, _watch) = watched(vec![Ok(a_snapshot(label))]);
        let nowhere = std::env::temp_dir().join("gil-live-nowhere-at-all");
        let _ = std::fs::remove_dir_all(&nowhere);
        let window = serve(observer, brisk(), wall_clock(), Some(&nowhere)).expect("창은 연다");

        assert!(window.blind().is_some(), "서지 못했는데 섰다고 한다");
        let page = screen(&window);
        assert!(
            page.contains("변화를 스스로 알아채지 못한다"),
            "눈이 먼 것을 화면이 말하지 않는다: {page}"
        );
        // 그래도 사실은 보인다 — 화면을 통째로 빼앗지 않는다.
        assert!(page.contains("활성 경로"), "사실까지 사라졌다");
    }

    #[test]
    fn closing_a_live_window_leaves_nothing_running() {
        let quick = Pace {
            debounce: Duration::from_millis(100),
            reconcile: Duration::from_millis(400),
            retry: Duration::from_millis(400),
        };
        let (mut window, root, looks) = live("closing-live", quick);
        let a = std::fs::read(root.join("a.txt")).expect("세계를 읽는다");
        let state = std::fs::read(root.join(crate::STATE_PATH)).expect("상태를 읽는다");
        let address = window.address();

        window.close();

        assert!(window.watcher.is_none(), "감시가 남았다");
        // **갈래가 진짜 멈췄는가.** `None` 이 된 것은 손잡이를 놓았다는 뜻일 뿐이다.
        // 살아남은 갈래는 제 기한마다 계속 관측한다 — 그것으로 잰다.
        let after_close = looks.load(Ordering::SeqCst);
        std::thread::sleep(Duration::from_millis(1200));
        assert_eq!(
            looks.load(Ordering::SeqCst),
            after_close,
            "닫았는데 갈래가 아직 돌고 있다"
        );
        // 주소는 더 이상 답하지 않는다.
        assert!(
            TcpStream::connect_timeout(&address, Duration::from_millis(200)).is_err(),
            "닫았는데 아직 붙는다"
        );
        // 프로젝트도 작업 파일도 그대로다.
        assert_eq!(a, std::fs::read(root.join("a.txt")).expect("다시 읽는다"));
        assert_eq!(
            state,
            std::fs::read(root.join(crate::STATE_PATH)).expect("다시 읽는다")
        );
        // 다음 명령이 곧바로 잠금을 얻는다.
        assert!(
            crate::ProjectSession::open(
                crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
                root.join(crate::STATE_PATH),
            )
            .is_ok(),
            "닫은 뒤에도 잠금이 남았다"
        );
    }


    // ── ⑩ 신호는 프로세스의 것이다 ────────────────────────────────────────
    //
    // 이 절의 시험들은 **process 전체를 공유한다.** 처리기가 걸려 있지 않은 순간에 신호를
    // 올리면 이 시험 프로세스가 그대로 죽는다. 그래서 둘을 지킨다 — 한 번에 하나만 돌고,
    // 신호는 처리기가 실제로 걸린 것을 **확인한 뒤에만** 올린다.

    /// 신호를 만지는 시험은 한 줄로 선다.
    static ONE_AT_A_TIME: std::sync::Mutex<()> = std::sync::Mutex::new(());

    /// 지금 이 신호에 걸려 있는 처리기.
    fn handler_of(signal: libc::c_int) -> libc::sighandler_t {
        unsafe {
            let mut now: libc::sigaction = std::mem::zeroed();
            assert_eq!(
                libc::sigaction(signal, std::ptr::null(), &mut now),
                0,
                "지금 걸린 처리기를 물어볼 수 없다"
            );
            now.sa_sigaction
        }
    }

    /// 우리 처리기의 주소.
    fn ours() -> libc::sighandler_t {
        note_interrupt as extern "C" fn(libc::c_int) as libc::sighandler_t
    }

    /// 시험이 잠깐 걸어 두는 남의 처리기 — 복원되었는지 알아보려고.
    extern "C" fn someone_elses(_signal: libc::c_int) {}

    /// 처리기가 **실제로 걸린 것을 본 뒤** 신호 하나를 올린다.
    ///
    /// 먼저 올리면 아직 기본 처리기라 이 프로세스가 죽는다. 그래서 기다렸다 올린다.
    fn signal_once_armed(signal: libc::c_int, after: Duration) -> std::thread::JoinHandle<bool> {
        std::thread::spawn(move || {
            let start = Instant::now();
            while start.elapsed() < Duration::from_secs(5) {
                if handler_of(signal) == ours() {
                    std::thread::sleep(after);
                    unsafe { libc::raise(signal) };
                    return true;
                }
                std::thread::sleep(Duration::from_millis(5));
            }
            false
        })
    }

    /// 신호 시험이 쓸 창 하나 — 감시 없이, 가짜 관측기로.
    fn a_window(label: &str) -> MonitorServer {
        let (observer, _watch) = watched(vec![Ok(a_snapshot(label))]);
        MonitorServer(serve(observer, pace(), wall_clock(), None).expect("창을 연다"))
    }

    #[test]
    fn two_waits_in_a_row_each_run_until_their_own_signal() {
        let _line = ONE_AT_A_TIME.lock().unwrap_or_else(|held| held.into_inner());

        // ① 첫 기다림은 SIGINT 로 끝난다.
        let mut first = a_window("signal-first");
        let raised = signal_once_armed(libc::SIGINT, Duration::from_millis(50));
        let began = Instant::now();
        assert!(first.wait().is_ok(), "첫 기다림이 거절당했다");
        assert!(raised.join().expect("신호 갈래"), "신호를 올리지 못했다");
        assert!(began.elapsed() >= Duration::from_millis(50), "신호 전에 끝났다");

        // ③ 첫 실행의 값이 남아 있지 않다.
        assert!(
            !INTERRUPTED.load(Ordering::SeqCst),
            "지난 신호가 그대로 남았다"
        );
        assert!(!WAITING.load(Ordering::SeqCst), "차례를 놓지 않았다");

        // ② 둘째 기다림은 **제 신호가 올 때까지** 돈다 — 즉시 끝나지 않는다.
        let mut second = a_window("signal-second");
        let raised = signal_once_armed(libc::SIGINT, Duration::from_millis(400));
        let began = Instant::now();
        assert!(second.wait().is_ok(), "둘째 기다림이 거절당했다");
        assert!(raised.join().expect("신호 갈래"), "신호를 올리지 못했다");
        assert!(
            began.elapsed() >= Duration::from_millis(400),
            "지난 신호를 물려받아 즉시 끝났다: {:?}",
            began.elapsed()
        );
    }

    #[test]
    fn sigterm_takes_the_same_road_as_sigint() {
        let _line = ONE_AT_A_TIME.lock().unwrap_or_else(|held| held.into_inner());
        let mut window = a_window("signal-sigterm");
        let address = window.0.address();
        let raised = signal_once_armed(libc::SIGTERM, Duration::from_millis(50));
        assert!(window.wait().is_ok());
        assert!(raised.join().expect("신호 갈래"), "신호를 올리지 못했다");
        // 같은 `close()` 를 지났다 — 주소가 죽었고 갈래도 감시도 없다.
        assert!(
            TcpStream::connect_timeout(&address, Duration::from_millis(200)).is_err(),
            "SIGTERM 이 다른 길로 갔다"
        );
        assert!(window.0.greeter.is_none() && window.0.worker.is_none());
    }

    #[test]
    fn the_handlers_that_were_there_before_are_put_back() {
        let _line = ONE_AT_A_TIME.lock().unwrap_or_else(|held| held.into_inner());
        // 남의 처리기를 걸어 둔다 — host program 이 제 정책을 갖고 있는 상황이다.
        let mine = someone_elses as extern "C" fn(libc::c_int) as libc::sighandler_t;
        let (int_before, term_before) = unsafe {
            let mut new: libc::sigaction = std::mem::zeroed();
            new.sa_sigaction = mine;
            libc::sigemptyset(&mut new.sa_mask);
            let (mut old_int, mut old_term): (libc::sigaction, libc::sigaction) =
                (std::mem::zeroed(), std::mem::zeroed());
            libc::sigaction(libc::SIGINT, &new, &mut old_int);
            libc::sigaction(libc::SIGTERM, &new, &mut old_term);
            (old_int, old_term)
        };
        assert_eq!(handler_of(libc::SIGINT), mine);
        assert_eq!(handler_of(libc::SIGTERM), mine);

        let mut window = a_window("signal-restore");
        let raised = signal_once_armed(libc::SIGINT, Duration::from_millis(50));
        assert!(window.wait().is_ok());
        assert!(raised.join().expect("신호 갈래"));

        // ⑤⑥ 둘 다 제자리로.
        assert_eq!(handler_of(libc::SIGINT), mine, "SIGINT 를 돌려주지 않았다");
        assert_eq!(handler_of(libc::SIGTERM), mine, "SIGTERM 을 돌려주지 않았다");

        // 시험이 빌린 것도 돌려놓는다.
        unsafe {
            libc::sigaction(libc::SIGINT, &int_before, std::ptr::null_mut());
            libc::sigaction(libc::SIGTERM, &term_before, std::ptr::null_mut());
        }
    }

    #[test]
    fn a_failed_second_install_puts_the_first_one_back() {
        let _line = ONE_AT_A_TIME.lock().unwrap_or_else(|held| held.into_inner());
        let before = handler_of(libc::SIGINT);
        // `SIGKILL` 은 잡을 수 없다 — 두 번째 설치가 반드시 실패한다.
        let refused = arm(libc::SIGINT, libc::SIGKILL);
        assert!(refused.is_err(), "잡을 수 없는 신호를 잡았다고 한다");
        assert_eq!(
            handler_of(libc::SIGINT),
            before,
            "둘째가 실패했는데 첫째가 바뀐 채로 남았다"
        );
    }

    #[test]
    fn only_one_wait_owns_the_signals() {
        let _line = ONE_AT_A_TIME.lock().unwrap_or_else(|held| held.into_inner());
        let mut first = a_window("signal-owner");
        let mut second = a_window("signal-rejected");
        let second_address = second.0.address();

        // 첫 기다림을 다른 갈래에서 시작하고, 신호를 소유할 때까지 기다린다.
        let waiting = std::thread::spawn(move || {
            let outcome = first.wait();
            (first, outcome)
        });
        let start = Instant::now();
        while handler_of(libc::SIGINT) != ours() && start.elapsed() < Duration::from_secs(5) {
            std::thread::sleep(Duration::from_millis(5));
        }
        assert_eq!(handler_of(libc::SIGINT), ours(), "첫 기다림이 서지 못했다");

        // ⑧ 둘째는 말없이 뺏지 않고 거절한다.
        let refused = second.wait();
        assert!(refused.is_err(), "둘이 함께 신호를 가졌다");
        assert!(
            refused.unwrap_err().contains("이미 다른 Monitor"),
            "무엇이 문제인지 말하지 않는다"
        );

        // ⑨ 거절당한 둘째도 떨어질 때 제대로 닫힌다.
        drop(second);
        assert!(
            TcpStream::connect_timeout(&second_address, Duration::from_millis(200)).is_err(),
            "거절당한 창이 아직 열려 있다"
        );

        // 첫 기다림을 끝낸다.
        let raised = signal_once_armed(libc::SIGINT, Duration::from_millis(20));
        let (_first, outcome) = waiting.join().expect("기다리던 갈래");
        assert!(outcome.is_ok());
        assert!(raised.join().expect("신호 갈래"));
    }

    #[test]
    fn after_waiting_the_project_is_free_and_unchanged() {
        let _line = ONE_AT_A_TIME.lock().unwrap_or_else(|held| held.into_inner());
        let label = "signal-project-intact";
        let root = std::env::temp_dir().join(format!("gil-serve-{label}"));
        let _ = a_snapshot(label); // 자리를 세운다
        let world = std::fs::read(root.join("a.txt")).expect("세계를 읽는다");
        let state = std::fs::read(root.join(crate::STATE_PATH)).expect("상태를 읽는다");

        let mut window = a_window(label);
        let raised = signal_once_armed(libc::SIGINT, Duration::from_millis(50));
        assert!(window.wait().is_ok());
        assert!(raised.join().expect("신호 갈래"));

        // ⑪ 작업 파일도 state.yaml 도 그대로다.
        assert_eq!(world, std::fs::read(root.join("a.txt")).expect("다시 읽는다"));
        assert_eq!(
            state,
            std::fs::read(root.join(crate::STATE_PATH)).expect("다시 읽는다")
        );
        // ⑩ 잠금이 남지 않았다.
        assert!(
            crate::ProjectSession::open(
                crate::rules::RuleSet::builtin().expect("함께 실린 명세"),
                root.join(crate::STATE_PATH),
            )
            .is_ok(),
            "기다림이 끝났는데 잠금이 남았다"
        );
    }
}
