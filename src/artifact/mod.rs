//! Artifact 관측 — **지금 이 폴더가 어떤 세계인가.**
//!
//! 여기서 하는 일은 하나다: 프로젝트를 읽어 [`Manifest`] 를 만든다. **아무것도 저장하지
//! 않는다** — Snapshot 객체도, `SnapshotRef` 도, `state.yaml` 도 이 모듈은 모른다.
//!
//! ```text
//! observe(root)  →  Manifest        관측만 한다
//!                   ↑
//!                   두 번 읽어 같을 때만 돌려준다
//! ```
//!
//! # 세계의 정체성은 경로와 바이트다
//!
//! Artifact Model §3.1 — 일반 파일의 정체성은 **정규화된 상대 경로 + 실제 바이트** 둘이다.
//! mtime·소유자·권한은 세계의 일부가 아니고, 빈 디렉터리도 아니다. 내용은 **바이트로**
//! 비교한다 — 줄바꿈도 인코딩도 GIL 이 바꾸지 않는다. 「정규화」는 **경로에만** 쓰는 말이다.
//!
//! # 조용히 빠지는 것이 없다
//!
//! 심볼릭 링크·특수 항목·UTF-8 로 못 적는 경로·중첩 GIL 저장소를 만나면 **그 항목만 빼는
//! 것이 아니라 관측 전체를 거절한다**(§3.4). 조용한 제외는 "그 파일은 세계에 없다" 는
//! 거짓말이 되고, 그 거짓말 위에 세운 Snapshot 은 복원할 때 진실이 아니다.

// 아직 crate 안의 아무도 이 기계를 부르지 않는다 — 관측기가 먼저 서고, 그것을 쓰는
// Snapshot 저장소가 다음 조각이다. **이 줄은 M3-B 가 관측기를 붙이는 순간 지운다.**
#![allow(dead_code)]

use std::ffi::OsStr;
use std::fmt;
use std::fs::{self, File};
use std::io::{self, Read};
use std::path::Path;

use sha2::{Digest, Sha256};

mod codec;
mod registry;
mod store;

// format 4 가 Cycle 의 entry/exit 와 함께 서면서 **쓰는 자리가 생겼다.** 도메인이
// registry 를 들고, 저장이 그것을 적는다.
//
// 이 중 밖으로 나가는 것은 [`ManifestAddress`] **하나뿐**이다(`lib.rs`). 세계를 여는
// 문(`Project::start`)이 세계의 주소를 받아야 하기 때문이다. 나머지 — 창고·manifest·
// blob 주소 — 는 안에 남는다.
pub use registry::{ManifestAddress, RegistryError};
#[allow(unused_imports)]
pub(crate) use registry::{SnapshotRecord, SnapshotRegistry};
pub(crate) use store::{ObjectError, ObjectStore};

/// 현재 프로젝트의 내부 저장소가 놓이는 이름.
///
/// **루트 바로 아래의 이것 하나만 제외한다.** 더 깊은 곳의 같은 이름은 제외가 아니라
/// 거절 사유다([`ObserveError::NestedGilRepository`]).
const GIL_DIR: &str = ".gil";

/// 파일을 읽어 들이는 조각의 크기.
///
/// 파일 전체를 메모리에 올리지 않기 위한 것이다(§3.5). 공개 계약이 아니라 구현 선택이므로
/// 값이 바뀌어도 manifest 는 같다.
const CHUNK: usize = 64 * 1024;

// ── 경로 ───────────────────────────────────────────────────────────────────

pub(crate) use path::EntryPath;

/// **`EntryPath` 를 만들 수 있는 유일한 자리.**
///
/// 안쪽 `String` 은 이 모듈 밖에서 손댈 수 없다. 바깥은 [`EntryPath::from_components`] 나
/// [`EntryPath::parse`] 를 지날 수밖에 없으므로, 계약은 규율이 아니라 **컴파일러가** 지킨다.
mod path {
    use std::fmt;

    /// manifest 에 적히는 **정규화된 프로젝트 상대 경로.**
    ///
    /// 계약을 **생성 시점에** 강제한다(Artifact Model §3.3). 이 타입을 손에 넣었다면 다음이
    /// 이미 참이다.
    ///
    /// ```text
    /// 프로젝트 루트 기준 상대 경로   절대경로가 아니다
    /// UTF-8                          운영체제 바이트가 아니다
    /// 구분자는 / 하나               `\` 를 담은 이름은 아예 들어오지 못한다
    /// 비어 있지 않다
    /// `.` 도 `..` 도 없다
    /// ```
    ///
    /// **대소문자와 Unicode 표기는 관측한 그대로 보존한다.** 정규화는 구분자를 `/` 로 만드는
    /// 것만 뜻한다 — NFC/NFD 변환도, 대소문자 접기도 하지 않는다.
    ///
    /// 운영체제 절대 경로를 담지 않으므로, **프로젝트 폴더를 옮겨도 같은 값**이다.
    #[derive(Debug, Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
    pub(crate) struct EntryPath(String);

    impl EntryPath {
        /// 루트 기준 상대 경로 **조각들**을 canonical 표현으로 잇는다.
        ///
        /// 조각 하나라도 계약을 어기면 `None` — 부르는 쪽이 관측 전체를 거절한다.
        /// 파일 시스템에서 온 이름이든 사람이 적은 글이든 **이 검사 하나를 지난다.**
        pub(crate) fn from_components(parts: &[String]) -> Option<EntryPath> {
            if parts.is_empty() {
                return None;
            }
            for part in parts {
                if !is_usable(part) {
                    return None;
                }
            }
            Some(EntryPath(parts.join("/")))
        }

        /// 사람이 적어 준 canonical 글자를 경로로 읽는다.
        ///
        /// **관측이 만든 값은 언제나 이 문을 다시 통과한다** — 두 자리가 같은 규칙을 쓰기
        /// 때문이다. 왕복하지 못하는 값을 manifest 에 담지 않는다.
        pub(crate) fn parse(text: &str) -> Option<EntryPath> {
            let parts: Vec<String> = text.split('/').map(str::to_string).collect();
            EntryPath::from_components(&parts)
        }

        /// canonical 표현 — 사람이 읽고 그대로 베끼는 글자.
        pub(crate) fn as_str(&self) -> &str {
            &self.0
        }

        /// **정렬과 비교의 근거.** 경로의 UTF-8 바이트를 부호 없는 값으로 본다.
        ///
        /// locale·collation·파일 시스템 열거 순서에 기대지 않는다 — 같은 세계는 어느
        /// 기계에서 관측해도 같은 순서의 manifest 가 된다.
        pub(crate) fn key(&self) -> &[u8] {
            self.0.as_bytes()
        }
    }

    /// 경로 **한 조각**이 Artifact 경로에 쓰일 수 있는가.
    ///
    /// `\` 를 막는 것이 규범이다(Artifact Model §3.3): `/` 가 유일한 canonical 구분자이므로,
    /// 이름 안에 `\` 를 담은 파일은 v0 Artifact 경로로 **표현되지 않는다.** 이것은 Windows
    /// 경로를 `\` 로 저장한다는 뜻이 아니다 — 모든 플랫폼의 공개 표현은 `/` 하나다.
    fn is_usable(part: &str) -> bool {
        !part.is_empty() && part != "." && part != ".." && !part.contains('\\')
    }

    impl fmt::Display for EntryPath {
        fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
            f.write_str(&self.0)
        }
    }
}

/// 관측이 무엇을 보다가 멈췄는가.
///
/// **프로젝트 루트는 파일이 아니다.** 루트에서 읽기가 실패해도 그것을 `EntryPath` 로 적으면
/// 「`.` 도 `..` 도 없다」는 계약을 모듈 안에서 스스로 어기게 된다. 그래서 자리를 **두 가지**로
/// 나눈다 — 루트이거나, 실재하는 항목이거나.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ObserveLocation {
    /// 관측 뿌리 그 자체. manifest 항목이 아니고 정렬 대상도 아니다.
    Root,
    Entry(EntryPath),
}

impl fmt::Display for ObserveLocation {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ObserveLocation::Root => f.write_str("프로젝트 루트"),
            ObserveLocation::Entry(path) => write!(f, "{path}"),
        }
    }
}

// ── 내용 ───────────────────────────────────────────────────────────────────

/// 내용 digest 를 만든 알고리즘.
///
/// **manifest 가 어떤 알고리즘으로 만들어졌는지 스스로 밝히게** 한다. 저장 계층이 생기면
/// 이 값이 함께 눕고, 알고리즘을 바꿀 때 옛 manifest 를 알아볼 수 있다. 지금은 하나뿐이다.
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(crate) enum DigestAlgorithm {
    Sha256,
}

impl DigestAlgorithm {
    pub(crate) fn as_str(self) -> &'static str {
        match self {
            DigestAlgorithm::Sha256 => "sha256",
        }
    }
}

impl fmt::Display for DigestAlgorithm {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

/// 파일 **실제 바이트**의 지문.
///
/// # 이것은 공개 Artifact 정체성이 아니다
///
/// 사용자와 Agent 가 보는 세계의 이름은 `snapshot:A1` 이다(Artifact Model §13). digest 는
/// 저장소가 같은 내용을 알아보는 **내부 수단**이며, Report·CLI·오류 메시지에 raw digest 를
/// 내보이지 않는다. 그래서 안쪽 바이트를 꺼내는 공개 문을 두지 않는다.
///
/// 경로는 여기 섞지 않는다 — 같은 내용의 파일은 어디에 있든 같은 digest 이고, 경로의
/// 다름은 [`ManifestEntry`] 가 따로 잰다.
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub(crate) struct ContentDigest {
    algorithm: DigestAlgorithm,
    bytes: [u8; 32],
}

impl ContentDigest {
    pub(crate) fn algorithm(&self) -> DigestAlgorithm {
        self.algorithm
    }

    /// 읽어 온 32 바이트를 지문으로 되세운다 — **codec 과 저장소만** 쓴다.
    ///
    /// 알고리즘 태그가 맞는지는 부르는 쪽이 이미 확인했다. 이 문은 자식 모듈에만 보이므로
    /// 밖에서 아무 바이트나 지문이라고 우길 수 없다.
    fn from_raw(algorithm: DigestAlgorithm, bytes: [u8; 32]) -> ContentDigest {
        ContentDigest { algorithm, bytes }
    }

    /// 지문의 바이트 — 객체 주소를 조립하는 자리에서만 쓴다.
    fn raw(&self) -> &[u8; 32] {
        &self.bytes
    }

    /// 소문자 16진수 — 객체 경로의 글자.
    fn hex(&self) -> String {
        let mut out = String::with_capacity(64);
        for byte in &self.bytes {
            use fmt::Write as _;
            let _ = write!(out, "{byte:02x}");
        }
        out
    }

    /// 열어 둔 파일을 **조각으로 흘려 가며** 지문을 만든다.
    ///
    /// 파일 크기만 한 버퍼를 잡지 않는다(§3.5) — 대용량 파일도 다른 일반 파일과 같은
    /// Artifact 이고, 공개 크기 상한을 두지 않기 때문이다.
    fn of(mut reader: impl Read) -> io::Result<ContentDigest> {
        let mut hasher = Sha256::new();
        let mut chunk = vec![0u8; CHUNK];
        loop {
            let read = reader.read(&mut chunk)?;
            if read == 0 {
                break;
            }
            hasher.update(&chunk[..read]);
        }
        Ok(ContentDigest {
            algorithm: DigestAlgorithm::Sha256,
            bytes: hasher.finalize().into(),
        })
    }
}

/// 진단에 쓰는 짧은 꼴. **공개 참조가 아니다** — 사람에게 보이는 세계의 이름은 `snapshot:A1`.
impl fmt::Debug for ContentDigest {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "{}:", self.algorithm)?;
        for byte in &self.bytes[..6] {
            write!(f, "{byte:02x}")?;
        }
        f.write_str("…")
    }
}

// ── manifest ───────────────────────────────────────────────────────────────

/// 세계를 이루는 파일 하나 — **어디에 있고 무엇이 담겼는가.**
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ManifestEntry {
    pub(crate) path: EntryPath,
    pub(crate) content: ContentDigest,
}

/// 한 순간의 Artifact 세계 전부.
///
/// **만들어질 때 이미 canonical 정렬 상태다** — 정렬을 밖에서 해 주기를 기다리지 않는다.
/// 두 manifest 의 동일성은 정렬된 `(EntryPath, ContentDigest)` 집합의 동일성이고, 그것이
/// 곧 "같은 세계인가" 의 답이다(§6).
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct Manifest {
    entries: Vec<ManifestEntry>,
}

impl Manifest {
    /// 모아 온 항목들을 canonical 순서로 세운다.
    ///
    /// 파일 시스템이 어떤 순서로 돌려주든 결과는 같다 — 경로의 UTF-8 바이트 오름차순 하나가
    /// canonical 이다(§3.3).
    pub(crate) fn new(mut entries: Vec<ManifestEntry>) -> Manifest {
        entries.sort_by(|left, right| left.path.key().cmp(right.path.key()));
        Manifest { entries }
    }

    /// **이미 canonical 순서임이 확인된** 항목들로 세운다.
    ///
    /// [`Manifest::new`] 와 달리 다시 정렬하지 않는다. codec 이 읽어 온 것을 여기 담는데,
    /// 거기서는 순서 자체가 검증 대상이라 **조용히 고치면 안 되기** 때문이다 — 비canonical
    /// 입력은 정렬해서 받아들이는 것이 아니라 거절한다.
    fn from_verified(entries: Vec<ManifestEntry>) -> Manifest {
        Manifest { entries }
    }

    /// 세계를 이루는 파일들 — canonical 순서로.
    pub(crate) fn entries(&self) -> &[ManifestEntry] {
        &self.entries
    }

    pub(crate) fn len(&self) -> usize {
        self.entries.len()
    }

    pub(crate) fn is_empty(&self) -> bool {
        self.entries.is_empty()
    }

    /// 그 자리에 무엇이 담겼는가. 없으면 `None`.
    pub(crate) fn get(&self, path: &EntryPath) -> Option<&ContentDigest> {
        self.entries
            .iter()
            .find(|entry| &entry.path == path)
            .map(|entry| &entry.content)
    }

    /// 담긴 경로들 — canonical 순서로.
    pub(crate) fn paths(&self) -> impl Iterator<Item = &EntryPath> {
        self.entries.iter().map(|entry| &entry.path)
    }
}

// ── 관측 ───────────────────────────────────────────────────────────────────

/// 프로젝트를 읽어 지금의 세계를 만든다.
///
/// **한 번 읽은 것을 바로 돌려주지 않는다.** 후보를 만들고, 다시 관측하고, 둘이 같을 때만
/// 돌려준다(§6 「안정된 관측」). 읽는 동안 프로젝트가 변하면 서로 다른 순간의 파일이 하나의
/// 세계로 조용히 섞이는데, 그렇게 만든 Snapshot 은 어느 순간도 재현하지 못한다.
///
/// 다르면 [`ObserveError::ChangedDuringObservation`] 으로 거절하고 **부분 결과를 돌려주지
/// 않는다.** 이 함수는 아무것도 쓰지 않으므로, 거절해도 프로젝트 파일과 GIL 논리 상태는
/// 한 글자도 바뀌지 않는다.
///
/// GIL 은 외부 프로세스의 쓰기를 **막는다고 주장하지 않는다.** 여기서 하는 것은 확정 직전에
/// 한 번 더 보는 것뿐이다.
/// 열어 둔 것을 흘려 읽어 지문을 만든다 — **복원이 「지금 이 자리」를 잴 때 쓴다.**
pub(crate) fn digest_of(reader: impl Read) -> io::Result<ContentDigest> {
    ContentDigest::of(reader)
}

/// 지문의 32 바이트 — **계획 codec 만** 쓴다. 사람에게 보이는 값이 아니다.
pub(crate) fn digest_bytes(digest: &ContentDigest) -> &[u8; 32] {
    digest.raw()
}

/// 읽어 온 32 바이트를 지문으로 되세운다 — 알고리즘 태그는 부르는 쪽이 이미 확인했다.
pub(crate) fn digest_from_raw(bytes: [u8; 32]) -> ContentDigest {
    ContentDigest::from_raw(DigestAlgorithm::Sha256, bytes)
}

pub(crate) fn observe(root: &Path) -> Result<Manifest, ObserveError> {
    observe_twice(root, || {})
}

/// 훑기가 몇 번 일어났는지 세는 자리 — **시험에서만 컴파일된다.**
///
/// 「파일을 두 번만 읽는다」는 규칙은 결과만 봐서는 잴 수 없다. 세 번째 훑기로 blob 을
/// 저장해도 세계가 조용하면 결과는 같기 때문이다. 그래서 횟수 자체를 센다 — 검증되지 않은
/// 세 번째 관측이 창고에 담기는 일을 막는 것이 이 규칙의 전부이므로.
#[cfg(test)]
pub(crate) mod scan_count {
    use std::cell::Cell;

    // **thread 마다 따로 센다.** 시험은 나란히 도는데 계수기가 하나면 남의 훑기가 섞여
    // 이 시험이 이유 없이 깜빡인다.
    thread_local! {
        static SCANS: Cell<usize> = const { Cell::new(0) };
    }

    pub(super) fn note() {
        SCANS.with(|count| count.set(count.get() + 1));
    }

    pub(crate) fn now() -> usize {
        SCANS.with(Cell::get)
    }
}

/// 두 번 훑고 견주는 **단 하나의 자리.**
///
/// `between` 은 두 훑기 **사이**에 끼어드는 틈이다. 실제 실행에서는 아무것도 하지 않고,
/// 시험만이 그 틈으로 세계를 흔들어 본다 — 잠을 재우거나 thread 를 겹쳐 운에 맡기면 그
/// 시험은 언젠가 이유 없이 깜빡인다.
///
/// **두 관측 논리를 여기 하나로 둔다.** 두 벌로 두면 한쪽만 고쳐도 다른 쪽 시험이 통과해,
/// 정작 이 규칙이 무너진 것을 아무도 모른다.
fn observe_twice(root: &Path, between: impl FnOnce()) -> Result<Manifest, ObserveError> {
    let candidate = scan(root, None)?;
    between();
    let again = scan(root, None)?;
    match candidate == again {
        true => Ok(candidate),
        false => Err(ObserveError::ChangedDuringObservation),
    }
}

/// 한 번의 훑기 — 후보 하나를 만든다.
///
/// [`observe`] 가 이것을 **두 번** 부르고 결과를 견준다. 둘을 나눠 둔 것은 다음 조각을 위한
/// 자리이기도 하다: content-addressed sink 로 바이트를 흘려보내는 것은 **첫 훑기**의 일이고,
/// 두 번째는 그것을 검증하는 재관측이다. 검증되지 않은 세 번째 훑기가 새 세계로 저장되는
/// 인터페이스로 굳지 않게 하려는 것이다.
fn scan(root: &Path, sink: Option<&ObjectStore>) -> Result<Manifest, ObserveError> {
    #[cfg(test)]
    scan_count::note();
    let mut entries = Vec::new();
    walk(root, &mut Vec::new(), true, &mut entries, sink)?;
    Ok(Manifest::new(entries))
}

/// 관측하면서 **바이트까지 창고에 눕힌다.**
///
/// ```text
/// 첫 훑기    파일을 한 번 흘려 읽으며 지문 계산 + blob 저장
/// 두 번째    저장 없이 다시 지문만 계산해 후보와 견준다
/// 같으면     manifest 를 확정할 수 있다
/// 다르면     ChangedDuringObservation — 논리 Snapshot 은 확정하지 않는다
/// ```
///
/// **파일을 세 번 읽지 않는다.** 검증되지 않은 세 번째 관측으로 blob 을 저장하면, 창고에
/// 담긴 것이 어느 순간의 세계인지 아무도 답할 수 없다.
///
/// 첫 훑기의 blob 은 지문이 정해지는 즉시 제자리(content-addressed 경로)로 간다. 두 번째
/// 관측이 다르면 그 객체들은 **미참조**로 남지만, 어떤 `SnapshotRef` 도 가리키지 않으므로
/// 논리 손상이 아니다(Artifact Model §3.5).
pub(crate) fn capture(root: &Path, store: &ObjectStore) -> Result<Manifest, ObserveError> {
    let candidate = scan(root, Some(store))?;
    let again = scan(root, None)?;
    match candidate == again {
        true => Ok(candidate),
        false => Err(ObserveError::ChangedDuringObservation),
    }
}

/// 한 디렉터리를 훑고 아래로 내려간다.
///
/// `at_root` 는 지금 보고 있는 디렉터리가 관측 뿌리인가다 — `.gil` 을 제외할지 거절할지가
/// 그 하나로 갈린다.
fn walk(
    dir: &Path,
    trail: &mut Vec<String>,
    at_root: bool,
    entries: &mut Vec<ManifestEntry>,
    sink: Option<&ObjectStore>,
) -> Result<(), ObserveError> {
    let listing = fs::read_dir(dir).map_err(|source| ObserveError::ReadFailed {
        at: here(trail),
        source: source.to_string(),
    })?;

    for item in listing {
        let item = item.map_err(|source| ObserveError::ReadFailed {
            at: here(trail),
            source: source.to_string(),
        })?;
        let name = item.file_name();

        // ① 이름이 UTF-8 로 적히지 않으면 **조용히 빼지 않고** 관측 전체를 거절한다.
        let Some(name) = utf8(&name) else {
            let shown = item.file_name().to_string_lossy().into_owned();
            return Err(ObserveError::UnrepresentablePath {
                near: here(trail),
                shown,
            });
        };
        trail.push(name);

        // ② 이 이름을 Artifact 경로로 적을 수 있는가 — `\` 를 담은 이름이 여기서 걸린다.
        //    파일 시스템에서 온 이름도 사람이 적은 글과 **같은 검사**를 지난다.
        let Some(path) = at(trail) else {
            let shown = trail.join("/");
            return Err(unrepresentable(trail, shown));
        };

        // ③ 종류를 **따라가지 않고** 본다. symlink_metadata 는 링크를 링크로 답한다.
        let kind = fs::symlink_metadata(item.path())
            .map_err(|source| ObserveError::ReadFailed {
                at: ObserveLocation::Entry(path.clone()),
                source: source.to_string(),
            })?
            .file_type();

        if kind.is_symlink() {
            return Err(ObserveError::Symlink { path });
        }

        if kind.is_dir() {
            let is_gil = trail.last().is_some_and(|name| name == GIL_DIR);
            match (is_gil, at_root) {
                // 루트의 `.gil/` — 현재 프로젝트의 내부 저장소다. 통째로 건너뛴다.
                (true, true) => {}
                // 더 깊은 곳의 `.gil/` — 중첩 GIL 경계다. **안을 들여다보지 않고** 거절한다.
                (true, false) => return Err(ObserveError::NestedGilRepository { path }),
                (false, _) => walk(&item.path(), trail, false, entries, sink)?,
            }
            trail.pop();
            continue;
        }

        if !kind.is_file() {
            return Err(ObserveError::SpecialEntry {
                path,
                kind: kind_name(&kind),
            });
        }

        // ④ 일반 파일 — 바이트를 흘려 읽는다.
        let file = File::open(item.path()).map_err(|source| ObserveError::ReadFailed {
            at: ObserveLocation::Entry(path.clone()),
            source: source.to_string(),
        })?;
        // **한 번의 스트림**으로 지문과 사본을 함께 만든다. 창고가 없으면 지문만.
        let content = match sink {
            Some(store) => store.put_blob(file).map_err(ObserveError::ObjectStore)?,
            None => ContentDigest::of(file).map_err(|source| ObserveError::ReadFailed {
                at: ObserveLocation::Entry(path.clone()),
                source: source.to_string(),
            })?,
        };

        entries.push(ManifestEntry { path, content });
        trail.pop();
    }
    Ok(())
}

/// 지금 서 있는 자리.
///
/// **뿌리를 `EntryPath` 로 지어내지 않는다.** 빈 자취는 곧 프로젝트 루트이고, 루트는 파일이
/// 아니므로 [`ObserveLocation::Root`] 다. 조각 하나라도 계약을 어기면 그것도 루트로 되짚어
/// 말한다 — 적을 수 없는 이름을 오류 메시지에서 억지로 적지 않기 위해서다.
fn here(trail: &[String]) -> ObserveLocation {
    match EntryPath::from_components(trail) {
        Some(path) => ObserveLocation::Entry(path),
        None => ObserveLocation::Root,
    }
}

/// 방금 본 항목의 상대 경로. **없을 수 없다** — 이름 하나를 자취에 얹고 부르기 때문이다.
///
/// 그래도 계약을 어긴 이름이면 `None` 이고, 그때는 부르는 쪽이
/// [`ObserveError::UnrepresentablePath`] 로 거절한다.
fn at(trail: &[String]) -> Option<EntryPath> {
    EntryPath::from_components(trail)
}

/// 이름이 계약을 어겨 경로로 못 적는 자리 — 부모까지만 말하고 이름은 글자로 보여 준다.
fn unrepresentable(trail: &[String], shown: String) -> ObserveError {
    let parent = &trail[..trail.len().saturating_sub(1)];
    ObserveError::UnrepresentablePath {
        near: here(parent),
        shown,
    }
}

fn utf8(name: &OsStr) -> Option<String> {
    name.to_str().map(str::to_string)
}

/// 그 항목이 무엇이었는지 사람의 말로. 종류를 말해야 사람이 무엇을 치울지 안다.
fn kind_name(kind: &fs::FileType) -> &'static str {
    #[cfg(unix)]
    {
        use std::os::unix::fs::FileTypeExt;
        if kind.is_fifo() {
            return "FIFO";
        }
        if kind.is_socket() {
            return "socket";
        }
        if kind.is_block_device() {
            return "block device";
        }
        if kind.is_char_device() {
            return "character device";
        }
    }
    let _ = kind;
    "지원하지 않는 종류"
}

// ── 거절 ───────────────────────────────────────────────────────────────────

/// 관측이 세계를 확정하지 못한 이유.
///
/// 어느 것이든 **아무 Snapshot 도 논리 상태도 확정되지 않았다**는 뜻이다. 이 모듈은 아무것도
/// 쓰지 않으므로 거절 뒤에도 프로젝트는 그대로다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) enum ObserveError {
    /// 심볼릭 링크가 있다 — 따라가지도, 저장하지도, 조용히 빼지도 않는다.
    Symlink { path: EntryPath },
    /// 일반 파일도 디렉터리도 아닌 것이 있다.
    SpecialEntry {
        path: EntryPath,
        kind: &'static str,
    },
    /// 이름을 v0 Artifact 경로로 적을 수 없다 — UTF-8 이 아니거나 `\` 를 담았다.
    UnrepresentablePath {
        near: ObserveLocation,
        shown: String,
    },
    /// 프로젝트 안에서 다른 GIL 저장소를 만났다.
    NestedGilRepository { path: EntryPath },
    /// 읽지 못했다. 루트에서 실패했을 수도 있으므로 자리는 [`ObserveLocation`] 이다.
    ReadFailed {
        at: ObserveLocation,
        source: String,
    },
    /// 두 관측 사이에 세계가 바뀌었다.
    ChangedDuringObservation,
    /// 객체 창고가 답하지 못했다.
    ObjectStore(ObjectError),
}

impl fmt::Display for ObserveError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ObserveError::Symlink { path } => write!(
                f,
                "{path} 은(는) 심볼릭 링크다. GIL 은 링크를 따라가지도 저장하지도 않고, \
                 조용히 빼지도 않는다 — 그러면 그 자리가 세계에 없다는 거짓말이 된다.\n\
                 어떤 Snapshot 도 확정하지 않았다. 링크를 치우거나 실제 파일로 바꾼 뒤 \
                 다시 시도한다."
            ),
            ObserveError::SpecialEntry { path, kind } => write!(
                f,
                "{path} 은(는) {kind} 라 Artifact 로 다룰 수 없다.\n\
                 어떤 Snapshot 도 확정하지 않았다. 그 항목을 프로젝트 밖으로 옮긴 뒤 \
                 다시 시도한다."
            ),
            ObserveError::UnrepresentablePath { near, shown } => write!(
                f,
                "{near} 아래의 {shown:?} 는 UTF-8 경로로 적을 수 없다. Artifact 경로는 \
                 UTF-8 로만 기록한다.\n\
                 어떤 Snapshot 도 확정하지 않았다. 이름을 바꾼 뒤 다시 시도한다."
            ),
            ObserveError::NestedGilRepository { path } => write!(
                f,
                "현재 프로젝트 안에서 다른 GIL 저장소를 발견했다: {path}\n\n\
                 현재 버전의 GIL 은 중첩 프로젝트의 Artifact 경계를 정의하지 않았다.\n\
                 바깥 프로젝트가 안쪽 세계를 복원하면 두 프로젝트의 기록이 어긋날 수 있어\n\
                 Snapshot 을 확정하지 않았다.\n\n\
                 중첩 프로젝트를 프로젝트 밖으로 옮긴 뒤 다시 시도한다."
            ),
            ObserveError::ReadFailed { at, source } => write!(
                f,
                "{at} 을(를) 읽지 못했다 — {source}.\n\
                 어떤 Snapshot 도 확정하지 않았다. 읽을 수 있게 한 뒤 다시 시도한다."
            ),
            ObserveError::ObjectStore(source) => write!(f, "{source}"),
            ObserveError::ChangedDuringObservation => write!(
                f,
                "관측 중 Artifact 세계가 변경되었다. 서로 다른 순간의 파일을 한 세계로 \
                 섞지 않으려고 멈췄다.\n\
                 어떤 Snapshot 도 확정하지 않았다. 프로젝트를 건드리는 다른 작업이 끝난 뒤 \
                 다시 시도한다."
            ),
        }
    }
}

impl std::error::Error for ObserveError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

/// 관측기의 시험은 **모듈 안에** 산다.
///
/// 밖에서 부를 수 있는 통합 시험으로 두면 `observe` 와 두 관측 사이를 비집는 문까지 공개
/// API 가 된다. 아직 Snapshot 저장 schema 도 정하지 않은 기계를 시험 편의로 굳히지 않는다 —
/// 한 번 내보낸 이름은 되돌리기 어렵다.
#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;
    use std::io::Write;
    use std::path::PathBuf;

    // ── 두 관측 사이를 비집는 자리 ────────────────────────────────────────

    /// 두 관측 사이의 틈으로 세계를 흔든다.
    ///
    /// **제품 코드와 같은 [`observe_twice`] 를 부른다** — 복제본을 두면 한쪽만 고쳐도
    /// 다른 쪽 시험이 통과해, 정작 두 번 보는 규칙이 무너진 것을 아무도 모른다.
    fn observe_with_interlude(
        root: &Path,
        between: impl FnOnce(),
    ) -> Result<Manifest, ObserveError> {
        observe_twice(root, between)
    }

    // ── 세계를 짓는 연장 ──────────────────────────────────────────────────

    /// 시험이 쓰는 빈 자리. 들어가기 전에 지운다 — 앞 판이 이번 판의 답이 되지 않도록.
    fn scratch(label: &str) -> PathBuf {
        let dir = std::env::temp_dir().join(format!("gil-artifact-{label}"));
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("시험이 쓸 자리를 만들 수 있어야 한다");
        dir
    }

    /// 그 자리에 파일 하나. 부모 디렉터리는 알아서 만든다.
    fn write(root: &Path, path: &str, bytes: &[u8]) {
        let at = root.join(path);
        if let Some(parent) = at.parent() {
            fs::create_dir_all(parent).expect("부모 디렉터리를 만들 수 있어야 한다");
        }
        fs::write(&at, bytes).expect("파일을 쓸 수 있어야 한다");
    }

    /// 그 파일들을 담은 새 프로젝트.
    fn project(label: &str, files: &[(&str, &[u8])]) -> PathBuf {
        let root = scratch(label);
        for (path, bytes) in files {
            write(&root, path, bytes);
        }
        root
    }

    fn seen(root: &Path) -> Manifest {
        observe(root).unwrap_or_else(|err| panic!("관측이 거절됐다: {err}"))
    }

    fn refused(root: &Path) -> ObserveError {
        observe(root).expect_err("거절돼야 하는데 관측됐다")
    }

    /// manifest 를 사람이 읽는 꼴로 — 경로만, 순서 그대로.
    fn paths(manifest: &Manifest) -> Vec<String> {
        manifest.paths().map(|path| path.to_string()).collect()
    }

    // ── ① 정체성은 경로와 바이트다 ────────────────────────────────────────────

    #[test]
    fn the_same_files_make_the_same_world() {
        let one = project("art-same-a", &[("src/main.rs", b"fn main() {}"), ("README.md", b"# hi")]);
        let two = project("art-same-b", &[("src/main.rs", b"fn main() {}"), ("README.md", b"# hi")]);

        assert_eq!(seen(&one), seen(&two), "같은 파일 집합이 다른 세계가 됐다");
    }

    #[test]
    fn the_absolute_location_is_not_part_of_the_world() {
        // 프로젝트를 옮겨도 상대 경로와 바이트가 같으면 같은 세계다(§3.3).
        let here = project("art-move-here", &[("a/b/c.txt", b"same bytes")]);
        let elsewhere = project("art-move-somewhere-far-away", &[("a/b/c.txt", b"same bytes")]);

        assert_ne!(here, elsewhere, "두 프로젝트가 같은 자리에 있으면 이 시험은 뜻이 없다");
        assert_eq!(seen(&here), seen(&elsewhere), "절대 위치가 세계에 섞였다");
    }

    #[test]
    fn different_bytes_are_a_different_world() {
        let before = project("art-bytes-before", &[("f.txt", b"one")]);
        let after = project("art-bytes-after", &[("f.txt", b"two")]);
        assert_ne!(seen(&before), seen(&after));
    }

    #[test]
    fn creating_or_deleting_a_file_is_a_different_world() {
        let root = project("art-create", &[("a.txt", b"a")]);
        let one = seen(&root);

        write(&root, "b.txt", b"b");
        let two = seen(&root);
        assert_ne!(one, two, "파일을 만들었는데 같은 세계다");

        fs::remove_file(root.join("b.txt")).unwrap();
        assert_eq!(seen(&root), one, "지웠는데 처음으로 안 돌아왔다");
    }

    #[test]
    fn a_rename_is_a_different_world() {
        // 이름과 위치 변경은 **삭제 + 생성**으로 관측한다(§3.1).
        let root = project("art-rename", &[("old.txt", b"same bytes")]);
        let before = seen(&root);

        fs::rename(root.join("old.txt"), root.join("new.txt")).unwrap();
        let after = seen(&root);

        assert_ne!(before, after, "바이트가 같으면 이름이 달라도 같은 세계라고 한다");
        assert_eq!(paths(&before), ["old.txt"]);
        assert_eq!(paths(&after), ["new.txt"]);
    }

    #[test]
    fn a_move_to_another_directory_is_a_different_world() {
        let root = project("art-move-dir", &[("a/f.txt", b"same bytes")]);
        let before = seen(&root);

        fs::create_dir_all(root.join("b")).unwrap();
        fs::rename(root.join("a/f.txt"), root.join("b/f.txt")).unwrap();

        assert_ne!(before, seen(&root), "위치가 바뀌었는데 같은 세계다");
    }

    #[test]
    fn line_endings_are_bytes_not_text() {
        // GIL 은 줄바꿈을 임의로 변환하지 않는다(§3.2).
        let lf = project("art-lf", &[("f.txt", b"a\nb\n")]);
        let crlf = project("art-crlf", &[("f.txt", b"a\r\nb\r\n")]);
        assert_ne!(seen(&lf), seen(&crlf), "CRLF 와 LF 가 같은 세계가 됐다");
    }

    #[test]
    fn a_bom_is_part_of_the_bytes() {
        let without = project("art-nobom", &[("f.txt", "가나다".as_bytes())]);
        let with = project("art-bom", &[("f.txt", &[&[0xEF, 0xBB, 0xBF][..], "가나다".as_bytes()].concat())]);
        assert_ne!(seen(&without), seen(&with), "BOM 유무가 같은 세계가 됐다");
    }

    #[test]
    fn a_different_encoding_is_a_different_world() {
        let utf8 = project("art-utf8", &[("f.txt", "가".as_bytes())]);
        let utf16 = project("art-utf16", &[("f.txt", &[0x00, 0xAC][..])]);
        assert_ne!(seen(&utf8), seen(&utf16));
    }

    // ── ② 세계에 없는 것은 세계에 없다 ────────────────────────────────────────

    #[test]
    fn the_manifest_is_sorted_by_path_bytes_whatever_the_filesystem_says() {
        // 파일 시스템이 어떤 순서로 돌려주든 canonical 은 하나다(§3.3).
        //
        // 디렉터리 이름은 대소문자만 다르게 두지 않는다 — macOS·Windows 의 대소문자 무시
        // 파일 시스템에서 두 이름이 한 디렉터리로 합쳐져 시험이 재려는 것과 다른 것을 잰다.
        let names = ["z.txt", "a.txt", "M.txt", "b/a.txt", "b/Z.txt", "가.txt", "0.txt"];
        let root = scratch("art-order");
        for name in names {
            write(&root, name, b"x");
        }

        let mut expected: Vec<&str> = names.to_vec();
        expected.sort_by_key(|name| name.as_bytes());
        assert_eq!(paths(&seen(&root)), expected, "canonical 순서가 아니다");

        // 대문자가 소문자보다 먼저 온다 — locale 이 아니라 바이트 값이 순서를 정한다.
        let sorted = paths(&seen(&root));
        let big = sorted.iter().position(|name| name == "M.txt").unwrap();
        let small = sorted.iter().position(|name| name == "a.txt").unwrap();
        assert!(big < small, "바이트 순서가 아니라 locale 을 따랐다:\n{sorted:?}");
    }

    #[test]
    fn an_empty_directory_is_not_part_of_the_world() {
        let root = project("art-empty-dir", &[("f.txt", b"x")]);
        let before = seen(&root);

        fs::create_dir_all(root.join("empty/deeper")).unwrap();
        assert_eq!(seen(&root), before, "빈 디렉터리가 세계에 섞였다");

        fs::remove_dir_all(root.join("empty")).unwrap();
        assert_eq!(seen(&root), before);
    }

    #[test]
    fn mtime_alone_does_not_change_the_world() {
        let root = project("art-mtime", &[("f.txt", b"x")]);
        let before = seen(&root);

        // 같은 바이트를 다시 쓴다 — mtime 은 움직이고 내용은 그대로다.
        write(&root, "f.txt", b"x");
        assert_eq!(seen(&root), before, "mtime 이 세계에 섞였다");
    }

    #[cfg(unix)]
    #[test]
    fn permissions_alone_do_not_change_the_world() {
        use std::os::unix::fs::PermissionsExt;

        let root = project("art-perm", &[("f.txt", b"x")]);
        let before = seen(&root);

        let at = root.join("f.txt");
        fs::set_permissions(&at, fs::Permissions::from_mode(0o755)).unwrap();
        assert_eq!(
            fs::metadata(&at).unwrap().permissions().mode() & 0o777,
            0o755,
            "권한이 실제로 바뀌지 않아 이 시험은 아무것도 재지 못한다"
        );

        assert_eq!(seen(&root), before, "권한이 세계에 섞였다");
    }

    // ── ③ `.gil` — 루트 하나만 제외, 나머지는 거절 ────────────────────────────

    #[test]
    fn the_root_gil_directory_is_excluded() {
        let root = project("art-root-gil", &[("src/main.rs", b"x")]);
        write(&root, ".gil/state.yaml", b"format: 3\n");

        assert_eq!(paths(&seen(&root)), ["src/main.rs"], "루트 .gil 이 세계에 섞였다");
    }

    #[test]
    fn what_the_root_gil_directory_holds_never_changes_the_world() {
        let root = project("art-root-gil-churn", &[("src/main.rs", b"x")]);
        write(&root, ".gil/state.yaml", b"format: 3\n");
        let before = seen(&root);

        // GIL 은 명령마다 이 안을 고친다. 그것이 바깥 세계를 더럽히면 아무 Step 도 못 닫는다.
        write(&root, ".gil/state.yaml", b"format: 3\nnext_will_id: 9\n");
        write(&root, ".gil/objects/deep/thing", "내부 저장소의 무엇".as_bytes());
        fs::create_dir_all(root.join(".gil/empty")).unwrap();

        assert_eq!(seen(&root), before, "내부 저장소가 바깥 세계를 움직였다");
    }

    #[test]
    fn a_nested_gil_repository_refuses_the_whole_observation() {
        // v0 은 중첩 GIL 프로젝트를 지원하지 않는다(Artifact Model §3.4).
        let root = project("art-nested-gil", &[("src/main.rs", b"x")]);
        write(&root, "sub/.gil/state.yaml", b"format: 3\n");
        write(&root, "sub/lib.rs", b"y");

        let err = refused(&root);
        let ObserveError::NestedGilRepository { path } = &err else {
            panic!("중첩 GIL 이 다른 이유로 거절됐다: {err}");
        };
        assert_eq!(path.to_string(), "sub/.gil");

        let said = err.to_string();
        assert!(said.contains("sub/.gil"), "어디인지 안 말한다:\n{said}");
        assert!(said.contains("Snapshot"), "무엇이 확정되지 않았는지 안 말한다:\n{said}");
        assert!(said.contains("옮긴"), "무엇을 하면 되는지 안 말한다:\n{said}");
    }

    #[test]
    fn an_empty_nested_gil_directory_is_still_refused() {
        // 안이 비어 있어도 경계는 경계다 — 내용으로 판정하지 않는다.
        let root = project("art-nested-gil-empty", &[("f.txt", b"x")]);
        fs::create_dir_all(root.join("sub/.gil")).unwrap();

        assert!(
            matches!(refused(&root), ObserveError::NestedGilRepository { .. }),
            "빈 중첩 .gil 이 통과했다"
        );
    }

    #[test]
    fn a_nested_gil_directory_is_refused_without_being_read() {
        // 이름과 위치만으로 즉시 거절한다. 안을 들여다보면 읽을 수 없는 것에서 다른 오류가 난다.
        let root = project("art-nested-gil-unreadable", &[("f.txt", b"x")]);
        fs::create_dir_all(root.join("sub/.gil")).unwrap();

        // 안에 **관측이 거절할 만한 것**을 넣어 둔다. 안을 봤다면 이 쪽 오류가 나온다.
        #[cfg(unix)]
        std::os::unix::fs::symlink("../../f.txt", root.join("sub/.gil/link")).unwrap();

        let err = refused(&root);
        assert!(
            matches!(err, ObserveError::NestedGilRepository { .. }),
            "중첩 .gil 안을 들여다봤다: {err}"
        );
    }

    #[test]
    fn a_nested_gil_is_found_whatever_the_enumeration_order() {
        // 열거 순서에 따라 놓치면 어떤 프로젝트에서는 통과하고 어떤 프로젝트에서는 거절된다.
        for label in ["art-nested-first", "art-nested-last"] {
            let root = scratch(label);
            // 이름을 앞뒤로 흩어 둔다 — `.gil` 이 첫 항목이기도 마지막 항목이기도 하게.
            for name in ["000/f.txt", "aaa/f.txt", "zzz/f.txt"] {
                write(&root, name, b"x");
            }
            let at = match label {
                "art-nested-first" => "000/.gil",
                _ => "zzz/.gil",
            };
            fs::create_dir_all(root.join(at)).unwrap();

            let err = refused(&root);
            let ObserveError::NestedGilRepository { path } = &err else {
                panic!("{label}: 다른 이유로 거절됐다: {err}");
            };
            assert_eq!(path.to_string(), at);
        }
    }

    #[test]
    fn a_regular_file_named_gil_is_an_ordinary_artifact() {
        // 이번 결정은 **디렉터리**에 관한 것이다. 같은 이름의 일반 파일은 평범한 Artifact 다.
        let root = project("art-gil-file", &[("sub/.gil", "디렉터리가 아니라 파일이다".as_bytes())]);

        assert_eq!(paths(&seen(&root)), ["sub/.gil"], "일반 파일 .gil 이 거절됐다");
    }

    #[test]
    fn a_root_level_regular_file_named_gil_is_also_an_artifact() {
        let root = project("art-gil-file-root", &[(".gil", "파일이다".as_bytes())]);
        assert_eq!(paths(&seen(&root)), [".gil"]);
    }

    // ── ④ 조용히 빠지는 것이 없다 ─────────────────────────────────────────────

    #[cfg(unix)]
    #[test]
    fn a_symlink_refuses_the_whole_observation() {
        let root = project("art-symlink", &[("real.txt", b"x")]);
        std::os::unix::fs::symlink("real.txt", root.join("link.txt")).unwrap();

        let err = refused(&root);
        let ObserveError::Symlink { path } = &err else {
            panic!("심볼릭 링크가 다른 이유로 거절됐다: {err}");
        };
        assert_eq!(path.to_string(), "link.txt");
        assert!(err.to_string().contains("링크"), "{err}");
    }

    #[cfg(unix)]
    #[test]
    fn a_symlink_named_gil_is_refused_as_a_symlink() {
        // `.gil` 이라는 이름의 링크는 중첩 저장소가 아니라 **링크**로 거절한다.
        let root = project("art-gil-symlink", &[("f.txt", b"x")]);
        std::os::unix::fs::symlink("f.txt", root.join("sub_gil_link")).unwrap();
        fs::create_dir_all(root.join("sub")).unwrap();
        std::os::unix::fs::symlink("../f.txt", root.join("sub/.gil")).unwrap();
        fs::remove_file(root.join("sub_gil_link")).unwrap();

        let err = refused(&root);
        let ObserveError::Symlink { path } = &err else {
            panic!(".gil 링크가 다른 이유로 거절됐다: {err}");
        };
        assert_eq!(path.to_string(), "sub/.gil");
    }

    #[cfg(unix)]
    #[test]
    fn a_fifo_refuses_the_whole_observation() {
        let root = project("art-fifo", &[("f.txt", b"x")]);
        if !make_fifo(&root.join("pipe")) {
            eprintln!("이 플랫폼에서 FIFO 를 만들지 못했다 — 시험을 건너뛴다");
            return;
        }

        let err = refused(&root);
        let ObserveError::SpecialEntry { path, kind } = &err else {
            panic!("특수 항목이 다른 이유로 거절됐다: {err}");
        };
        assert_eq!(path.to_string(), "pipe");
        assert_eq!(*kind, "FIFO");
        assert!(err.to_string().contains("FIFO"), "종류를 안 말한다:\n{err}");
    }

    /// `mkfifo` 로 FIFO 하나. 못 만들면 `false` — 조용히 통과시키지 않고 부르는 쪽이 알린다.
    #[cfg(unix)]
    fn make_fifo(at: &Path) -> bool {
        std::process::Command::new("mkfifo")
            .arg(at)
            .status()
            .map(|status| status.success())
            .unwrap_or(false)
    }

    #[cfg(unix)]
    #[test]
    fn a_non_utf8_name_refuses_the_whole_observation() {
        use std::ffi::OsStr;
        use std::os::unix::ffi::OsStrExt;

        let root = project("art-non-utf8", &[("f.txt", b"x")]);
        // 홀로 선 0xFF 는 어떤 UTF-8 문자열의 일부도 될 수 없다.
        let bad = root.join(OsStr::from_bytes(b"bad\xFFname"));
        if fs::write(&bad, b"x").is_err() {
            eprintln!("이 파일 시스템이 비UTF-8 이름을 허락하지 않는다 — 시험을 건너뛴다");
            return;
        }

        let err = refused(&root);
        assert!(
            matches!(err, ObserveError::UnrepresentablePath { .. }),
            "비UTF-8 이름이 다른 이유로 거절됐다: {err}"
        );
        assert!(err.to_string().contains("UTF-8"), "{err}");
    }

    #[cfg(unix)]
    #[test]
    fn a_read_failure_refuses_without_a_partial_manifest() {
        use std::os::unix::fs::PermissionsExt;

        if unsafe { libc_geteuid() } == 0 {
            eprintln!("root 는 권한을 무시하므로 읽기 실패를 만들 수 없다 — 시험을 건너뛴다");
            return;
        }
        let root = project("art-unreadable", &[("a.txt", b"a"), ("locked.txt", b"secret")]);
        fs::set_permissions(root.join("locked.txt"), fs::Permissions::from_mode(0o000)).unwrap();

        let err = refused(&root);
        let ObserveError::ReadFailed { at, .. } = &err else {
            panic!("읽기 실패가 다른 이유로 거절됐다: {err}");
        };
        assert_eq!(at, &ObserveLocation::Entry(EntryPath::parse("locked.txt").unwrap()));

        // 되살릴 수 있게 돌려 둔다 — 시험이 남긴 자리가 다음 판을 막지 않게.
        fs::set_permissions(root.join("locked.txt"), fs::Permissions::from_mode(0o644)).unwrap();
    }

    #[cfg(unix)]
    unsafe extern "C" {
        #[link_name = "geteuid"]
        fn libc_geteuid() -> u32;
    }

    // ── ⑤ 두 번 본다 ──────────────────────────────────────────────────────────

    #[test]
    fn a_change_between_the_two_observations_is_refused() {
        // 잠을 재우거나 thread 를 겹치지 않는다 — 두 관측 사이의 틈에 결정적으로 끼어든다.
        let root = project("art-changed-create", &[("a.txt", b"a")]);

        let err = observe_with_interlude(&root, || write(&root, "b.txt", b"b"))
            .expect_err("관측 중 파일이 생겼는데 통과했다");
        assert_eq!(err, ObserveError::ChangedDuringObservation);
    }

    #[test]
    fn a_deletion_between_the_two_observations_is_refused() {
        let root = project("art-changed-delete", &[("a.txt", b"a"), ("b.txt", b"b")]);

        let err = observe_with_interlude(&root, || fs::remove_file(root.join("b.txt")).unwrap())
            .expect_err("관측 중 파일이 사라졌는데 통과했다");
        assert_eq!(err, ObserveError::ChangedDuringObservation);
    }

    #[test]
    fn an_edit_between_the_two_observations_is_refused() {
        let root = project("art-changed-edit", &[("a.txt", b"before")]);

        let err = observe_with_interlude(&root, || write(&root, "a.txt", b"after"))
            .expect_err("관측 중 내용이 바뀌었는데 통과했다");
        assert_eq!(err, ObserveError::ChangedDuringObservation);
    }

    #[test]
    fn a_still_world_passes_the_second_look() {
        let root = project("art-unchanged", &[("a.txt", b"a")]);
        let quiet = observe_with_interlude(&root, || {}).expect("아무것도 안 했으면 통과한다");
        assert_eq!(quiet, seen(&root));
    }

    // ── ⑥ 큰 파일을 통째로 들지 않는다 ────────────────────────────────────────

    #[test]
    fn a_large_file_is_read_in_chunks() {
        // 파일 크기만 한 버퍼를 요구하면 대용량 파일에 공개 상한이 생긴다(§3.5).
        let size = CHUNK * 5 + 7;

        struct Counting<'a> {
            left: usize,
            largest: &'a mut usize,
            reads: &'a mut usize,
        }
        impl std::io::Read for Counting<'_> {
            fn read(&mut self, buf: &mut [u8]) -> std::io::Result<usize> {
                *self.largest = (*self.largest).max(buf.len());
                *self.reads += 1;
                let give = buf.len().min(self.left);
                buf[..give].fill(b'x');
                self.left -= give;
                Ok(give)
            }
        }

        let (mut largest, mut reads) = (0, 0);
        ContentDigest::of(Counting {
            left: size,
            largest: &mut largest,
            reads: &mut reads,
        })
        .expect("흘려 읽는다");

        assert!(
            largest <= CHUNK,
            "한 번에 {largest} 바이트를 요구했다 — 조각보다 크다"
        );
        assert!(largest < size, "파일 크기만 한 버퍼를 잡았다");
        assert!(reads >= 6, "조각으로 나눠 읽지 않았다: {reads}회");
    }

    #[test]
    fn a_large_file_on_disk_is_observed() {
        let size = CHUNK * 3 + 11;
        let root = scratch("art-large");
        let at = root.join("big.bin");
        let mut file = fs::File::create(&at).unwrap();
        file.write_all(&vec![7u8; size]).unwrap();
        drop(file);

        assert_eq!(paths(&seen(&root)), ["big.bin"]);

        // 마지막 한 바이트만 달라도 다른 세계다.
        let mut bytes = vec![7u8; size];
        bytes[size - 1] = 8;
        fs::write(&at, &bytes).unwrap();
        assert_ne!(seen(&root), seen(&project("art-large-twin", &[("big.bin", &vec![7u8; size])])));
    }

    // ── ⑦ 경로 계약 ───────────────────────────────────────────────────────────

    #[test]
    fn an_entry_path_refuses_what_the_contract_forbids() {
        for bad in ["/abs/path", "", ".", "..", "a/../b", "a/./b", "a//b", "a\\b"] {
            assert!(
                EntryPath::parse(bad).is_none(),
                "{bad:?} 가 경로 계약을 통과했다"
            );
        }
        for good in ["a.txt", "src/main.rs", "가/나.txt", "A.txt"] {
            assert_eq!(
                EntryPath::parse(good).map(|path| path.to_string()).as_deref(),
                Some(good),
                "{good:?} 가 거절되거나 바뀌었다"
            );
        }
    }

    #[test]
    fn case_and_unicode_spelling_are_preserved() {
        // 대소문자 접기도, NFC/NFD 변환도 하지 않는다(§3.3).
        let composed = "\u{ac00}.txt"; // 가 — 하나의 코드포인트
        let decomposed = "\u{1100}\u{1161}.txt"; // ᄀ + ᅡ

        let root = scratch("art-unicode");
        write(&root, "Case.txt", b"x");
        write(&root, composed, b"x");

        let shown = paths(&seen(&root));
        assert!(shown.contains(&"Case.txt".to_string()), "대소문자가 접혔다:\n{shown:?}");

        // 파일 시스템이 표기를 보존하는 곳에서만 재는 것 — macOS 는 NFD 로 바꿔 저장한다.
        let stored = shown.iter().find(|name| name.ends_with(".txt") && *name != "Case.txt");
        if let Some(stored) = stored {
            assert!(
                stored == composed || stored == decomposed,
                "관측한 표기가 둘 다 아니다: {stored:?}"
            );
        }
    }

    // ── ⑧ 역슬래시는 Artifact 경로가 아니다 ───────────────────────────────

    #[test]
    fn the_parser_refuses_a_backslash_component() {
        // `/` 가 유일한 canonical 구분자다(§3.3). Windows 경로를 `\` 로 담는다는 뜻이 아니다.
        for bad in ["a\\b", "src\\main.rs", "a/b\\c", "\\", "a\\"] {
            assert!(
                EntryPath::parse(bad).is_none(),
                "{bad:?} 가 경로 계약을 통과했다"
            );
        }
    }

    #[test]
    fn the_component_validator_refuses_a_backslash_the_same_way() {
        // 파일 시스템에서 온 이름도 사람이 적은 글과 **같은 검사**를 지난다.
        assert!(EntryPath::from_components(&["a\\b".to_string()]).is_none());
        assert!(EntryPath::from_components(&["a".to_string(), "b\\c".to_string()]).is_none());
        assert!(EntryPath::from_components(&["a".to_string(), "b".to_string()]).is_some());
    }

    #[test]
    fn a_normal_slash_path_is_two_components() {
        let path = EntryPath::parse("a/b").expect("정상 경로다");
        assert_eq!(path.to_string(), "a/b");
        assert_eq!(
            EntryPath::from_components(&["a".to_string(), "b".to_string()]),
            Some(path)
        );
    }

    #[cfg(unix)]
    #[test]
    fn a_real_file_named_with_a_backslash_refuses_the_whole_observation() {
        let root = project("art-backslash", &[("ok.txt", b"x")]);
        if fs::write(root.join("a\\b"), b"x").is_err() {
            eprintln!("이 파일 시스템이 역슬래시 이름을 허락하지 않는다 — 시험을 건너뛴다");
            return;
        }

        let err = refused(&root);
        let ObserveError::UnrepresentablePath { near, shown } = &err else {
            panic!("역슬래시 이름이 다른 이유로 거절됐다: {err}");
        };
        assert_eq!(near, &ObserveLocation::Root, "부모 자리를 틀리게 말한다");
        assert!(shown.contains('\\'), "무엇이 문제인지 안 보여 준다: {shown:?}");
    }

    #[test]
    fn every_observed_path_survives_a_round_trip_through_the_parser() {
        // 관측이 만든 값을 같은 parser 가 다시 읽지 못하면 계약이 두 벌인 것이다.
        let root = project(
            "art-roundtrip",
            &[
                ("a.txt", b"x"),
                ("src/main.rs", b"x"),
                ("가/나/다.txt", b"x"),
                ("A/b/C.txt", b"x"),
                (".hidden", b"x"),
                ("space in name.txt", b"x"),
            ],
        );
        let manifest = seen(&root);
        assert!(!manifest.is_empty(), "잴 것이 없다");

        for path in manifest.paths() {
            let again = EntryPath::parse(path.as_str());
            assert_eq!(
                again.as_ref(),
                Some(path),
                "{path} 를 같은 parser 가 다시 읽지 못한다"
            );
        }
    }

    // ── ⑨ 프로젝트 루트는 파일이 아니다 ───────────────────────────────────

    #[test]
    fn the_parser_still_refuses_a_dot() {
        // 루트를 자리로 말하려고 `.` 을 허락하지 않는다 — 그것은 별도 타입이 진다.
        for bad in [".", "..", "a/.", "./a", "a/../b"] {
            assert!(EntryPath::parse(bad).is_none(), "{bad:?} 가 통과했다");
        }
    }

    #[test]
    fn a_failure_at_the_project_root_is_a_root_location() {
        // 루트에서 읽지 못하면 자리는 `EntryPath` 가 아니라 Root 다.
        let missing = scratch("art-root-gone");
        fs::remove_dir_all(&missing).unwrap();

        let err = observe(&missing).expect_err("없는 자리를 관측했다");
        let ObserveError::ReadFailed { at, .. } = &err else {
            panic!("루트 읽기 실패가 다른 이유로 거절됐다: {err}");
        };
        assert_eq!(at, &ObserveLocation::Root);
        assert!(
            err.to_string().contains("프로젝트 루트"),
            "사람이 읽을 자리를 안 말한다:\n{err}"
        );
    }

    #[test]
    fn no_entry_path_ever_spells_the_root() {
        // `EntryPath(".")` 는 만들어질 수 없다 — 생성 문 하나가 그것을 막는다.
        assert!(EntryPath::parse(".").is_none());
        assert!(EntryPath::from_components(&[".".to_string()]).is_none());
        assert!(EntryPath::from_components(&[]).is_none());

        // 그리고 Root 는 `EntryPath` 와 애초에 다른 값이다.
        let root = ObserveLocation::Root;
        assert_ne!(
            root,
            ObserveLocation::Entry(EntryPath::parse("a").unwrap())
        );
        assert_eq!(root.to_string(), "프로젝트 루트");
    }

    #[test]
    fn the_root_location_never_becomes_a_manifest_entry() {
        // 루트는 정렬 대상도 manifest 항목도 아니다.
        let root = project("art-root-not-an-entry", &[("a.txt", b"x"), ("b/c.txt", b"x")]);
        let manifest = seen(&root);

        for path in manifest.paths() {
            assert_ne!(path.as_str(), ".", "루트가 항목이 됐다");
            assert_ne!(path.as_str(), "", "빈 경로가 항목이 됐다");
        }
        assert_eq!(paths(&manifest), ["a.txt", "b/c.txt"]);
    }

    #[cfg(unix)]
    #[test]
    fn a_failure_below_the_root_keeps_its_relative_path() {
        use std::os::unix::fs::PermissionsExt;

        if unsafe { libc_geteuid() } == 0 {
            eprintln!("root 는 권한을 무시하므로 읽기 실패를 만들 수 없다 — 시험을 건너뛴다");
            return;
        }
        let root = project("art-deep-unreadable", &[("deep/locked.txt", b"secret")]);
        let at = root.join("deep/locked.txt");
        fs::set_permissions(&at, fs::Permissions::from_mode(0o000)).unwrap();

        let err = refused(&root);
        let ObserveError::ReadFailed { at: where_at, .. } = &err else {
            panic!("다른 이유로 거절됐다: {err}");
        };
        assert_eq!(
            where_at,
            &ObserveLocation::Entry(EntryPath::parse("deep/locked.txt").unwrap()),
            "하위 파일의 상대 경로를 잃었다"
        );

        fs::set_permissions(&at, fs::Permissions::from_mode(0o644)).unwrap();
    }
}
