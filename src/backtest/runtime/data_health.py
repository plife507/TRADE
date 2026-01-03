"""
Data health check for backtest preflight.

Validates data coverage and quality before running a backtest:
- Coverage: earliest/latest timestamps cover required window
- Gap detection: find missing candles within the window
- Sanity checks: OHLC consistency, no NaN values

This module is called during Phase -1 preflight gate.
If gaps are detected, heal_database is invoked before simulation starts.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .timeframe import tf_duration

# Funding happens every 8 hours, so allow this tolerance for coverage checks
FUNDING_INTERVAL_TOLERANCE = timedelta(hours=8)


@dataclass
class GapRange:
    """A range of missing data."""
    start: datetime
    end: datetime
    tf: str
    series: str  # "ohlcv", "funding", "oi"
    missing_count: int  # Estimated missing bars
    
    def to_dict(self) -> dict:
        return {
            "start": self.start.isoformat(),
            "end": self.end.isoformat(),
            "tf": self.tf,
            "series": self.series,
            "missing_count": self.missing_count,
        }


@dataclass
class CoverageInfo:
    """Coverage information for a single series/TF."""
    series: str
    tf: str
    earliest: datetime | None
    latest: datetime | None
    bar_count: int
    covers_start: bool  # earliest <= load_start
    covers_end: bool    # latest >= load_end
    
    def to_dict(self) -> dict:
        return {
            "series": self.series,
            "tf": self.tf,
            "earliest": self.earliest.isoformat() if self.earliest else None,
            "latest": self.latest.isoformat() if self.latest else None,
            "bar_count": self.bar_count,
            "covers_start": self.covers_start,
            "covers_end": self.covers_end,
        }


@dataclass
class SanityIssue:
    """A data sanity issue."""
    timestamp: datetime
    series: str
    tf: str
    issue_type: str  # "high_lt_low", "ohlc_range", "nan_value", "negative_volume"
    detail: str
    
    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "series": self.series,
            "tf": self.tf,
            "issue_type": self.issue_type,
            "detail": self.detail,
        }


@dataclass
class DataHealthReport:
    """Complete data health report."""

    # Request parameters
    load_start: datetime
    load_end: datetime
    required_tfs: list[str]
    required_series: list[str]
    symbol: str

    # Results
    passed: bool = False

    # Coverage results
    coverage: dict[str, CoverageInfo] = field(default_factory=dict)
    coverage_issues: list[str] = field(default_factory=list)

    # Gap results
    gaps: list[GapRange] = field(default_factory=list)
    total_missing_bars: int = 0

    # Sanity results
    sanity_issues: list[SanityIssue] = field(default_factory=list)

    # Healing info
    heal_required: bool = False
    heal_ranges: list[GapRange] = field(default_factory=list)
    
    def to_dict(self) -> dict:
        return {
            "load_start": self.load_start.isoformat(),
            "load_end": self.load_end.isoformat(),
            "required_tfs": self.required_tfs,
            "required_series": self.required_series,
            "symbol": self.symbol,
            "passed": self.passed,
            "coverage": {k: v.to_dict() for k, v in self.coverage.items()},
            "coverage_issues": self.coverage_issues,
            "gaps": [g.to_dict() for g in self.gaps],
            "total_missing_bars": self.total_missing_bars,
            "sanity_issues": [s.to_dict() for s in self.sanity_issues],
            "heal_required": self.heal_required,
            "heal_ranges": [r.to_dict() for r in self.heal_ranges],
        }


class DataHealthCheck:
    """
    Validates data health for a backtest run.
    
    Checks coverage, gaps, and sanity for required TFs/series.
    Returns a DataHealthReport with issues and heal ranges.
    """
    
    def __init__(
        self,
        load_start: datetime,
        load_end: datetime,
        required_tfs: list[str],
        symbol: str,
        required_series: list[str] | None = None,
    ):
        """
        Initialize health check.
        
        Args:
            load_start: Start of required data window
            load_end: End of required data window
            required_tfs: List of required timeframes
            symbol: Trading symbol
            required_series: Required data series (default: ohlcv, funding)
        """
        self.load_start = load_start
        self.load_end = load_end
        self.required_tfs = required_tfs
        self.symbol = symbol
        self.required_series = required_series or ["ohlcv", "funding"]
    
    def check_coverage(
        self,
        timestamps_by_tf: dict[str, list[datetime]],
        series: str = "ohlcv",
    ) -> tuple[dict[str, CoverageInfo], list[str]]:
        """
        Check data coverage for each required TF.
        
        Args:
            timestamps_by_tf: Dict of tf -> list of timestamps in data
            series: Series name for reporting
            
        Returns:
            Tuple of (coverage_dict, issues_list)
            
        Note:
            Funding data uses 8-hour tolerance since funding only occurs
            at fixed 8-hour intervals (00:00, 08:00, 16:00 UTC).
        """
        coverage = {}
        issues = []
        
        # Funding gets tolerance since it only happens every 8 hours
        tolerance = FUNDING_INTERVAL_TOLERANCE if series == "funding" else timedelta(0)
        
        for tf in self.required_tfs:
            timestamps = timestamps_by_tf.get(tf, [])
            
            if not timestamps:
                info = CoverageInfo(
                    series=series,
                    tf=tf,
                    earliest=None,
                    latest=None,
                    bar_count=0,
                    covers_start=False,
                    covers_end=False,
                )
                issues.append(f"No data for {series}/{tf}")
            else:
                sorted_ts = sorted(timestamps)
                earliest = sorted_ts[0]
                latest = sorted_ts[-1]
                
                # Apply tolerance for funding data
                covers_start = earliest <= self.load_start + tolerance
                covers_end = latest >= self.load_end - tolerance
                
                info = CoverageInfo(
                    series=series,
                    tf=tf,
                    earliest=earliest,
                    latest=latest,
                    bar_count=len(timestamps),
                    covers_start=covers_start,
                    covers_end=covers_end,
                )
                
                if not covers_start:
                    issues.append(
                        f"{series}/{tf} starts at {earliest}, "
                        f"need {self.load_start} (tolerance: {tolerance})"
                    )
                if not covers_end:
                    issues.append(
                        f"{series}/{tf} ends at {latest}, "
                        f"need {self.load_end} (tolerance: {tolerance})"
                    )
            
            coverage[f"{series}/{tf}"] = info
        
        return coverage, issues
    
    def detect_gaps(
        self,
        timestamps_by_tf: dict[str, list[datetime]],
        series: str = "ohlcv",
    ) -> list[GapRange]:
        """
        Detect gaps in data within [load_start, load_end].
        
        Args:
            timestamps_by_tf: Dict of tf -> list of timestamps
            series: Series name
            
        Returns:
            List of GapRange objects
        """
        gaps = []
        
        for tf in self.required_tfs:
            timestamps = timestamps_by_tf.get(tf, [])
            if not timestamps:
                # Entire range is a gap
                td = tf_duration(tf)
                expected_bars = int((self.load_end - self.load_start) / td)
                gaps.append(GapRange(
                    start=self.load_start,
                    end=self.load_end,
                    tf=tf,
                    series=series,
                    missing_count=expected_bars,
                ))
                continue
            
            # Sort and filter to window
            sorted_ts = sorted(timestamps)
            td = tf_duration(tf)
            
            # Filter to relevant window
            relevant_ts = [
                ts for ts in sorted_ts
                if self.load_start <= ts <= self.load_end
            ]
            
            if not relevant_ts:
                expected_bars = int((self.load_end - self.load_start) / td)
                gaps.append(GapRange(
                    start=self.load_start,
                    end=self.load_end,
                    tf=tf,
                    series=series,
                    missing_count=expected_bars,
                ))
                continue
            
            # Check gap at start
            if relevant_ts[0] > self.load_start:
                gap_start = self.load_start
                gap_end = relevant_ts[0]
                missing = int((gap_end - gap_start) / td)
                if missing > 0:
                    gaps.append(GapRange(
                        start=gap_start,
                        end=gap_end,
                        tf=tf,
                        series=series,
                        missing_count=missing,
                    ))
            
            # Check gaps between consecutive bars
            for i in range(len(relevant_ts) - 1):
                expected_next = relevant_ts[i] + td
                actual_next = relevant_ts[i + 1]
                
                if actual_next > expected_next:
                    gap_duration = actual_next - expected_next
                    missing = int(gap_duration / td)
                    if missing > 0:
                        gaps.append(GapRange(
                            start=expected_next,
                            end=actual_next,
                            tf=tf,
                            series=series,
                            missing_count=missing,
                        ))
            
            # Check gap at end
            if relevant_ts[-1] < self.load_end:
                gap_start = relevant_ts[-1] + td
                gap_end = self.load_end
                missing = int((gap_end - gap_start) / td)
                if missing > 0:
                    gaps.append(GapRange(
                        start=gap_start,
                        end=gap_end,
                        tf=tf,
                        series=series,
                        missing_count=missing,
                    ))
        
        return gaps
    
    def check_sanity(
        self,
        data_rows: list[dict],
        series: str = "ohlcv",
        tf: str = "",
    ) -> list[SanityIssue]:
        """
        Check data sanity (OHLC consistency, no NaNs, etc.).
        
        Args:
            data_rows: List of data dicts with OHLCV keys
            series: Series name
            tf: Timeframe
            
        Returns:
            List of SanityIssue objects
        """
        issues = []
        
        for row in data_rows:
            ts = row.get("timestamp")
            if ts is None:
                continue
            
            # OHLC sanity
            o = row.get("open")
            h = row.get("high")
            l = row.get("low")  # noqa: E741
            c = row.get("close")
            v = row.get("volume")
            
            # Check for NaN/None
            for field, val in [("open", o), ("high", h), ("low", l), ("close", c)]:
                if val is None or (isinstance(val, float) and val != val):  # NaN check
                    issues.append(SanityIssue(
                        timestamp=ts,
                        series=series,
                        tf=tf,
                        issue_type="nan_value",
                        detail=f"{field} is NaN/None",
                    ))
            
            # Skip further checks if we have NaN
            if None in (o, h, l, c):
                continue
            
            # High >= Low
            if h < l:
                issues.append(SanityIssue(
                    timestamp=ts,
                    series=series,
                    tf=tf,
                    issue_type="high_lt_low",
                    detail=f"high ({h}) < low ({l})",
                ))
            
            # OHLC range consistency
            if h < max(o, c) or l > min(o, c):
                issues.append(SanityIssue(
                    timestamp=ts,
                    series=series,
                    tf=tf,
                    issue_type="ohlc_range",
                    detail=f"OHLC out of range: O={o}, H={h}, L={l}, C={c}",
                ))
            
            # Volume non-negative
            if v is not None and v < 0:
                issues.append(SanityIssue(
                    timestamp=ts,
                    series=series,
                    tf=tf,
                    issue_type="negative_volume",
                    detail=f"volume ({v}) < 0",
                ))
        
        return issues
    
    def run(
        self,
        timestamps_by_series_tf: dict[str, dict[str, list[datetime]]],
        data_rows_by_tf: dict[str, list[dict]] | None = None,
    ) -> DataHealthReport:
        """
        Run full health check and return report.
        
        Args:
            timestamps_by_series_tf: Dict of series -> tf -> timestamps
            data_rows_by_tf: Optional dict of tf -> data rows for sanity check
            
        Returns:
            DataHealthReport with all results
        """
        report = DataHealthReport(
            load_start=self.load_start,
            load_end=self.load_end,
            required_tfs=self.required_tfs,
            required_series=self.required_series,
            symbol=self.symbol,
        )
        
        all_gaps = []
        
        # Check each required series
        for series in self.required_series:
            ts_by_tf = timestamps_by_series_tf.get(series, {})
            
            # Coverage
            coverage, issues = self.check_coverage(ts_by_tf, series)
            report.coverage.update(coverage)
            report.coverage_issues.extend(issues)
            
            # Gaps (only for OHLCV)
            if series == "ohlcv":
                gaps = self.detect_gaps(ts_by_tf, series)
                all_gaps.extend(gaps)
        
        # Sanity check (if data provided)
        if data_rows_by_tf:
            for tf, rows in data_rows_by_tf.items():
                sanity_issues = self.check_sanity(rows, "ohlcv", tf)
                report.sanity_issues.extend(sanity_issues)
        
        # Aggregate gaps
        report.gaps = all_gaps
        report.total_missing_bars = sum(g.missing_count for g in all_gaps)
        
        # Determine if healing is required
        report.heal_required = len(all_gaps) > 0 or len(report.coverage_issues) > 0
        report.heal_ranges = all_gaps
        
        # Overall pass/fail
        report.passed = (
            not report.heal_required and
            len(report.sanity_issues) == 0
        )
        
        return report

