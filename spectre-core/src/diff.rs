//! Offline byte-level diff of two raw memory dumps.
//!
//! This is the "diff method" of offset discovery: dump the same memory range
//! twice (e.g. before and after spending gold) and look at which bytes changed.

use serde::Serialize;

/// Maximum number of *unchanged* bytes between two changed bytes that still
/// lets them belong to the same [`ChangedRegion`].
pub const DEFAULT_MERGE_GAP: usize = 16;

/// Result of comparing two dumps.
#[derive(Debug, Clone, Default, PartialEq, Eq, Serialize)]
pub struct DumpDiff {
    /// Changed regions, sorted by offset and non-overlapping.
    pub changed: Vec<ChangedRegion>,
}

/// One contiguous span that differs between the two dumps.
///
/// `old_bytes` / `new_bytes` cover the *full* span starting at `offset`,
/// including unchanged gap bytes that were merged into the region. When the
/// dumps differ in length, the side that ends early contributes fewer (possibly
/// zero) bytes.
#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub struct ChangedRegion {
    /// Byte offset of the region from the start of the dump.
    pub offset: usize,
    pub old_bytes: Vec<u8>,
    pub new_bytes: Vec<u8>,
}

impl ChangedRegion {
    /// Length of the region (the longer of the two sides).
    pub fn len(&self) -> usize {
        self.old_bytes.len().max(self.new_bytes.len())
    }

    /// Always `false` for regions produced by [`diff_dumps`].
    pub fn is_empty(&self) -> bool {
        self.len() == 0
    }

    /// Number of bytes that actually differ in this region (excluding merged
    /// unchanged gap bytes; bytes present on only one side count as changed).
    pub fn changed_bytes(&self) -> usize {
        let differing = self
            .old_bytes
            .iter()
            .zip(&self.new_bytes)
            .filter(|(a, b)| a != b)
            .count();
        differing + self.old_bytes.len().abs_diff(self.new_bytes.len())
    }
}

impl DumpDiff {
    /// Number of changed regions.
    pub fn changed_count(&self) -> usize {
        self.changed.len()
    }

    /// The changed regions, sorted by offset.
    pub fn regions(&self) -> &[ChangedRegion] {
        &self.changed
    }

    /// Total number of differing bytes across all regions.
    pub fn changed_bytes(&self) -> usize {
        self.changed.iter().map(ChangedRegion::changed_bytes).sum()
    }

    /// `true` when the dumps are identical.
    pub fn is_empty(&self) -> bool {
        self.changed.is_empty()
    }
}

/// Diff two dumps, merging changes separated by at most
/// [`DEFAULT_MERGE_GAP`] unchanged bytes.
pub fn diff_dumps(old: &[u8], new: &[u8]) -> DumpDiff {
    diff_dumps_with_gap(old, new, DEFAULT_MERGE_GAP)
}

/// Diff two dumps, merging changes separated by at most `max_gap` unchanged
/// bytes into one region. If the lengths differ, the tail beyond the shorter
/// dump is treated as changed (and merged with a preceding region when it is
/// within `max_gap`).
pub fn diff_dumps_with_gap(old: &[u8], new: &[u8], max_gap: usize) -> DumpDiff {
    let common = old.len().min(new.len());
    let total = old.len().max(new.len());

    // Half-open [start, end) spans of changed bytes.
    let mut spans: Vec<(usize, usize)> = Vec::new();
    let mut push = |start: usize, end: usize| match spans.last_mut() {
        Some(last) if start - last.1 <= max_gap => last.1 = end,
        _ => spans.push((start, end)),
    };

    for (i, (a, b)) in old[..common].iter().zip(&new[..common]).enumerate() {
        if a != b {
            push(i, i + 1);
        }
    }
    if total > common {
        push(common, total);
    }

    let slice = |data: &[u8], start: usize, end: usize| -> Vec<u8> {
        let len = data.len();
        data[start.min(len)..end.min(len)].to_vec()
    };
    let changed = spans
        .into_iter()
        .map(|(start, end)| ChangedRegion {
            offset: start,
            old_bytes: slice(old, start, end),
            new_bytes: slice(new, start, end),
        })
        .collect();
    DumpDiff { changed }
}
