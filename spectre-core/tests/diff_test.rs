//! Tests for the offline dump diff (`diff_dumps`).

use spectre_core::{ChangedRegion, DEFAULT_MERGE_GAP, diff_dumps, diff_dumps_with_gap};

fn buf(len: usize) -> Vec<u8> {
    (0..len).map(|i| i as u8).collect()
}

#[test]
fn identical_dumps_have_no_regions() {
    let a = buf(256);
    let d = diff_dumps(&a, &a);
    assert_eq!(d.changed_count(), 0);
    assert!(d.regions().is_empty());
    assert!(d.is_empty());
    assert_eq!(d.changed_bytes(), 0);
}

#[test]
fn empty_dumps_have_no_regions() {
    assert!(diff_dumps(&[], &[]).is_empty());
}

#[test]
fn single_byte_change() {
    let old = buf(64);
    let mut new = old.clone();
    new[42] = 0xFF;
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 1);
    assert_eq!(
        d.regions()[0],
        ChangedRegion {
            offset: 42,
            old_bytes: vec![42],
            new_bytes: vec![0xFF],
        }
    );
    assert_eq!(d.changed_bytes(), 1);
}

#[test]
fn adjacent_bytes_form_one_region() {
    let old = buf(64);
    let mut new = old.clone();
    new[10..14].copy_from_slice(&0xDEADBEEFu32.to_le_bytes());
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 1);
    let r = &d.regions()[0];
    assert_eq!(r.offset, 10);
    assert_eq!(r.old_bytes, vec![10, 11, 12, 13]);
    assert_eq!(r.new_bytes, 0xDEADBEEFu32.to_le_bytes().to_vec());
    assert_eq!(r.len(), 4);
}

#[test]
fn near_changes_merge_and_include_gap_bytes() {
    let old = buf(64);
    let mut new = old.clone();
    new[4] = 0xAA;
    new[8] = 0xBB;
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 1);
    let r = &d.regions()[0];
    assert_eq!(r.offset, 4);
    // Full contiguous span 4..=8, unchanged bytes 5..8 included.
    assert_eq!(r.old_bytes, vec![4, 5, 6, 7, 8]);
    assert_eq!(r.new_bytes, vec![0xAA, 5, 6, 7, 0xBB]);
    assert_eq!(r.changed_bytes(), 2);
}

#[test]
fn far_apart_changes_form_two_regions() {
    let old = vec![0u8; 4096];
    let mut new = old.clone();
    new[100] = 1;
    new[3000] = 2;
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 2);
    assert_eq!(d.regions()[0].offset, 100);
    assert_eq!(d.regions()[0].new_bytes, vec![1]);
    assert_eq!(d.regions()[1].offset, 3000);
    assert_eq!(d.regions()[1].new_bytes, vec![2]);
}

#[test]
fn gap_of_exactly_max_merges() {
    let old = vec![0u8; 128];
    let mut new = old.clone();
    // Unchanged bytes between: 11..=26 = 16 bytes.
    new[10] = 1;
    new[10 + DEFAULT_MERGE_GAP + 1] = 1;
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 1);
    assert_eq!(d.regions()[0].offset, 10);
    assert_eq!(d.regions()[0].len(), DEFAULT_MERGE_GAP + 2);
}

#[test]
fn gap_of_max_plus_one_splits() {
    let old = vec![0u8; 128];
    let mut new = old.clone();
    // Unchanged bytes between: 17.
    new[10] = 1;
    new[10 + DEFAULT_MERGE_GAP + 2] = 1;
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 2);
    assert_eq!(d.regions()[0].offset, 10);
    assert_eq!(d.regions()[1].offset, 10 + DEFAULT_MERGE_GAP + 2);
}

#[test]
fn custom_gap_zero_only_merges_touching_bytes() {
    let old = vec![0u8; 16];
    let mut new = old.clone();
    new[2] = 1;
    new[3] = 1;
    new[5] = 1;
    let d = diff_dumps_with_gap(&old, &new, 0);
    assert_eq!(d.changed_count(), 2);
    assert_eq!(d.regions()[0].offset, 2);
    assert_eq!(d.regions()[0].len(), 2);
    assert_eq!(d.regions()[1].offset, 5);
}

#[test]
fn longer_new_dump_tail_is_one_region() {
    let old = buf(32);
    let mut new = buf(32);
    new.extend_from_slice(&[0xEE; 8]);
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 1);
    let last = d.regions().last().unwrap();
    assert_eq!(last.offset, 32);
    assert!(last.old_bytes.is_empty());
    assert_eq!(last.new_bytes, vec![0xEE; 8]);
    assert_eq!(d.changed_bytes(), 8);
}

#[test]
fn shorter_new_dump_tail_is_one_region() {
    let old = buf(40);
    let new = buf(32);
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 1);
    let last = d.regions().last().unwrap();
    assert_eq!(last.offset, 32);
    assert_eq!(last.old_bytes, (32u8..40).collect::<Vec<_>>());
    assert!(last.new_bytes.is_empty());
}

#[test]
fn tail_merges_with_nearby_change() {
    let old = buf(32);
    let mut new = buf(36);
    new[30] = 0xFF;
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 1);
    let r = &d.regions()[0];
    assert_eq!(r.offset, 30);
    assert_eq!(r.old_bytes, vec![30, 31]);
    assert_eq!(r.new_bytes, vec![0xFF, 31, 32, 33, 34, 35]);
    assert_eq!(r.changed_bytes(), 1 + 4);
}

#[test]
fn tail_far_from_last_change_is_separate_region() {
    let old = vec![0u8; 100];
    let mut new = vec![0u8; 110];
    new[5] = 1;
    let d = diff_dumps(&old, &new);
    assert_eq!(d.changed_count(), 2);
    assert_eq!(d.regions()[0].offset, 5);
    assert_eq!(d.regions()[1].offset, 100);
    assert_eq!(d.regions()[1].new_bytes.len(), 10);
}

#[test]
fn diff_against_empty_dump_is_whole_tail() {
    let new = buf(20);
    let d = diff_dumps(&[], &new);
    assert_eq!(d.changed_count(), 1);
    assert_eq!(d.regions()[0].offset, 0);
    assert_eq!(d.regions()[0].new_bytes, new);
}
