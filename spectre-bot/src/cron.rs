/// Cron-style schedules for bot tasks.
///
/// A schedule is a classic five-field cron expression:
///
/// ```text
/// ┌───────── minute   (0-59)
/// │ ┌─────── hour     (0-23)
/// │ │ ┌───── day      (1-31, day of month)
/// │ │ │ ┌─── month    (1-12)
/// │ │ │ │ ┌─ weekday  (0-6, 0 = Sunday; 7 is accepted as Sunday too)
/// │ │ │ │ │
/// * * * * *
/// ```
///
/// Each field accepts:
/// - `*` — any value,
/// - `5` — a single value,
/// - `a-b` — an inclusive range,
/// - `*/n` and `a-b/n` — every n-th value of the full range / of `a-b`,
/// - `a,b,c` — a comma-separated list of any of the above.
///
/// Fields are expanded into the full set of allowed values at parse time,
/// so `*/15` in the minute field matches minutes 0, 15, 30 and 45. A field
/// whose expansion covers its entire range (e.g. `*/1` or `0-59`) is
/// normalised to [`CronField::Any`].
///
/// # Day / weekday semantics
/// Like standard (Vixie/POSIX) cron, when **both** the day-of-month and the
/// weekday field are restricted (i.e. not [`CronField::Any`]), a date
/// matches if **either** of them matches (`0 9 1 * 1` = 09:00 on the 1st of
/// each month *and* every Monday). When only one of them is restricted, only
/// that one is checked.
///
/// Not supported: month/weekday names (`JAN`, `MON`), `@daily`-style
/// macros, `L`/`W`/`#` extensions, and a seconds field.
use std::fmt;
use std::str::FromStr;

use anyhow::{Context, anyhow, bail};
use chrono::{DateTime, Datelike, Local, NaiveDateTime, TimeZone, Timelike};

// ── Field ───────────────────────────────────────────────────────────────────

/// Matcher for a single cron field.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum CronField {
    /// Matches every value of the field's range (`*`).
    Any,
    /// Matches exactly these values (sorted ascending, deduplicated).
    Values(Vec<u32>),
}

impl CronField {
    /// Returns `true` when `value` is accepted by this field.
    pub fn contains(&self, value: u32) -> bool {
        match self {
            CronField::Any => true,
            CronField::Values(values) => values.binary_search(&value).is_ok(),
        }
    }

    /// Returns `true` for [`CronField::Any`].
    pub fn is_any(&self) -> bool {
        matches!(self, CronField::Any)
    }
}

/// Static description of one of the five fields (name and inclusive range).
struct FieldSpec {
    name: &'static str,
    min: u32,
    max: u32,
}

const MINUTE: FieldSpec = FieldSpec {
    name: "minute",
    min: 0,
    max: 59,
};
const HOUR: FieldSpec = FieldSpec {
    name: "hour",
    min: 0,
    max: 23,
};
const DAY: FieldSpec = FieldSpec {
    name: "day",
    min: 1,
    max: 31,
};
const MONTH: FieldSpec = FieldSpec {
    name: "month",
    min: 1,
    max: 12,
};
/// Weekday accepts 0-7 on input; 7 is folded into 0 (Sunday).
const WEEKDAY: FieldSpec = FieldSpec {
    name: "weekday",
    min: 0,
    max: 7,
};

fn parse_number(text: &str, spec: &FieldSpec) -> anyhow::Result<u32> {
    let value: u32 = text
        .parse()
        .map_err(|_| anyhow!("{}: '{}' is not a number", spec.name, text))?;
    if value < spec.min || value > spec.max {
        bail!(
            "{}: value {} out of range {}-{}",
            spec.name,
            value,
            spec.min,
            spec.max
        );
    }
    Ok(value)
}

/// Parse one comma-separated field into a matcher.
fn parse_field(text: &str, spec: &FieldSpec) -> anyhow::Result<CronField> {
    let mut values: Vec<u32> = Vec::new();

    for item in text.split(',') {
        if item.is_empty() {
            bail!("{}: empty list element in '{}'", spec.name, text);
        }

        let (range, step) = match item.split_once('/') {
            Some((range, step)) => {
                let step: u32 = step
                    .parse()
                    .map_err(|_| anyhow!("{}: invalid step '{}' in '{}'", spec.name, step, item))?;
                if step == 0 {
                    bail!("{}: step must be at least 1 in '{}'", spec.name, item);
                }
                (range, Some(step))
            }
            None => (item, None),
        };

        let (start, end) = if range == "*" {
            (spec.min, spec.max)
        } else if let Some((a, b)) = range.split_once('-') {
            let a = parse_number(a, spec)?;
            let b = parse_number(b, spec)?;
            if a > b {
                bail!("{}: range start {} is after end {}", spec.name, a, b);
            }
            (a, b)
        } else {
            if let Some(step) = step {
                bail!(
                    "{}: step requires '*' or a range (e.g. '*/{step}' or 'a-b/{step}'), got '{}'",
                    spec.name,
                    item
                );
            }
            let v = parse_number(range, spec)?;
            (v, v)
        };

        let step = step.unwrap_or(1) as usize;
        values.extend((start..=end).step_by(step));
    }

    // Weekday 7 is an alias for Sunday (0).
    if spec.name == WEEKDAY.name {
        for v in &mut values {
            if *v == 7 {
                *v = 0;
            }
        }
    }

    values.sort_unstable();
    values.dedup();

    // Normalise full coverage to `Any` (weekday: 0-6 after folding 7).
    let effective_max = if spec.name == WEEKDAY.name {
        6
    } else {
        spec.max
    };
    let full = (effective_max - spec.min + 1) as usize;
    if values.len() == full {
        return Ok(CronField::Any);
    }
    Ok(CronField::Values(values))
}

// ── Schedule ────────────────────────────────────────────────────────────────

/// A parsed five-field cron expression. See the module docs for syntax.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CronSchedule {
    pub minute: CronField,
    pub hour: CronField,
    pub day: CronField,
    pub month: CronField,
    /// 0 = Sunday … 6 = Saturday.
    pub weekday: CronField,
    /// The original expression (kept for logs / `Display`).
    source: String,
}

impl CronSchedule {
    /// Returns `true` when the wall-clock minute of `time` matches.
    ///
    /// Seconds are ignored. The time zone of `time` is used as-is, so pass
    /// a `DateTime<Local>` for local-time schedules (see [`matches`]).
    pub fn matches<Tz: TimeZone>(&self, time: &DateTime<Tz>) -> bool {
        self.matches_naive(&time.naive_local())
    }

    /// Like [`CronSchedule::matches`] for a naive (zone-less) date/time.
    pub fn matches_naive(&self, time: &NaiveDateTime) -> bool {
        if !self.minute.contains(time.minute())
            || !self.hour.contains(time.hour())
            || !self.month.contains(time.month())
        {
            return false;
        }

        let day_ok = self.day.contains(time.day());
        let weekday_ok = self.weekday.contains(time.weekday().num_days_from_sunday());

        // Standard cron: if both day fields are restricted, either may match.
        if !self.day.is_any() && !self.weekday.is_any() {
            day_ok || weekday_ok
        } else {
            day_ok && weekday_ok
        }
    }

    /// The expression this schedule was parsed from.
    pub fn source(&self) -> &str {
        &self.source
    }
}

impl FromStr for CronSchedule {
    type Err = anyhow::Error;

    fn from_str(expr: &str) -> anyhow::Result<CronSchedule> {
        parse_cron(expr)
    }
}

impl fmt::Display for CronSchedule {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(&self.source)
    }
}

/// Parse a five-field cron expression (`minute hour day month weekday`).
pub fn parse_cron(expr: &str) -> anyhow::Result<CronSchedule> {
    let fields: Vec<&str> = expr.split_whitespace().collect();
    if fields.len() != 5 {
        bail!(
            "invalid cron expression '{}': expected 5 fields (minute hour day month weekday), got {}",
            expr,
            fields.len()
        );
    }
    let ctx = || format!("invalid cron expression '{}'", expr);

    Ok(CronSchedule {
        minute: parse_field(fields[0], &MINUTE).with_context(ctx)?,
        hour: parse_field(fields[1], &HOUR).with_context(ctx)?,
        day: parse_field(fields[2], &DAY).with_context(ctx)?,
        month: parse_field(fields[3], &MONTH).with_context(ctx)?,
        weekday: parse_field(fields[4], &WEEKDAY).with_context(ctx)?,
        source: fields.join(" "),
    })
}

/// Returns `true` when `schedule` matches the local wall-clock minute `now`.
pub fn matches(schedule: &CronSchedule, now: DateTime<Local>) -> bool {
    schedule.matches(&now)
}

// ── Trigger ─────────────────────────────────────────────────────────────────

/// Edge detector that fires a [`CronSchedule`] at most once per matching
/// minute, independent of how often it is polled.
#[derive(Debug, Clone)]
pub struct CronTrigger {
    schedule: CronSchedule,
    /// Local wall-clock minute (seconds truncated) of the last firing.
    last_fired: Option<NaiveDateTime>,
}

impl CronTrigger {
    pub fn new(schedule: CronSchedule) -> CronTrigger {
        CronTrigger {
            schedule,
            last_fired: None,
        }
    }

    pub fn schedule(&self) -> &CronSchedule {
        &self.schedule
    }

    /// Returns `true` (and records the minute) if `now` lies in a matching
    /// minute that has not fired yet. Subsequent polls within the same
    /// minute return `false`.
    pub fn should_fire<Tz: TimeZone>(&mut self, now: &DateTime<Tz>) -> bool {
        let naive = now.naive_local();
        let minute = naive
            .with_second(0)
            .and_then(|t| t.with_nanosecond(0))
            .unwrap_or(naive);

        if self.last_fired == Some(minute) || !self.schedule.matches_naive(&minute) {
            return false;
        }
        self.last_fired = Some(minute);
        true
    }
}

// ── Tests ───────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use chrono::{NaiveDate, Utc};

    /// Build a naive date/time; 2026-10-26 is a Monday.
    fn at(y: i32, mo: u32, d: u32, h: u32, mi: u32) -> NaiveDateTime {
        NaiveDate::from_ymd_opt(y, mo, d)
            .unwrap()
            .and_hms_opt(h, mi, 0)
            .unwrap()
    }

    fn vals(v: &[u32]) -> CronField {
        CronField::Values(v.to_vec())
    }

    #[test]
    fn parse_any_and_single_values() {
        let s = parse_cron("* * * * *").unwrap();
        assert!(s.minute.is_any() && s.hour.is_any() && s.day.is_any());
        assert!(s.month.is_any() && s.weekday.is_any());

        let s = parse_cron("5 4 3 2 1").unwrap();
        assert_eq!(s.minute, vals(&[5]));
        assert_eq!(s.hour, vals(&[4]));
        assert_eq!(s.day, vals(&[3]));
        assert_eq!(s.month, vals(&[2]));
        assert_eq!(s.weekday, vals(&[1]));
    }

    #[test]
    fn parse_steps_ranges_lists() {
        let s = parse_cron("*/15 0-23/6 1,15,31 3-5 1-5").unwrap();
        assert_eq!(s.minute, vals(&[0, 15, 30, 45]));
        assert_eq!(s.hour, vals(&[0, 6, 12, 18]));
        assert_eq!(s.day, vals(&[1, 15, 31]));
        assert_eq!(s.month, vals(&[3, 4, 5]));
        assert_eq!(s.weekday, vals(&[1, 2, 3, 4, 5]));

        // Mixed list with duplicates is sorted and deduplicated.
        let s = parse_cron("30,0-10/5,5 * * * *").unwrap();
        assert_eq!(s.minute, vals(&[0, 5, 10, 30]));

        // Full coverage normalises to Any.
        assert!(parse_cron("*/1 0-23 * * 0-6").unwrap().minute.is_any());
        assert!(parse_cron("* 0-23 * * *").unwrap().hour.is_any());
        assert!(parse_cron("* * * * 1-7").unwrap().weekday.is_any());
    }

    #[test]
    fn parse_weekday_seven_is_sunday() {
        let s = parse_cron("0 0 * * 7").unwrap();
        assert_eq!(s.weekday, vals(&[0]));
        let s = parse_cron("0 0 * * 0,7").unwrap();
        assert_eq!(s.weekday, vals(&[0]));
        let s = parse_cron("0 0 * * 5-7").unwrap();
        assert_eq!(s.weekday, vals(&[0, 5, 6]));
    }

    #[test]
    fn parse_tolerates_extra_whitespace() {
        let s = parse_cron("  */5\t*  * *   * ").unwrap();
        assert_eq!(s.source(), "*/5 * * * *");
        assert_eq!(s.to_string(), "*/5 * * * *");
        assert_eq!(
            "0 * * * *".parse::<CronSchedule>().unwrap().minute,
            vals(&[0])
        );
    }

    #[test]
    fn parse_rejects_wrong_field_count() {
        for expr in ["", "* * * *", "* * * * * *", "0 0"] {
            let err = parse_cron(expr).unwrap_err().to_string();
            assert!(err.contains("expected 5 fields"), "{expr:?}: {err}");
        }
    }

    #[test]
    fn parse_rejects_out_of_range() {
        for expr in [
            "60 * * * *",
            "* 24 * * *",
            "* * 0 * *",
            "* * 32 * *",
            "* * * 0 *",
            "* * * 13 *",
            "* * * * 8",
            "0-60 * * * *",
            "1,99 * * * *",
        ] {
            let err = format!("{:#}", parse_cron(expr).unwrap_err());
            assert!(err.contains("out of range"), "{expr:?}: {err}");
        }
    }

    #[test]
    fn parse_rejects_bad_steps_and_syntax() {
        for expr in [
            "*/0 * * * *",
            "*/x * * * *",
            "*/ * * * *",
            "*/-1 * * * *",
            "5/10 * * * *",
            "10-5 * * * *",
            "1,,2 * * * *",
            "a * * * *",
            "-5 * * * *",
            "1-2-3 * * * *",
        ] {
            assert!(parse_cron(expr).is_err(), "{expr:?} should be rejected");
        }
        let err = format!("{:#}", parse_cron("*/0 * * * *").unwrap_err());
        assert!(err.contains("minute") && err.contains("step"), "{err}");
    }

    #[test]
    fn matches_every_fifteen_minutes() {
        let s = parse_cron("*/15 * * * *").unwrap();
        for m in [0, 15, 30, 45] {
            assert!(s.matches_naive(&at(2026, 10, 26, 13, m)), "minute {m}");
        }
        for m in [1, 14, 16, 44, 59] {
            assert!(!s.matches_naive(&at(2026, 10, 26, 13, m)), "minute {m}");
        }
    }

    #[test]
    fn matches_every_six_hours() {
        let s = parse_cron("0 */6 * * *").unwrap();
        for h in [0, 6, 12, 18] {
            assert!(s.matches_naive(&at(2026, 10, 26, h, 0)), "hour {h}");
            assert!(!s.matches_naive(&at(2026, 10, 26, h, 1)), "hour {h}:01");
        }
        for h in [1, 5, 7, 23] {
            assert!(!s.matches_naive(&at(2026, 10, 26, h, 0)), "hour {h}");
        }
    }

    #[test]
    fn matches_lists_and_ranges() {
        let s = parse_cron("0,30 9-17 * * *").unwrap();
        assert!(s.matches_naive(&at(2026, 10, 26, 9, 0)));
        assert!(s.matches_naive(&at(2026, 10, 26, 17, 30)));
        assert!(!s.matches_naive(&at(2026, 10, 26, 8, 30)));
        assert!(!s.matches_naive(&at(2026, 10, 26, 18, 0)));
        assert!(!s.matches_naive(&at(2026, 10, 26, 12, 15)));

        let s = parse_cron("0 12 * 6-8 *").unwrap();
        assert!(s.matches_naive(&at(2026, 7, 4, 12, 0)));
        assert!(!s.matches_naive(&at(2026, 10, 4, 12, 0)));
    }

    #[test]
    fn matches_weekday_including_seven() {
        // 2026-11-01 is a Sunday, 2026-10-31 a Saturday.
        let s = parse_cron("0 8 * * 7").unwrap();
        assert!(s.matches_naive(&at(2026, 11, 1, 8, 0)));
        assert!(!s.matches_naive(&at(2026, 10, 31, 8, 0)));

        let weekdays = parse_cron("0 8 * * 1-5").unwrap();
        assert!(weekdays.matches_naive(&at(2026, 10, 26, 8, 0))); // Monday
        assert!(weekdays.matches_naive(&at(2026, 10, 30, 8, 0))); // Friday
        assert!(!weekdays.matches_naive(&at(2026, 10, 31, 8, 0))); // Saturday
    }

    #[test]
    fn day_and_weekday_use_or_semantics_when_both_restricted() {
        // 1st of the month OR Monday.
        let s = parse_cron("0 9 1 * 1").unwrap();
        assert!(s.matches_naive(&at(2026, 10, 1, 9, 0))); // Thursday the 1st
        assert!(s.matches_naive(&at(2026, 10, 26, 9, 0))); // Monday the 26th
        assert!(!s.matches_naive(&at(2026, 10, 27, 9, 0))); // Tuesday the 27th

        // Only day restricted -> weekday ignored.
        let s = parse_cron("0 9 1 * *").unwrap();
        assert!(s.matches_naive(&at(2026, 10, 1, 9, 0)));
        assert!(!s.matches_naive(&at(2026, 10, 26, 9, 0)));

        // Only weekday restricted -> day ignored.
        let s = parse_cron("0 9 * * 1").unwrap();
        assert!(!s.matches_naive(&at(2026, 10, 1, 9, 0)));
        assert!(s.matches_naive(&at(2026, 10, 26, 9, 0)));
    }

    #[test]
    fn matches_with_time_zone_aware_inputs() {
        let s = parse_cron("30 14 * * *").unwrap();
        let utc = Utc.from_utc_datetime(&at(2026, 10, 26, 14, 30));
        assert!(s.matches(&utc));
        let local = Local::now();
        // The free function agrees with the method for local time.
        assert_eq!(matches(&s, local), s.matches(&local));
    }

    #[test]
    fn trigger_fires_once_per_matching_minute() {
        let mut trig = CronTrigger::new(parse_cron("*/15 * * * *").unwrap());
        let base = at(2026, 10, 26, 10, 0);
        let utc = |offset_secs: i64| {
            Utc.from_utc_datetime(&(base + chrono::Duration::seconds(offset_secs)))
        };

        // Poll every 250 ms across the whole 10:00 minute: exactly one fire.
        let fires = (0..240)
            .filter(|i| {
                trig.should_fire(
                    &utc(0)
                        .checked_add_signed(chrono::Duration::milliseconds(i * 250))
                        .unwrap(),
                )
            })
            .count();
        assert_eq!(fires, 1);

        // Non-matching minutes never fire.
        assert!(!trig.should_fire(&utc(60)));
        assert!(!trig.should_fire(&utc(14 * 60 + 59)));

        // Next matching minute fires again, once.
        assert!(trig.should_fire(&utc(15 * 60 + 3)));
        assert!(!trig.should_fire(&utc(15 * 60 + 40)));

        // A coarse poll (every 60 s, landing mid-minute) still fires each slot.
        let mut trig = CronTrigger::new(parse_cron("*/15 * * * *").unwrap());
        let fires = (0..120)
            .filter(|i| trig.should_fire(&utc(i * 60 + 59)))
            .count();
        assert_eq!(fires, 8); // 120 minutes / 15
    }
}
