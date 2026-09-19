//! **Companion 설치 handshake v1** — launcher가 이름이나 경로만 보고 호환성을 짐작하지 않는 문.
//!
//! 이 문은 Project를 열지 않고 Tauri도 시작하지 않는다. 설치된 binary가 자기 identity와
//! 이해하는 protocol·wire 범위를 compact JSON 하나로 답한다. launcher는 그 답과 실행 상태를
//! 함께 보고 `missing | stopped | outdated | ready`를 가른다.

use std::ffi::OsString;
use std::io;
use std::path::PathBuf;
use std::sync::Mutex;

use serde::{Deserialize, Serialize};

pub const ARG: &str = "--gil-companion-handshake";
pub const PROBE_ARG: &str = "--gil-companion-probe";
pub const SCHEMA_VERSION: u32 = 1;
pub const PROTOCOL_VERSION: u32 = 1;
pub const PRODUCT: &str = "gil_companion";
pub const BUNDLE_ID: &str = "dev.ariadne.gil.companion";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RangeV1 {
    pub min: u32,
    pub max: u32,
}

impl RangeV1 {
    fn exact(version: u32) -> Self {
        Self {
            min: version,
            max: version,
        }
    }

    fn contains(&self, version: u32) -> bool {
        self.min <= version && version <= self.max
    }
}

/// 설치된 binary가 스스로 말하는 공개 계약. 경로·PID·Project는 싣지 않는다.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct DescriptorV1 {
    pub schema_version: u32,
    pub product: String,
    pub bundle_id: String,
    pub app_version: String,
    pub protocol: RangeV1,
    pub monitor_view_schema: RangeV1,
    pub node_detail_schema: RangeV1,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
struct ChallengeV1 {
    schema_version: u32,
    challenge: String,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct RuntimeReplyV1 {
    pub schema_version: u32,
    pub challenge: String,
    pub companion: DescriptorV1,
}

impl DescriptorV1 {
    pub fn current() -> Self {
        Self {
            schema_version: SCHEMA_VERSION,
            product: PRODUCT.to_string(),
            bundle_id: BUNDLE_ID.to_string(),
            app_version: env!("CARGO_PKG_VERSION").to_string(),
            protocol: RangeV1::exact(PROTOCOL_VERSION),
            monitor_view_schema: RangeV1::exact(gil::SCHEMA_VERSION),
            node_detail_schema: RangeV1::exact(gil::SCHEMA_VERSION),
        }
    }

    fn is_compatible_with(&self, expected: &ExpectedV1) -> bool {
        self.schema_version == SCHEMA_VERSION
            && self.product == PRODUCT
            && self.bundle_id == BUNDLE_ID
            && self.protocol.contains(expected.protocol)
            && self.monitor_view_schema.contains(expected.monitor_view_schema)
            && self.node_detail_schema.contains(expected.node_detail_schema)
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ExpectedV1 {
    pub protocol: u32,
    pub monitor_view_schema: u32,
    pub node_detail_schema: u32,
}

impl ExpectedV1 {
    pub fn current() -> Self {
        Self {
            protocol: PROTOCOL_VERSION,
            monitor_view_schema: gil::SCHEMA_VERSION,
            node_detail_schema: gil::SCHEMA_VERSION,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum InstallationState {
    Missing,
    Stopped,
    Outdated,
    Ready,
}

/// launcher가 관측한 세 사실만으로 상태를 가른다. 경로가 있다는 사실만으로 `ready`가 되지 않는다.
pub fn classify(
    installed: bool,
    descriptor: Option<&DescriptorV1>,
    runtime_reply: Option<&RuntimeReplyV1>,
    challenge: &str,
    expected: ExpectedV1,
) -> InstallationState {
    if !installed {
        return InstallationState::Missing;
    }
    let Some(descriptor) = descriptor else {
        return InstallationState::Outdated;
    };
    if !descriptor.is_compatible_with(&expected) {
        return InstallationState::Outdated;
    }
    match runtime_reply {
        Some(reply)
            if reply.schema_version == SCHEMA_VERSION
                && reply.challenge == challenge
                && reply.companion == *descriptor =>
        {
            InstallationState::Ready
        }
        _ => InstallationState::Stopped,
    }
}

/// handshake 인수이면 JSON을 돌려주고 Tauri 시작을 막는다. 그 밖의 인수는 건드리지 않는다.
pub fn answer_cli(args: impl IntoIterator<Item = OsString>) -> Option<Result<String, String>> {
    let mut args = args.into_iter();
    let _program = args.next();
    match (args.next().as_deref(), args.next(), args.next()) {
        (Some(one), None, None) if one == ARG => {
            Some(Ok(serde_json::to_string(&DescriptorV1::current()).expect("handshake JSON")))
        }
        (Some(one), Some(challenge), None) if one == PROBE_ARG => Some(
            probe(&challenge.to_string_lossy())
                .and_then(|reply| {
                    let descriptor = DescriptorV1::current();
                    match classify(
                        true,
                        Some(&descriptor),
                        Some(&reply),
                        &challenge.to_string_lossy(),
                        ExpectedV1::current(),
                    ) {
                        InstallationState::Ready => serde_json::to_string(&reply).map_err(io::Error::other),
                        _ => Err(io::Error::new(
                            io::ErrorKind::InvalidData,
                            "실행 중인 Companion의 handshake가 이 판과 맞지 않는다",
                        )),
                    }
                })
                .map_err(|err| format!("실행 중인 GIL Companion이 handshake에 답하지 않았다: {err}")),
        ),
        _ => None,
    }
}

/// 실행 중인 Companion의 challenge 문. 앱 수명 동안 하나만 산다.
pub struct RuntimeHandshake {
    inner: Mutex<Option<runtime::Server>>,
}

impl RuntimeHandshake {
    pub fn start() -> io::Result<Self> {
        runtime::Server::start(runtime_path()).map(|server| Self {
            inner: Mutex::new(Some(server)),
        })
    }

    pub fn stop(&self) {
        if let Some(server) = self.inner.lock().expect("handshake server").take() {
            server.stop();
        }
    }
}

impl Drop for RuntimeHandshake {
    fn drop(&mut self) {
        if let Some(server) = self.inner.get_mut().expect("handshake server").take() {
            server.stop();
        }
    }
}

fn runtime_path() -> PathBuf {
    std::env::temp_dir().join("dev.ariadne.gil.companion.handshake.sock")
}

fn valid_challenge(challenge: &str) -> bool {
    (16..=128).contains(&challenge.len())
        && challenge
            .bytes()
            .all(|one| one.is_ascii_alphanumeric() || one == b'-' || one == b'_')
}

fn reply(challenge: &str) -> io::Result<RuntimeReplyV1> {
    if !valid_challenge(challenge) {
        return Err(io::Error::new(io::ErrorKind::InvalidInput, "challenge 모양이 잘못됐다"));
    }
    Ok(RuntimeReplyV1 {
        schema_version: SCHEMA_VERSION,
        challenge: challenge.to_string(),
        companion: DescriptorV1::current(),
    })
}

fn probe(challenge: &str) -> io::Result<RuntimeReplyV1> {
    runtime::probe(&runtime_path(), challenge)
}

#[cfg(unix)]
mod runtime {
    use std::fs;
    use std::io::{self, BufRead, BufReader, Read, Write};
    use std::os::unix::fs::PermissionsExt;
    use std::os::unix::net::{UnixListener, UnixStream};
    use std::path::{Path, PathBuf};
    use std::sync::Arc;
    use std::sync::atomic::{AtomicBool, Ordering};
    use std::thread::{self, JoinHandle};
    use std::time::Duration;

    use super::{ChallengeV1, RuntimeReplyV1, SCHEMA_VERSION, reply, valid_challenge};

    pub struct Server {
        path: PathBuf,
        stop: Arc<AtomicBool>,
        thread: Option<JoinHandle<()>>,
    }

    impl Server {
        pub fn start(path: PathBuf) -> io::Result<Self> {
            if path.exists() {
                match UnixStream::connect(&path) {
                    Ok(_) => {
                        return Err(io::Error::new(
                            io::ErrorKind::AddrInUse,
                            "이미 handshake 문이 열려 있다",
                        ));
                    }
                    Err(_) => fs::remove_file(&path)?,
                }
            }
            let listener = UnixListener::bind(&path)?;
            fs::set_permissions(&path, fs::Permissions::from_mode(0o600))?;
            listener.set_nonblocking(true)?;
            let stop = Arc::new(AtomicBool::new(false));
            let stopping = Arc::clone(&stop);
            let thread = thread::spawn(move || {
                while !stopping.load(Ordering::SeqCst) {
                    match listener.accept() {
                        Ok((stream, _)) => {
                            // listener만 nonblocking이다. macOS에서는 accept된 stream도 그 flag를
                            // 물려받으므로, client가 한 줄을 쓰기 직전에 읽으면 WouldBlock으로
                            // 끊긴다. 연결 하나는 짧은 요청을 온전히 기다린다.
                            let served = stream.set_nonblocking(false).and_then(|_| answer(stream));
                            if let Err(err) = served {
                                eprintln!("Companion handshake 요청을 거절했다: {err}");
                            }
                        }
                        Err(err) if err.kind() == io::ErrorKind::WouldBlock => {
                            thread::sleep(Duration::from_millis(20));
                        }
                        Err(_) => break,
                    }
                }
            });
            Ok(Self {
                path,
                stop,
                thread: Some(thread),
            })
        }

        pub fn stop(mut self) {
            self.stop.store(true, Ordering::SeqCst);
            let _ = UnixStream::connect(&self.path);
            if let Some(thread) = self.thread.take() {
                let _ = thread.join();
            }
            let _ = fs::remove_file(&self.path);
        }
    }

    fn answer(mut stream: UnixStream) -> io::Result<()> {
        let mut line = String::new();
        BufReader::new(stream.try_clone()?)
            .take(4097)
            .read_line(&mut line)?;
        if line.len() > 4096 {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "handshake가 너무 길다"));
        }
        let asked: ChallengeV1 = serde_json::from_str(line.trim_end())
            .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?;
        if asked.schema_version != SCHEMA_VERSION || !valid_challenge(&asked.challenge) {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "handshake 요청이 맞지 않는다"));
        }
        let said = serde_json::to_string(&reply(&asked.challenge)?)?;
        stream.write_all(said.as_bytes())?;
        stream.write_all(b"\n")?;
        stream.flush()
    }

    pub fn probe(path: &Path, challenge: &str) -> io::Result<RuntimeReplyV1> {
        if !valid_challenge(challenge) {
            return Err(io::Error::new(io::ErrorKind::InvalidInput, "challenge 모양이 잘못됐다"));
        }
        let mut stream = UnixStream::connect(path)?;
        let asked = ChallengeV1 {
            schema_version: SCHEMA_VERSION,
            challenge: challenge.to_string(),
        };
        stream.write_all(serde_json::to_string(&asked)?.as_bytes())?;
        stream.write_all(b"\n")?;
        stream.flush()?;
        let mut line = String::new();
        BufReader::new(stream).take(16385).read_line(&mut line)?;
        if line.len() > 16384 {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "handshake 응답이 너무 길다"));
        }
        let replied: RuntimeReplyV1 = serde_json::from_str(line.trim_end())
            .map_err(|err| io::Error::new(io::ErrorKind::InvalidData, err))?;
        if replied.challenge != challenge {
            return Err(io::Error::new(io::ErrorKind::InvalidData, "challenge가 돌아오지 않았다"));
        }
        Ok(replied)
    }
}

#[cfg(not(unix))]
mod runtime {
    use std::io;
    use std::path::{Path, PathBuf};

    use super::RuntimeReplyV1;

    pub struct Server;

    impl Server {
        pub fn start(_path: PathBuf) -> io::Result<Self> {
            // Companion 자체는 계속 쓸 수 있다. 이 platform의 launcher는 runtime challenge를
            // 확인할 수 없으므로 `ready`가 아니라 `stopped`에 머문다.
            Ok(Self)
        }

        pub fn stop(self) {}
    }

    pub fn probe(_path: &Path, _challenge: &str) -> io::Result<RuntimeReplyV1> {
        Err(io::Error::new(io::ErrorKind::Unsupported, "이 platform의 IPC는 아직 없다"))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn args(words: &[&str]) -> Vec<OsString> {
        words.iter().map(OsString::from).collect()
    }

    #[test]
    fn the_handshake_is_compact_canonical_json_without_a_path_or_project() {
        let said = answer_cli(args(&["gil-companion", ARG]))
            .expect("handshake")
            .expect("answer");
        assert!(!said.contains('\n'));
        assert!(!said.contains("/Users/"));
        assert!(!said.contains("project"));

        let decoded: DescriptorV1 = serde_json::from_str(&said).expect("descriptor");
        assert_eq!(decoded, DescriptorV1::current());
        assert_eq!(serde_json::to_string(&decoded).expect("JSON"), said);
    }

    #[test]
    fn ordinary_launch_arguments_do_not_enter_the_handshake_door() {
        for words in [
            vec!["gil-companion"],
            vec!["gil-companion", "--help"],
            vec!["gil-companion", ARG, "extra"],
        ] {
            assert_eq!(answer_cli(args(&words)), None);
        }
    }

    #[test]
    fn path_presence_alone_never_means_ready() {
        let expected = ExpectedV1::current();
        assert_eq!(
            classify(false, None, None, "abcdefghijklmnop", expected),
            InstallationState::Missing
        );
        assert_eq!(
            classify(true, None, None, "abcdefghijklmnop", expected),
            InstallationState::Outdated
        );
        assert_eq!(
            classify(true, None, None, "abcdefghijklmnop", expected),
            InstallationState::Outdated
        );
    }

    #[test]
    fn a_compatible_descriptor_distinguishes_stopped_from_ready() {
        let descriptor = DescriptorV1::current();
        let expected = ExpectedV1::current();
        let challenge = "abcdefghijklmnop";
        assert_eq!(classify(true, Some(&descriptor), None, challenge, expected), InstallationState::Stopped);
        let replied = reply(challenge).expect("reply");
        assert_eq!(
            classify(true, Some(&descriptor), Some(&replied), challenge, expected),
            InstallationState::Ready
        );
    }

    #[test]
    fn every_incompatible_boundary_is_outdated() {
        let expected = ExpectedV1::current();
        let mutations = [
            |one: &mut DescriptorV1| one.schema_version += 1,
            |one: &mut DescriptorV1| one.product = "another".into(),
            |one: &mut DescriptorV1| one.bundle_id = "dev.another.app".into(),
            |one: &mut DescriptorV1| one.protocol = RangeV1::exact(2),
            |one: &mut DescriptorV1| one.monitor_view_schema = RangeV1::exact(2),
            |one: &mut DescriptorV1| one.node_detail_schema = RangeV1::exact(2),
        ];
        for mutate in mutations {
            let mut descriptor = DescriptorV1::current();
            mutate(&mut descriptor);
            assert_eq!(
                classify(true, Some(&descriptor), None, "abcdefghijklmnop", expected),
                InstallationState::Outdated
            );
        }
    }

    #[test]
    fn ready_requires_the_same_fresh_challenge() {
        let descriptor = DescriptorV1::current();
        let replied = reply("abcdefghijklmnop").expect("reply");
        assert_eq!(
            classify(
                true,
                Some(&descriptor),
                Some(&replied),
                "ponmlkjihgfedcba",
                ExpectedV1::current(),
            ),
            InstallationState::Stopped
        );
    }

    #[cfg(unix)]
    #[test]
    fn the_running_process_answers_a_fresh_challenge_over_a_private_socket() {
        use std::os::unix::fs::PermissionsExt;

        let dir = std::env::temp_dir().join(format!("gil-handshake-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&dir);
        std::fs::create_dir_all(&dir).expect("scratch");
        let path = dir.join("companion.sock");
        let server = runtime::Server::start(path.clone()).expect("server");
        for turn in 0..50 {
            let challenge = format!("fresh_challenge_{turn:04}");
            let replied = runtime::probe(&path, &challenge).expect("probe");
            assert_eq!(replied.challenge, challenge);
            assert_eq!(replied.companion, DescriptorV1::current());
        }
        assert_eq!(
            std::fs::metadata(&path).expect("socket").permissions().mode() & 0o777,
            0o600
        );
        server.stop();
        assert!(!path.exists());
        let _ = std::fs::remove_dir_all(dir);
    }
}
