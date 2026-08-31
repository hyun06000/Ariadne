//! Snapshot registry — **세계에 공개 이름을 준다.**
//!
//! 창고는 내용으로 주소를 정하고(`sha256:…`), registry 는 그 주소에 **프로젝트 로컬 이름**을
//! 붙인다. 사람과 Report 가 보는 것은 언제나 이름 쪽이다.
//!
//! ```text
//! SnapshotRef → manifest 주소    여기
//! manifest    → blob 목록        store
//! blob        → 바이트           store
//! ```
//!
//! # 이름은 세계의 정체성이지 사건의 이름이 아니다
//!
//! Artifact Model §13 — 같은 세계가 다시 나타나면 **기존 이름을 다시 가리킨다.**
//!
//! ```text
//! A1  manifest ①
//! A2  manifest ②
//! A1  manifest ①   ← 새 A3 을 만들지 않는다
//! ```
//!
//! 이것은 사건을 잃는 것이 아니다. **어느 시점에 누가 A1 을 다시 가리켰는지는 Graph 와
//! Journey 가 기록한다.** registry 는 사건 시간선을 담지 않는다 — 담으면 같은 사실이 두
//! 자리에 살고, 한쪽이 낡는다.
//!
//! # 아직 저장되지 않는다
//!
//! 이 타입은 메모리 안에서만 산다. `state.yaml` 을 읽지도 쓰지도 않는다 — format 4 는
//! Cycle 의 entry/exit 필드와 **함께** 나와야 하기 때문이다(§10.5의 구현 순서).

use std::fmt;

use super::{ContentDigest, DigestAlgorithm};
use crate::refs::SnapshotRef;

/// 처음 발급될 이름. `A0` 은 없다.
const FIRST_SNAPSHOT: u32 = 1;

/// SHA-256 의 길이 — 주소가 이 길이가 아니면 주소가 아니다.
const DIGEST_BYTES: usize = 32;

/// **manifest 객체의 주소.** blob 주소가 이 자리에 올 수 없다.
///
/// 종류를 타입으로 지닌다 — [`ContentDigest`] 는 무엇의 지문인지 모르므로, 그것을 그대로
/// registry 에 넣으면 blob 주소를 세계의 주소로 적는 실수가 컴파일을 통과한다.
#[derive(Clone, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct ManifestAddress(ContentDigest);

impl ManifestAddress {
    /// 창고가 manifest 를 확정하며 돌려준 지문을 주소로 삼는다.
    ///
    /// `store` 안에서만 부른다 — 그 자리에서만 이 지문이 manifest 의 것임을 안다.
    pub(super) fn of_manifest(digest: ContentDigest) -> ManifestAddress {
        ManifestAddress(digest)
    }

    /// 저장에서 읽어 온 값으로 주소를 되세운다 — **알고리즘과 길이를 검사하며.**
    ///
    /// format 4 가 붙으면 이 문이 그 입구가 된다. 지금은 시험만 지난다.
    pub fn from_parts(algorithm: &str, bytes: &[u8]) -> Result<ManifestAddress, RegistryError> {
        if algorithm != DigestAlgorithm::Sha256.as_str() {
            return Err(RegistryError::UnknownDigestAlgorithm {
                found: algorithm.to_string(),
            });
        }
        let raw: [u8; DIGEST_BYTES] =
            bytes
                .try_into()
                .map_err(|_| RegistryError::BadDigestLength {
                    found: bytes.len(),
                    wanted: DIGEST_BYTES,
                })?;
        Ok(ManifestAddress(ContentDigest::from_raw(
            DigestAlgorithm::Sha256,
            raw,
        )))
    }

    pub(crate) fn algorithm(&self) -> DigestAlgorithm {
        self.0.algorithm()
    }

    /// 저장이 적는 알고리즘 이름 — `sha256`.
    pub fn algorithm_name(&self) -> &'static str {
        self.0.algorithm().as_str()
    }

    /// 저장에 적는 소문자 canonical 16진수.
    ///
    /// **사람에게 보이는 세계의 이름이 아니다.** 공개 표면은 `snapshot:A1` 하나이고,
    /// 이 값은 receipt 에 기본으로 실리지 않는다(Artifact Model §13·§15).
    pub fn hex(&self) -> String {
        self.0.hex()
    }

    pub(super) fn digest(&self) -> &ContentDigest {
        &self.0
    }
}

impl fmt::Debug for ManifestAddress {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "manifest({:?})", self.0)
    }
}

/// 이름 하나와 그것이 가리키는 세계.
///
/// **확정된 뒤에는 고치지도 지우지도 않는다.** 이름이 다른 세계를 가리키게 되면, 그 이름을
/// 적어 둔 모든 Node 의 뜻이 소급해 바뀐다.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SnapshotRecord {
    id: SnapshotRef,
    manifest: ManifestAddress,
}

impl SnapshotRecord {
    pub(crate) fn id(&self) -> SnapshotRef {
        self.id
    }

    pub(crate) fn manifest(&self) -> &ManifestAddress {
        &self.manifest
    }
}

/// 이 프로젝트가 이름 붙인 세계들.
#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct SnapshotRegistry {
    /// 다음에 발급될 이름의 수. **마지막으로 발급한 것 다음**이다.
    next_id: u32,
    /// 이름 오름차순. 빈틈이 없다.
    records: Vec<SnapshotRecord>,
}

impl SnapshotRegistry {
    /// 아직 아무 세계에도 이름을 주지 않은 registry.
    pub(crate) fn new() -> SnapshotRegistry {
        SnapshotRegistry {
            next_id: FIRST_SNAPSHOT,
            records: Vec::new(),
        }
    }

    pub(crate) fn next_id(&self) -> u32 {
        self.next_id
    }

    pub(crate) fn records(&self) -> &[SnapshotRecord] {
        &self.records
    }

    pub(crate) fn is_empty(&self) -> bool {
        self.records.is_empty()
    }

    /// 그 이름이 가리키는 세계. 모르는 이름이면 `None`.
    pub(crate) fn resolve(&self, id: SnapshotRef) -> Option<&ManifestAddress> {
        self.records
            .iter()
            .find(|record| record.id == id)
            .map(|record| &record.manifest)
    }

    /// 그 세계에 이미 붙은 이름. 없으면 `None`.
    pub(crate) fn find_by_manifest(&self, manifest: &ManifestAddress) -> Option<SnapshotRef> {
        self.records
            .iter()
            .find(|record| &record.manifest == manifest)
            .map(|record| record.id)
    }

    /// 그 세계의 이름을 얻는다 — **없으면 새로 발급하고, 있으면 그것을 준다.**
    ///
    /// ```text
    /// 이미 아는 세계   기존 이름 · next_id 불변 · records 불변
    /// 처음 보는 세계   새 이름 발급 · record append · next_id 증가
    /// ```
    ///
    /// 같은 세계에 두 이름을 주지 않는다. 그것이 §13의 「이름이 같으면 세계가 같다」의
    /// 반쪽이다 — 나머지 반쪽은 이름이 다르면 세계도 다르다는 것이고, 그것은 아래의
    /// 「이미 쓴 이름을 다시 발급하지 않는다」가 지킨다.
    pub(crate) fn intern(
        &mut self,
        manifest: ManifestAddress,
    ) -> Result<SnapshotRef, RegistryError> {
        if let Some(known) = self.find_by_manifest(&manifest) {
            return Ok(known);
        }
        // **감싸 돌지 않는다.** 이름이 되돌아가면 옛 이름이 새 세계를 가리키게 된다.
        let id = SnapshotRef::new(self.next_id).ok_or(RegistryError::Exhausted)?;
        let next = self.next_id.checked_add(1).ok_or(RegistryError::Exhausted)?;

        self.records.push(SnapshotRecord { id, manifest });
        self.next_id = next;
        Ok(id)
    }

    /// 저장이 읽어 온 값으로 다시 세운다 — **구조적 정합성만 잰다.**
    ///
    /// manifest 객체가 실제로 창고에 있는지, 그 내용이 주소와 맞는지는 **여기서 보지
    /// 않는다.** 그것은 저장 계층과 결합하는 다음 조각의 몫이다. 여기서 I/O 를 하면
    /// registry 하나를 세우는 데 디스크가 필요해지고, 그러면 시험도 복원도 무거워진다.
    pub(crate) fn restore(
        next_id: u32,
        records: Vec<(u32, ManifestAddress)>,
    ) -> Result<SnapshotRegistry, RegistryError> {
        let mut seen: Vec<SnapshotRecord> = Vec::with_capacity(records.len());

        for (position, (raw, manifest)) in records.into_iter().enumerate() {
            // `A0` 은 없다 — 이름은 1 부터 센다(Node Model §2.1).
            let id = SnapshotRef::new(raw).ok_or(RegistryError::ZeroId)?;

            // **빈틈 없는 오름차순.** 이름은 record 를 붙일 때만 발급되므로, 걸어서 만든
            // registry 에는 빈틈이 생길 수 없다 — `next_will_id` 와 같은 규칙이다.
            let expected = FIRST_SNAPSHOT
                .checked_add(position as u32)
                .ok_or(RegistryError::Exhausted)?;
            if raw != expected {
                return Err(match seen.iter().any(|record| record.id == id) {
                    true => RegistryError::DuplicateId { id },
                    false => RegistryError::NotContiguous { found: id, expected },
                });
            }
            // 서로 다른 이름이 같은 세계를 가리킬 수 없다.
            if let Some(other) = seen.iter().find(|record| record.manifest == manifest) {
                return Err(RegistryError::DuplicateManifest {
                    first: other.id,
                    second: id,
                });
            }
            seen.push(SnapshotRecord { id, manifest });
        }

        // `next_id` 는 마지막으로 발급한 것 다음이다.
        let wanted = FIRST_SNAPSHOT
            .checked_add(seen.len() as u32)
            .ok_or(RegistryError::Exhausted)?;
        if next_id != wanted {
            return Err(RegistryError::WrongNextId {
                found: next_id,
                wanted,
            });
        }
        Ok(SnapshotRegistry {
            next_id,
            records: seen,
        })
    }
}

/// registry 가 거절한 이유.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum RegistryError {
    /// 발급할 이름이 남지 않았다. **감싸 돌지 않는다.**
    Exhausted,
    /// `A0` 은 이름이 아니다.
    ZeroId,
    /// 같은 이름이 두 번 실렸다.
    DuplicateId { id: SnapshotRef },
    /// 서로 다른 이름이 같은 세계를 가리킨다.
    DuplicateManifest {
        first: SnapshotRef,
        second: SnapshotRef,
    },
    /// 이름이 오름차순이 아니거나 빈틈이 있다.
    NotContiguous { found: SnapshotRef, expected: u32 },
    /// `next_id` 가 마지막으로 발급한 것 다음이 아니다.
    WrongNextId { found: u32, wanted: u32 },
    /// 이 gil 이 모르는 digest 알고리즘이다.
    UnknownDigestAlgorithm { found: String },
    /// 주소의 길이가 그 알고리즘의 것이 아니다.
    BadDigestLength { found: usize, wanted: usize },
}

impl fmt::Display for RegistryError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            RegistryError::Exhausted => write!(
                f,
                "Snapshot 이름을 더 발급할 수 없다 — 이름은 감싸 돌지 않는다. \
                 감싸 돌면 옛 이름이 새 세계를 가리키게 된다"
            ),
            RegistryError::ZeroId => write!(
                f,
                "snapshot:A0 은 이름이 아니다 — Snapshot 이름은 A1 부터 센다"
            ),
            RegistryError::DuplicateId { id } => {
                write!(f, "{id} 이(가) 두 번 실렸다 — 한 이름은 한 세계만 가리킨다")
            }
            RegistryError::DuplicateManifest { first, second } => write!(
                f,
                "{first} 와(과) {second} 가 같은 세계를 가리킨다 — 같은 세계에는 이름이 \
                 하나여야 「이름이 같으면 세계가 같다」가 성립한다"
            ),
            RegistryError::NotContiguous { found, expected } => write!(
                f,
                "{found} 이(가) 있어야 할 자리에 A{expected} 이(가) 와야 한다 — \
                 이름은 record 를 붙일 때만 발급되므로 빈틈이 생길 수 없다"
            ),
            RegistryError::WrongNextId { found, wanted } => write!(
                f,
                "next_id 가 {found} 인데 마지막으로 발급한 것 다음은 {wanted} 다"
            ),
            RegistryError::UnknownDigestAlgorithm { found } => write!(
                f,
                "manifest 주소의 digest 알고리즘 {found:?} 을(를) 이 gil 이 모른다 \
                 (아는 것: {})",
                DigestAlgorithm::Sha256.as_str()
            ),
            RegistryError::BadDigestLength { found, wanted } => write!(
                f,
                "manifest 주소가 {found} 바이트인데 {wanted} 바이트여야 한다"
            ),
        }
    }
}

impl std::error::Error for RegistryError {}

// ── 시험 ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    /// 서로 다른 세계의 주소 — 내용은 지어내되 **길이와 알고리즘은 진짜다.**
    fn address(seed: u8) -> ManifestAddress {
        ManifestAddress::of_manifest(ContentDigest::from_raw(
            DigestAlgorithm::Sha256,
            [seed; DIGEST_BYTES],
        ))
    }

    fn name(number: u32) -> SnapshotRef {
        SnapshotRef::new(number).expect("시험이 쓰는 이름은 1 부터다")
    }

    fn pairs(registry: &SnapshotRegistry) -> Vec<(u32, ManifestAddress)> {
        registry
            .records()
            .iter()
            .map(|record| (record.id().number(), record.manifest().clone()))
            .collect()
    }

    // ── 발급 ──────────────────────────────────────────────────────────────

    #[test]
    fn a_new_registry_has_named_no_world() {
        let registry = SnapshotRegistry::new();
        assert!(registry.is_empty());
        assert_eq!(registry.next_id(), FIRST_SNAPSHOT);
        assert_eq!(registry.records(), &[]);
    }

    #[test]
    fn the_first_world_is_named_a1() {
        let mut registry = SnapshotRegistry::new();
        let id = registry.intern(address(1)).unwrap();

        assert_eq!(id, name(1));
        assert_eq!(id.to_string(), "snapshot:A1");
        assert_eq!(registry.next_id(), 2, "발급하고도 다음 이름이 그대로다");
    }

    #[test]
    fn a_new_world_gets_the_next_name() {
        let mut registry = SnapshotRegistry::new();
        assert_eq!(registry.intern(address(1)).unwrap(), name(1));
        assert_eq!(registry.intern(address(2)).unwrap(), name(2));
        assert_eq!(registry.intern(address(3)).unwrap(), name(3));
        assert_eq!(registry.next_id(), 4);
        assert_eq!(registry.records().len(), 3);
    }

    #[test]
    fn the_same_world_reuses_its_name() {
        // Artifact Model §13 — 이름은 사건이 아니라 세계의 정체성이다.
        let mut registry = SnapshotRegistry::new();
        let first = registry.intern(address(9)).unwrap();
        let before = registry.clone();

        let again = registry.intern(address(9)).unwrap();
        assert_eq!(again, first, "같은 세계가 두 이름을 얻었다");
        assert_eq!(registry, before, "이름을 다시 준 것뿐인데 registry 가 움직였다");
    }

    #[test]
    fn returning_to_an_older_world_does_not_mint_a_new_name() {
        // A → B → A. 되돌아온 세계는 이미 이름이 있다.
        let mut registry = SnapshotRegistry::new();
        let a = registry.intern(address(1)).unwrap();
        let b = registry.intern(address(2)).unwrap();
        let back = registry.intern(address(1)).unwrap();

        assert_eq!(back, a);
        assert_ne!(a, b);
        assert_eq!(registry.next_id(), 3, "되돌아온 것만으로 이름이 늘었다");
        assert_eq!(registry.records().len(), 2);
    }

    #[test]
    fn a_name_resolves_to_its_world() {
        let mut registry = SnapshotRegistry::new();
        let a = registry.intern(address(1)).unwrap();
        let b = registry.intern(address(2)).unwrap();

        assert_eq!(registry.resolve(a), Some(&address(1)));
        assert_eq!(registry.resolve(b), Some(&address(2)));
        assert_eq!(registry.resolve(name(3)), None, "모르는 이름이 답을 얻었다");
    }

    #[test]
    fn a_world_finds_the_name_it_already_has() {
        let mut registry = SnapshotRegistry::new();
        let a = registry.intern(address(1)).unwrap();

        assert_eq!(registry.find_by_manifest(&address(1)), Some(a));
        assert_eq!(registry.find_by_manifest(&address(7)), None);
    }

    #[test]
    fn names_are_never_reissued() {
        // 지운 자리를 다시 쓰지 않는다 — 여기서는 지울 길 자체가 없다.
        let mut registry = SnapshotRegistry::new();
        let mut given = Vec::new();
        for seed in 1..=5u8 {
            given.push(registry.intern(address(seed)).unwrap());
        }
        let mut unique = given.clone();
        unique.sort_by_key(|id: &SnapshotRef| id.number());
        unique.dedup();
        assert_eq!(unique.len(), given.len(), "같은 이름이 두 번 발급됐다");
        assert_eq!(registry.next_id(), 6);
    }

    #[test]
    fn records_stay_in_ascending_order() {
        let mut registry = SnapshotRegistry::new();
        for seed in 1..=4u8 {
            registry.intern(address(seed)).unwrap();
        }
        let numbers: Vec<u32> = registry.records().iter().map(|r| r.id().number()).collect();
        assert_eq!(numbers, vec![1, 2, 3, 4]);
    }

    #[test]
    fn names_run_out_rather_than_wrapping() {
        // **감싸 돌면 옛 이름이 새 세계를 가리킨다.** 그래서 멈춘다.
        let mut registry = SnapshotRegistry {
            next_id: u32::MAX,
            records: Vec::new(),
        };
        let before = registry.clone();

        let err = registry.intern(address(1)).expect_err("이름이 감싸 돌았다");
        assert_eq!(err, RegistryError::Exhausted);
        assert_eq!(registry, before, "거절하고도 registry 가 움직였다");
    }

    // ── 복원 ──────────────────────────────────────────────────────────────

    #[test]
    fn a_registry_restores_to_exactly_what_it_was() {
        let mut registry = SnapshotRegistry::new();
        for seed in 1..=3u8 {
            registry.intern(address(seed)).unwrap();
        }
        let again = SnapshotRegistry::restore(registry.next_id(), pairs(&registry)).unwrap();
        assert_eq!(again, registry);

        // 빈 registry 도 마찬가지다.
        let empty = SnapshotRegistry::restore(FIRST_SNAPSHOT, Vec::new()).unwrap();
        assert_eq!(empty, SnapshotRegistry::new());
    }

    #[test]
    fn restore_refuses_the_name_a0() {
        let err = SnapshotRegistry::restore(2, vec![(0, address(1))]).expect_err("A0 이 실렸다");
        assert_eq!(err, RegistryError::ZeroId);
    }

    #[test]
    fn restore_refuses_a_repeated_name() {
        // 같은 이름이 두 번 — 두 번째가 어느 세계를 가리키든 이름 하나에 세계 하나다.
        let err = SnapshotRegistry::restore(3, vec![(1, address(1)), (1, address(2))])
            .expect_err("같은 이름이 두 번 실렸다");
        assert_eq!(err, RegistryError::DuplicateId { id: name(1) });
    }

    #[test]
    fn restore_refuses_two_names_for_one_world() {
        let err = SnapshotRegistry::restore(3, vec![(1, address(5)), (2, address(5))])
            .expect_err("한 세계가 두 이름을 가졌다");
        assert_eq!(
            err,
            RegistryError::DuplicateManifest {
                first: name(1),
                second: name(2),
            }
        );
    }

    #[test]
    fn restore_refuses_records_out_of_order() {
        let err = SnapshotRegistry::restore(3, vec![(2, address(1)), (1, address(2))])
            .expect_err("차례가 뒤집힌 채 실렸다");
        assert_eq!(
            err,
            RegistryError::NotContiguous {
                found: name(2),
                expected: 1,
            }
        );
    }

    #[test]
    fn restore_refuses_a_gap() {
        // 이름은 record 를 붙일 때만 발급되므로 빈틈이 생길 길이 없다.
        let err = SnapshotRegistry::restore(4, vec![(1, address(1)), (3, address(2))])
            .expect_err("빈틈이 통과했다");
        assert_eq!(
            err,
            RegistryError::NotContiguous {
                found: name(3),
                expected: 2,
            }
        );
    }

    #[test]
    fn restore_refuses_a_next_id_that_does_not_follow() {
        // 너무 작으면 — 다음 발급이 이미 쓴 이름을 다시 낸다.
        let err = SnapshotRegistry::restore(2, vec![(1, address(1)), (2, address(2))])
            .expect_err("다음 이름이 이미 쓴 이름이다");
        assert_eq!(err, RegistryError::WrongNextId { found: 2, wanted: 3 });

        // 너무 커도 — 아무도 발급하지 않은 이름을 건너뛴 것이다.
        let err = SnapshotRegistry::restore(9, vec![(1, address(1))]).expect_err("빈틈이 생겼다");
        assert_eq!(err, RegistryError::WrongNextId { found: 9, wanted: 2 });

        // 빈 registry 의 next_id 는 언제나 1 이다.
        let err = SnapshotRegistry::restore(0, Vec::new()).expect_err("A0 을 다음으로 삼았다");
        assert_eq!(err, RegistryError::WrongNextId { found: 0, wanted: 1 });
    }

    #[test]
    fn a_restored_registry_keeps_issuing_where_it_left_off() {
        let mut registry =
            SnapshotRegistry::restore(3, vec![(1, address(1)), (2, address(2))]).unwrap();

        assert_eq!(registry.intern(address(2)).unwrap(), name(2), "아는 세계다");
        assert_eq!(registry.intern(address(3)).unwrap(), name(3), "처음 보는 세계다");
        assert_eq!(registry.next_id(), 4);
    }

    // ── 주소 ──────────────────────────────────────────────────────────────

    #[test]
    fn an_address_refuses_an_algorithm_this_gil_does_not_know() {
        let err = ManifestAddress::from_parts("blake3", &[0u8; DIGEST_BYTES])
            .expect_err("모르는 알고리즘이 통과했다");
        assert_eq!(
            err,
            RegistryError::UnknownDigestAlgorithm {
                found: "blake3".to_string(),
            }
        );
    }

    #[test]
    fn an_address_refuses_the_wrong_number_of_bytes() {
        for length in [0usize, 31, 33, 64] {
            let err = ManifestAddress::from_parts("sha256", &vec![0u8; length])
                .expect_err("길이가 틀린 주소가 통과했다");
            assert_eq!(
                err,
                RegistryError::BadDigestLength {
                    found: length,
                    wanted: DIGEST_BYTES,
                }
            );
        }
    }

    #[test]
    fn an_address_that_parses_is_the_address_it_came_from() {
        let raw = [0x2bu8; DIGEST_BYTES];
        let parsed = ManifestAddress::from_parts("sha256", &raw).unwrap();

        assert_eq!(parsed, address(0x2b));
        assert_eq!(parsed.algorithm(), DigestAlgorithm::Sha256);
        assert_eq!(parsed.hex(), "2b".repeat(DIGEST_BYTES));
    }
}
