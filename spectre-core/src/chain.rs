//! Pointer-chain walking on top of [`MemoryReader`].
//!
//! Two entry points:
//!
//! - [`follow`] walks a known chain `base + [offsets]` with exactly the
//!   semantics of [`MemoryReader::resolve_ptr_chain`], but records every step.
//! - [`follow_until_end`] explores an unknown chain by dereferencing raw
//!   pointers (no offsets) until NULL, a cycle, unreadable memory or a depth
//!   limit, and reports *why* it stopped.

use std::collections::HashSet;
use std::fmt;

use anyhow::{Result, anyhow};
use serde::{Deserialize, Serialize};
use tracing::debug;

use crate::reader::MemoryReader;

/// Result of walking a pointer chain.
#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct PointerChain {
    /// Start address of the walk.
    pub base: u64,
    /// Offsets of the chain. For [`follow`] these are the requested offsets;
    /// for [`follow_until_end`] one `0` per successful read, so that
    /// `follow(base, &offsets)` replays the same walk.
    pub offsets: Vec<u64>,
    /// Every successful 8-byte read, in walk order.
    pub steps: Vec<ChainStep>,
    /// Final address of the chain, or `None` if the walk did not get there
    /// (see [`follow`] / [`follow_until_end`] for the exact rules).
    pub resolved: Option<u64>,
    /// Why the walk stopped.
    pub stop: ChainStop,
}

/// One dereference in a chain: `*(pointer + offset) == value`.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct ChainStep {
    /// Pointer the offset was added to (the base, or the previous `value`).
    pub pointer: u64,
    /// Offset added before reading.
    pub offset: u64,
    /// `pointer + offset`: where the u64 was read.
    pub address: u64,
    /// The u64 stored at `address`.
    pub value: u64,
}

/// Why a chain walk stopped.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(tag = "reason", rename_all = "snake_case")]
pub enum ChainStop {
    /// [`follow`] only: every offset was applied.
    Complete,
    /// A dereferenced pointer that would have been followed was 0.
    Null,
    /// [`follow_until_end`] only: `max_depth` reads were made.
    MaxDepth,
    /// Reading 8 bytes at `address` failed.
    Unreadable { address: u64 },
    /// [`follow_until_end`] only: the next pointer `address` was already read.
    Cycle { address: u64 },
}

impl fmt::Display for ChainStop {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            ChainStop::Complete => write!(f, "complete (all offsets applied)"),
            ChainStop::Null => write!(f, "null pointer"),
            ChainStop::MaxDepth => write!(f, "max depth reached"),
            ChainStop::Unreadable { address } => write!(f, "unreadable memory at {address:#x}"),
            ChainStop::Cycle { address } => write!(f, "cycle ({address:#x} already visited)"),
        }
    }
}

/// Walk `base + offsets` and record every step.
///
/// Semantics are those of [`MemoryReader::resolve_ptr_chain`]: each offset is
/// added *before* its dereference, the base itself is never dereferenced, and
/// the last address is read (it must be readable) but not followed — it is
/// the result:
///
/// ```text
/// follow(base, [o0, o1, o2]):
///
///   base --+o0--> a0 --*--> p1 --+o1--> a1 --*--> p2 --+o2--> a2 = resolved
///                 read                  read                  read, not followed
/// ```
///
/// `steps[i]` is `{ pointer, offset: o_i, address: a_i, value: *a_i }`, so the
/// value stored at the resolved address is `steps.last().value`. With empty
/// `offsets` nothing is read and `resolved == Some(base)`.
///
/// Where `resolve_ptr_chain` returns `Err` on a failed read, `follow` returns
/// `Ok` with [`ChainStop::Unreadable`] and `resolved == None`. One deliberate
/// difference: a NULL intermediate pointer stops the walk with
/// [`ChainStop::Null`] instead of reading near address 0. Otherwise
/// `resolved` equals `resolve_ptr_chain(...)`. Address overflow
/// (`pointer + offset > u64::MAX`) is an `Err`, as in `resolve_ptr_chain`.
pub fn follow(
    reader: &dyn MemoryReader,
    pid: u32,
    base: u64,
    offsets: &[u64],
    little: bool,
) -> Result<PointerChain> {
    let mut chain = PointerChain {
        base,
        offsets: offsets.to_vec(),
        steps: Vec::with_capacity(offsets.len()),
        resolved: None,
        stop: ChainStop::Complete,
    };
    let Some(last) = offsets.len().checked_sub(1) else {
        chain.resolved = Some(base);
        return Ok(chain);
    };

    let mut pointer = base;
    for (i, &offset) in offsets.iter().enumerate() {
        let address = pointer
            .checked_add(offset)
            .ok_or_else(|| anyhow!("pointer overflow: {pointer:#x} + {offset:#x}"))?;
        let value = match reader.read_u64(pid, address, little) {
            Ok(v) => v,
            Err(e) => {
                debug!("chain step {i}: read at {address:#x} failed: {e:#}");
                chain.stop = ChainStop::Unreadable { address };
                return Ok(chain);
            }
        };
        chain.steps.push(ChainStep {
            pointer,
            offset,
            address,
            value,
        });
        if i == last {
            chain.resolved = Some(address);
            break;
        }
        if value == 0 {
            chain.stop = ChainStop::Null;
            return Ok(chain);
        }
        pointer = value;
    }
    Ok(chain)
}

/// Dereference raw pointers starting at `start` until the chain ends.
///
/// Reads the u64 at `start`, jumps to it, and repeats (offset 0 each time):
///
/// ```text
/// start --*--> p1 --*--> p2 --*--> ... --*--> 0      (stop: Null)
///                                         \--> pK    (pK already read: Cycle)
/// ```
///
/// The walk stops, in this order of checks, when
/// - the next pointer was already read ([`ChainStop::Cycle`], no extra read),
/// - `max_depth` reads were made ([`ChainStop::MaxDepth`]),
/// - the read fails ([`ChainStop::Unreadable`]),
/// - the value read is 0 ([`ChainStop::Null`], that step is recorded).
///
/// `resolved` is the last address that was read successfully — the deepest
/// link of the chain — or `None` if nothing could be read (including
/// `max_depth == 0`). `offsets` holds one `0` per step, so when at least one
/// read succeeded `follow(start, &offsets)` resolves to the same address.
pub fn follow_until_end(
    reader: &dyn MemoryReader,
    pid: u32,
    start: u64,
    max_depth: u32,
    little: bool,
) -> Result<PointerChain> {
    let mut chain = PointerChain {
        base: start,
        offsets: Vec::new(),
        steps: Vec::new(),
        resolved: None,
        stop: ChainStop::MaxDepth,
    };
    let mut visited = HashSet::new();
    let mut address = start;

    loop {
        if visited.contains(&address) {
            chain.stop = ChainStop::Cycle { address };
            break;
        }
        if chain.steps.len() >= max_depth as usize {
            chain.stop = ChainStop::MaxDepth;
            break;
        }
        let value = match reader.read_u64(pid, address, little) {
            Ok(v) => v,
            Err(e) => {
                debug!("chain: read at {address:#x} failed: {e:#}");
                chain.stop = ChainStop::Unreadable { address };
                break;
            }
        };
        visited.insert(address);
        chain.steps.push(ChainStep {
            pointer: address,
            offset: 0,
            address,
            value,
        });
        chain.offsets.push(0);
        if value == 0 {
            chain.stop = ChainStop::Null;
            break;
        }
        address = value;
    }

    chain.resolved = chain.steps.last().map(|s| s.address);
    Ok(chain)
}
