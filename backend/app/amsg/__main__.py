import argparse
from pathlib import Path

from .config import load_config, load_inputs
from .demo import run_demo
from .io import load_series
from .bundle import create_bundle
from .inspect import inspect_event
from .nmdb import run_nmdb_demo
from .omni import run_omni_demo
from .omni_btc import run_omni_btc_control
from .omni_nmdb import run_omni_nmdb_control, run_omni_nmdb_demo
from .pipeline import make_run_dir, run_pipeline
from .swpc import run_swpc_demo
from .meteo import run_meteo_demo
from .geomag import run_geomag_demo
from .pageviews import run_pageviews_demo
from .seismic import run_omni_seismic_control, run_seismic_demo
from .earth import run_earth_demo
from .usgs import run_usgs_demo
from .omni_pageviews import run_omni_pageviews_control
from .control_summary import write_control_summary
from .events_overlap import compute_overlaps
from .quality_scan import run_quality_scan
from .nmdb_quality_scan import run_nmdb_quality_scan_raw
from .holdout_catalog import build_holdout_catalog
from .campaign import run_campaign
from .evidence_summary import write_evidence_summary
from .candidate_conversion import run_candidate_conversion


def _cmd_demo(args):
    project_root = Path(args.project_root).resolve()
    run_demo(project_root)


def _cmd_run(args):
    config = load_config(args.config)
    inputs = load_inputs(args.inputs)
    if not inputs:
        raise SystemExit("No inputs defined.")

    series_list = [load_series(spec) for spec in inputs]
    run_dir = make_run_dir(Path(args.output_dir))
    run_pipeline(series_list, config, run_dir)
    print("Run complete:", run_dir)


def _cmd_swpc_demo(args):
    project_root = Path(args.project_root).resolve()
    run_swpc_demo(project_root, args.days, Path(args.config), include_kp=args.include_kp)


def _cmd_bundle(args):
    project_root = Path(args.project_root).resolve()
    bundle_path = create_bundle(Path(args.run), project_root)
    print("Bundle created:", bundle_path)


def _cmd_control_summary(args):
    project_root = Path(args.project_root).resolve()
    out_json, out_csv = write_control_summary(project_root, Path(args.runs_dir))
    print("Control summary JSON:", out_json)
    print("Control summary CSV:", out_csv)


def _cmd_evidence_summary(args):
    project_root = Path(args.project_root).resolve()
    event_evidence_path = Path(args.event_evidence)
    refresh = bool(args.refresh)
    if not event_evidence_path.exists():
        refresh = True
    summary_json, summary_csv, payload = write_evidence_summary(
        project_root=project_root,
        runs_dir=Path(args.runs_dir),
        event_evidence_path=event_evidence_path,
        summary_json_path=Path(args.summary_json),
        summary_csv_path=Path(args.summary_csv),
        refresh=refresh,
    )
    counts = payload.get("counts", {})
    print("Evidence summary JSON:", summary_json)
    print("Evidence summary CSV:", summary_csv)
    print(
        "Counts:",
        f"replicated={counts.get('replicated', 0)}",
        f"candidate={counts.get('candidate', 0)}",
        f"rejected={counts.get('rejected', 0)}",
    )
    top_replicated = payload.get("top_replicated", [])
    if top_replicated:
        print("Top replicated events:")
        for row in top_replicated[:5]:
            print(
                f"- {row.get('event_key')} "
                f"(overlap_nmdb_quality={row.get('overlap_nmdb_quality')}, "
                f"overlap_geomag_holdout={row.get('overlap_geomag_holdout')})"
            )
    else:
        print("Top replicated events: none")


def _cmd_candidate_conversion(args):
    project_root = Path(args.project_root).resolve()
    shifts = [int(value) for value in args.shifts.split(",") if value.strip()]
    summary = run_candidate_conversion(
        project_root=project_root,
        event_evidence_path=Path(args.event_evidence),
        conversion_report_path=Path(args.conversion_report),
        omni_nmdb_config=Path(args.omni_nmdb_config),
        geomag_config=Path(args.geomag_config),
        strict_top_p=args.strict_top_p,
        pad_days=args.pad_days,
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
        shifts=shifts,
        nmdb_stations=args.nmdb_stations,
        geomag_stations=args.geomag_stations,
        geomag_elements=args.geomag_elements,
        q_threshold=args.q_threshold,
        overlap_window_hours=args.overlap_window_hours,
    )
    print(
        "Conversion result:",
        f"candidate_before={summary['candidate_before']}",
        f"replicated_new={summary['replicated_new']}",
        f"rejected_new={summary['rejected_new']}",
        f"candidate_left={summary['candidate_left']}",
    )


def _cmd_events_overlap(args):
    run_a = Path(args.run_a)
    run_b = Path(args.run_b)
    output_path, rows = compute_overlaps(
        run_a,
        run_b,
        args.window_hours,
        output_suffix=args.output_suffix,
        require_domain=args.require_domain,
        min_domain_edges=args.min_domain_edges,
        min_domain_novelty_sum=args.min_domain_novelty_sum,
        min_nmdb_edges=args.min_nmdb_edges,
        min_nmdb_pair_median=args.min_nmdb_pair_median,
        nmdb_filter_side=args.nmdb_filter_side,
        holdout_only_a=args.holdout_only_a,
        holdout_only_b=args.holdout_only_b,
        max_q_value_a=args.max_q_a,
        max_q_value_b=args.max_q_b,
    )
    print("Overlap CSV:", output_path)
    print(f"Pairs written: {len(rows)}")


def _cmd_inspect(args):
    project_root = Path(args.project_root).resolve()
    run_dir = Path(args.run)
    if args.out:
        out_dir = Path(args.out)
    else:
        out_dir = run_dir / "inspect" / args.event
    inspect_event(run_dir, args.event, out_dir, project_root, args.pad_minutes)
    print("Inspect export:", out_dir)


def _cmd_omni_demo(args):
    project_root = Path(args.project_root).resolve()
    run_omni_demo(
        project_root,
        args.start,
        args.days,
        Path(args.config),
        chunk_days=args.chunk_days,
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
    )


def _cmd_nmdb_demo(args):
    project_root = Path(args.project_root).resolve()
    run_nmdb_demo(
        project_root,
        args.start,
        args.days,
        args.stations,
        dtype=args.dtype,
        tabchoice=args.tabchoice,
        yunits=args.yunits,
        save_csv=not args.no_save_csv,
    )


def _cmd_omni_nmdb_demo(args):
    project_root = Path(args.project_root).resolve()
    run_omni_nmdb_demo(
        project_root,
        args.start,
        args.days,
        args.stations,
        Path(args.config),
        chunk_days=args.chunk_days,
        dtype=args.dtype,
        tabchoice=args.tabchoice,
        yunits=args.yunits,
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
    )


def _cmd_omni_nmdb_control(args):
    project_root = Path(args.project_root).resolve()
    run_omni_nmdb_control(
        project_root,
        args.start,
        args.days,
        args.stations,
        Path(args.config),
        nmdb_shift_days=args.nmdb_shift_days,
        chunk_days=args.chunk_days,
        dtype=args.dtype,
        tabchoice=args.tabchoice,
        yunits=args.yunits,
    )


def _cmd_omni_btc_control(args):
    project_root = Path(args.project_root).resolve()
    run_omni_btc_control(
        project_root,
        args.start,
        args.days,
        Path(args.btc_csv),
        Path(args.config),
        btc_time_col=args.btc_time_col,
        btc_price_col=args.btc_price_col,
        btc_volume_col=args.btc_volume_col,
        btc_transform=args.btc_transform,
        btc_shift_days=args.btc_shift_days,
        chunk_days=args.chunk_days,
        freq=args.freq,
        top_p=args.top_p,
        window_sizes=args.window_sizes,
        null_shifts_count=args.null_shifts_count,
    )


def _cmd_usgs_demo(args):
    project_root = Path(args.project_root).resolve()
    run_usgs_demo(
        project_root,
        args.start,
        args.days,
        args.sites,
        args.params,
        Path(args.config),
        transform=args.transform,
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
    )


def _cmd_meteo_demo(args):
    project_root = Path(args.project_root).resolve()
    values = args.latlon
    if len(values) % 2 != 0:
        raise SystemExit("latlon must be pairs: --latlon <lat1> <lon1> <lat2> <lon2> ...")
    pairs = []
    for idx in range(0, len(values), 2):
        pairs.append((float(values[idx]), float(values[idx + 1])))
    run_meteo_demo(
        project_root,
        args.start,
        args.days,
        pairs,
        Path(args.config),
        transform=args.transform,
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
    )


def _cmd_geomag_demo(args):
    project_root = Path(args.project_root).resolve()
    run_geomag_demo(
        project_root,
        args.start,
        args.days,
        args.stations,
        args.elements,
        Path(args.config),
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
    )


def _cmd_pageviews_demo(args):
    project_root = Path(args.project_root).resolve()
    run_pageviews_demo(
        project_root,
        args.start,
        args.days,
        args.articles,
        Path(args.config),
        project=args.project,
        access=args.access,
        agent=args.agent,
        granularity=args.granularity,
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
    )


def _cmd_omni_pageviews_control(args):
    project_root = Path(args.project_root).resolve()
    shift_list = None
    if args.pageviews_shift_list:
        shift_list = [
            int(value) for value in args.pageviews_shift_list.split(",") if value.strip()
        ]
    run_omni_pageviews_control(
        project_root,
        args.start,
        args.days,
        args.articles,
        Path(args.config),
        project=args.project,
        access=args.access,
        agent=args.agent,
        granularity=args.granularity,
        pageviews_shift_list=shift_list,
        pageviews_shift_days=args.pageviews_shift_days,
        chunk_days=args.chunk_days,
    )


def _cmd_earth_demo(args):
    project_root = Path(args.project_root).resolve()
    values = args.latlon
    if len(values) % 2 != 0:
        raise SystemExit("latlon must be pairs: --latlon <lat1> <lon1> <lat2> <lon2> ...")
    pairs = []
    for idx in range(0, len(values), 2):
        pairs.append((float(values[idx]), float(values[idx + 1])))
    run_earth_demo(
        project_root,
        args.start,
        args.days,
        args.sites,
        args.params,
        pairs,
        Path(args.config),
        meteo_shift_days=args.meteo_shift_days,
        meteo_shift_hours=args.meteo_shift_hours,
    )


def _cmd_quality_scan(args):
    project_root = Path(args.project_root).resolve()
    run_quality_scan(
        Path(args.run),
        args.sources,
        args.window_hours,
        args.min_valid,
        args.min_duration_hours,
        profile=args.profile,
        project_root=project_root,
    )


def _cmd_nmdb_quality_scan_raw(args):
    project_root = Path(args.project_root).resolve()
    run_nmdb_quality_scan_raw(
        project_root,
        args.stations,
        args.start,
        args.days,
        args.window_hours,
        args.min_valid,
        args.min_duration_hours,
        top_k=args.top_k,
    )


def _cmd_holdout_catalog(args):
    output_path, _ = build_holdout_catalog(Path(args.run), args.q_threshold)
    print("Holdout catalog saved:", output_path)


def _cmd_campaign_run(args):
    project_root = Path(args.project_root).resolve()
    summary_path = run_campaign(
        project_root,
        args.start,
        args.end,
        args.window_days,
        args.step_days,
        args.stack,
        omni_nmdb_config=Path(args.omni_nmdb_config) if args.omni_nmdb_config else None,
        geomag_config=Path(args.geomag_config) if args.geomag_config else None,
        nmdb_stations=args.nmdb_stations,
        geomag_stations=args.geomag_stations,
        geomag_elements=args.geomag_elements,
        holdout_ratio=args.holdout_ratio,
        holdout_mode=args.holdout_mode,
        q_threshold=args.q_threshold,
        overlap_window_hours=args.overlap_window_hours,
    )
    print("Campaign summary saved:", summary_path)


def _cmd_seismic_demo(args):
    project_root = Path(args.project_root).resolve()
    bbox = None
    if args.bbox:
        if len(args.bbox) != 4:
            raise SystemExit("--bbox requires 4 values: minlat maxlat minlon maxlon")
        bbox = tuple(float(value) for value in args.bbox)
    run_seismic_demo(
        project_root,
        args.start,
        args.days,
        Path(args.config),
        min_magnitude=args.min_magnitude,
        bbox=bbox,
        transform=args.transform,
        zero_as_nan=args.seismic_zero_as_nan,
        min_nonzero_fraction=args.seismic_min_nonzero_fraction,
    )


def _cmd_omni_seismic_control(args):
    project_root = Path(args.project_root).resolve()
    bbox = None
    if args.bbox:
        if len(args.bbox) != 4:
            raise SystemExit("--bbox requires 4 values: minlat maxlat minlon maxlon")
        bbox = tuple(float(value) for value in args.bbox)
    shift_list = None
    if args.seismic_shift_list:
        shift_list = [int(value) for value in args.seismic_shift_list.split(",") if value.strip()]
    run_omni_seismic_control(
        project_root,
        args.start,
        args.days,
        Path(args.config),
        min_magnitude=args.min_magnitude,
        bbox=bbox,
        seismic_shift_days=args.seismic_shift_days,
        seismic_shift_hours=args.seismic_shift_hours,
        seismic_shift_list=shift_list,
        repeat=args.repeat,
        seismic_transform=args.seismic_transform,
        seismic_zero_as_nan=args.seismic_zero_as_nan,
        seismic_min_nonzero_fraction=args.seismic_min_nonzero_fraction,
    )


def main():
    parser = argparse.ArgumentParser(prog="amsg")
    subparsers = parser.add_subparsers(dest="command", required=True)

    demo_parser = subparsers.add_parser("demo", help="Run the synthetic demo")
    demo_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    demo_parser.set_defaults(func=_cmd_demo)

    run_parser = subparsers.add_parser("run", help="Run the pipeline on inputs")
    run_parser.add_argument("--config", required=True, help="Path to config YAML/JSON")
    run_parser.add_argument("--inputs", required=True, help="Path to inputs YAML/JSON")
    run_parser.add_argument(
        "--output-dir",
        default="runs",
        help="Base output directory for runs",
    )
    run_parser.set_defaults(func=_cmd_run)

    swpc_parser = subparsers.add_parser("swpc_demo", help="Run SWPC real-data demo")
    swpc_parser.add_argument("--days", type=int, default=7, help="Days of data to keep")
    swpc_parser.add_argument(
        "--include-kp",
        action="store_true",
        help="Include planetary Kp source (upsampled/ffill)",
    )
    swpc_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "swpc_7day.yaml",
        help="Path to SWPC config YAML/JSON",
    )
    swpc_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    swpc_parser.set_defaults(func=_cmd_swpc_demo)

    bundle_parser = subparsers.add_parser("bundle", help="Bundle a run with context")
    bundle_parser.add_argument("--run", required=True, help="Path to run directory")
    bundle_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    bundle_parser.set_defaults(func=_cmd_bundle)

    summary_parser = subparsers.add_parser(
        "control_summary", help="Aggregate control_compare/control_report files"
    )
    summary_parser.add_argument(
        "--runs-dir",
        default=Path(__file__).resolve().parents[1] / "runs",
        help="Runs directory to scan",
    )
    summary_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    summary_parser.set_defaults(func=_cmd_control_summary)

    evidence_parser = subparsers.add_parser(
        "evidence_summary",
        help="Build event_evidence gate table and aggregate replicated/candidate/rejected counts",
    )
    evidence_parser.add_argument(
        "--runs-dir",
        default=Path(__file__).resolve().parents[1] / "runs",
        help="Runs directory to scan (default: ./runs)",
    )
    evidence_parser.add_argument(
        "--event-evidence",
        default=Path(__file__).resolve().parents[1] / "runs" / "event_evidence.csv",
        help="Path to event_evidence.csv",
    )
    evidence_parser.add_argument(
        "--summary-json",
        default=Path(__file__).resolve().parents[1] / "runs" / "evidence_summary.json",
        help="Path to evidence_summary.json",
    )
    evidence_parser.add_argument(
        "--summary-csv",
        default=Path(__file__).resolve().parents[1] / "runs" / "evidence_summary.csv",
        help="Path to evidence_summary.csv",
    )
    evidence_parser.add_argument(
        "--refresh",
        action="store_true",
        help="Rebuild event_evidence.csv from raw run artifacts before summarizing",
    )
    evidence_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    evidence_parser.set_defaults(func=_cmd_evidence_summary)

    conversion_parser = subparsers.add_parser(
        "candidate_conversion",
        help="Run mini-replication cycle for candidate events and update event_evidence statuses",
    )
    conversion_parser.add_argument(
        "--event-evidence",
        default=Path(__file__).resolve().parents[1] / "runs" / "event_evidence.csv",
        help="Path to event_evidence.csv",
    )
    conversion_parser.add_argument(
        "--conversion-report",
        default=Path(__file__).resolve().parents[1] / "runs" / "conversion_report.csv",
        help="Path to conversion_report.csv",
    )
    conversion_parser.add_argument(
        "--omni-nmdb-config",
        default=Path(__file__).resolve().parents[1]
        / "configs"
        / "omni_nmdb_90day_discovery_10min.yaml",
        help="Base config for OMNI+NMDB mini-replication",
    )
    conversion_parser.add_argument(
        "--geomag-config",
        default=Path(__file__).resolve().parents[1] / "configs" / "geomag_90day_discovery.yaml",
        help="Base config for geomag mini-replication",
    )
    conversion_parser.add_argument(
        "--strict-top-p",
        type=float,
        default=0.005,
        help="Strict variant top_p (default: 0.005)",
    )
    conversion_parser.add_argument(
        "--pad-days",
        type=int,
        default=14,
        help="Pad window around event interval in days (default: 14)",
    )
    conversion_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=0.3,
        help="Holdout ratio for mini-replication runs (default: 0.3)",
    )
    conversion_parser.add_argument(
        "--holdout-mode",
        default="time",
        help="Holdout mode for mini-replication runs (default: time)",
    )
    conversion_parser.add_argument(
        "--shifts",
        default="7,13,19",
        help="Comma-separated NMDB shift stress-check days (default: 7,13,19)",
    )
    conversion_parser.add_argument(
        "--nmdb-stations",
        nargs="+",
        default=["OULU", "JUNG"],
        help="NMDB stations for OMNI+NMDB stack (default: OULU JUNG)",
    )
    conversion_parser.add_argument(
        "--geomag-stations",
        nargs="+",
        default=["BOU", "FRD"],
        help="Geomag stations (default: BOU FRD)",
    )
    conversion_parser.add_argument(
        "--geomag-elements",
        nargs="+",
        default=["H", "Z"],
        help="Geomag elements (default: H Z)",
    )
    conversion_parser.add_argument(
        "--q-threshold",
        type=float,
        default=0.05,
        help="Holdout q threshold for overlap filter (default: 0.05)",
    )
    conversion_parser.add_argument(
        "--overlap-window-hours",
        type=float,
        default=6.0,
        help="Overlap tolerance in hours (default: 6)",
    )
    conversion_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    conversion_parser.set_defaults(func=_cmd_candidate_conversion)

    overlap_parser = subparsers.add_parser(
        "events_overlap", help="Compute overlap between two events.csv files"
    )
    overlap_parser.add_argument("--run-a", required=True, help="Run directory A")
    overlap_parser.add_argument("--run-b", required=True, help="Run directory B")
    overlap_parser.add_argument(
        "--window-hours",
        type=float,
        default=6.0,
        help="Gap tolerance in hours (default: 6)",
    )
    overlap_parser.add_argument(
        "--require-domain",
        default=None,
        help="Require domain participation (e.g. nmdb_cosmicray)",
    )
    overlap_parser.add_argument(
        "--min-domain-edges",
        type=int,
        default=0,
        help="Minimum edges for required domain (default: 0)",
    )
    overlap_parser.add_argument(
        "--min-domain-novelty-sum",
        type=float,
        default=0.0,
        help="Minimum novelty sum for required domain (default: 0)",
    )
    overlap_parser.add_argument(
        "--min-nmdb-edges",
        type=int,
        default=0,
        help="Minimum NMDB edges count (default: 0)",
    )
    overlap_parser.add_argument(
        "--min-nmdb-pair-median",
        type=float,
        default=0.0,
        help="Minimum NMDB pair_valid_fraction median (default: 0)",
    )
    overlap_parser.add_argument(
        "--nmdb-filter-side",
        choices=["a", "b", "both"],
        default="both",
        help="Which side to apply NMDB filters to (default: both)",
    )
    overlap_parser.add_argument(
        "--holdout-only-a",
        action="store_true",
        help="Require holdout events for run A",
    )
    overlap_parser.add_argument(
        "--holdout-only-b",
        action="store_true",
        help="Require holdout events for run B",
    )
    overlap_parser.add_argument(
        "--max-q-a",
        type=float,
        default=None,
        help="Max q_value for run A events (default: none)",
    )
    overlap_parser.add_argument(
        "--max-q-b",
        type=float,
        default=None,
        help="Max q_value for run B events (default: none)",
    )
    overlap_parser.add_argument(
        "--output-suffix",
        default="",
        help="Suffix for overlap CSV filename (e.g. _geomag_holdout)",
    )
    overlap_parser.set_defaults(func=_cmd_events_overlap)

    inspect_parser = subparsers.add_parser("inspect", help="Export event-aligned slices")
    inspect_parser.add_argument("--run", required=True, help="Path to run directory")
    inspect_parser.add_argument("--event", required=True, help="Event id (e.g. e0001)")
    inspect_parser.add_argument(
        "--out",
        required=False,
        default=None,
        help="Output directory for inspection CSVs (default: runs/<run_id>/inspect/<event>)",
    )
    inspect_parser.add_argument(
        "--pad-minutes",
        type=float,
        default=None,
        help="Padding in minutes around event window (default: 2*max(window_sizes))",
    )
    inspect_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    inspect_parser.set_defaults(func=_cmd_inspect)

    omni_parser = subparsers.add_parser("omni_demo", help="Run OMNI HAPI demo")
    omni_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    omni_parser.add_argument("--days", type=int, default=30, help="Number of days")
    omni_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "omni_30day.yaml",
        help="Path to OMNI config YAML/JSON",
    )
    omni_parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Chunk size for HAPI downloads (days)",
    )
    omni_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=None,
        help="Holdout ratio for test split (override config)",
    )
    omni_parser.add_argument(
        "--holdout-mode",
        default=None,
        help="Holdout mode (override config, e.g. time)",
    )
    omni_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    omni_parser.set_defaults(func=_cmd_omni_demo)

    nmdb_parser = subparsers.add_parser("nmdb_demo", help="Fetch NMDB data via NEST")
    nmdb_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    nmdb_parser.add_argument("--days", type=int, default=1, help="Number of days")
    nmdb_parser.add_argument(
        "--stations",
        nargs="+",
        required=True,
        help="NMDB station codes (e.g. OULU JUNG)",
    )
    nmdb_parser.add_argument(
        "--dtype",
        default="corr_for_efficiency",
        help="NMDB dtype (default: corr_for_efficiency)",
    )
    nmdb_parser.add_argument(
        "--tabchoice",
        default="ori",
        help="NMDB tabchoice (default: ori)",
    )
    nmdb_parser.add_argument(
        "--yunits",
        type=int,
        default=0,
        help="NMDB yunits (default: 0)",
    )
    nmdb_parser.add_argument(
        "--no-save-csv",
        action="store_true",
        help="Disable saving NMDB CSV to data/derived/",
    )
    nmdb_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    nmdb_parser.set_defaults(func=_cmd_nmdb_demo)

    omni_nmdb_parser = subparsers.add_parser(
        "omni_nmdb_demo", help="Run OMNI + NMDB demo"
    )
    omni_nmdb_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    omni_nmdb_parser.add_argument("--days", type=int, default=30, help="Number of days")
    omni_nmdb_parser.add_argument(
        "--stations",
        nargs="+",
        required=True,
        help="NMDB station codes (e.g. OULU JUNG)",
    )
    omni_nmdb_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "omni_nmdb_30day.yaml",
        help="Path to OMNI+NMDB config YAML/JSON",
    )
    omni_nmdb_parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Chunk size for HAPI downloads (days)",
    )
    omni_nmdb_parser.add_argument(
        "--dtype",
        default="corr_for_efficiency",
        help="NMDB dtype (default: corr_for_efficiency)",
    )
    omni_nmdb_parser.add_argument(
        "--tabchoice",
        default="ori",
        help="NMDB tabchoice (default: ori)",
    )
    omni_nmdb_parser.add_argument(
        "--yunits",
        type=int,
        default=0,
        help="NMDB yunits (default: 0)",
    )
    omni_nmdb_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=None,
        help="Holdout ratio for test split (override config)",
    )
    omni_nmdb_parser.add_argument(
        "--holdout-mode",
        default=None,
        help="Holdout mode (override config, e.g. time)",
    )
    omni_nmdb_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    omni_nmdb_parser.set_defaults(func=_cmd_omni_nmdb_demo)

    omni_nmdb_control_parser = subparsers.add_parser(
        "omni_nmdb_control", help="Run OMNI + NMDB negative control (REAL vs SHIFT)"
    )
    omni_nmdb_control_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    omni_nmdb_control_parser.add_argument(
        "--days", type=int, default=30, help="Number of days"
    )
    omni_nmdb_control_parser.add_argument(
        "--stations",
        nargs="+",
        required=True,
        help="NMDB station codes (e.g. OULU JUNG)",
    )
    omni_nmdb_control_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "omni_nmdb_30day.yaml",
        help="Path to OMNI+NMDB config YAML/JSON",
    )
    omni_nmdb_control_parser.add_argument(
        "--nmdb_shift_days",
        type=int,
        default=13,
        help="Days to shift NMDB for control (default: 13)",
    )
    omni_nmdb_control_parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Chunk size for HAPI downloads (days)",
    )
    omni_nmdb_control_parser.add_argument(
        "--dtype",
        default="corr_for_efficiency",
        help="NMDB dtype (default: corr_for_efficiency)",
    )
    omni_nmdb_control_parser.add_argument(
        "--tabchoice",
        default="ori",
        help="NMDB tabchoice (default: ori)",
    )
    omni_nmdb_control_parser.add_argument(
        "--yunits",
        type=int,
        default=0,
        help="NMDB yunits (default: 0)",
    )
    omni_nmdb_control_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    omni_nmdb_control_parser.set_defaults(func=_cmd_omni_nmdb_control)

    btc_control_parser = subparsers.add_parser(
        "omni_btc_control", help="Run OMNI + BTC negative control (REAL vs SHIFT)"
    )
    btc_control_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    btc_control_parser.add_argument("--days", type=int, default=30, help="Number of days")
    btc_control_parser.add_argument("--btc_csv", required=True, help="Path to BTC CSV")
    btc_control_parser.add_argument(
        "--btc_time_col",
        default="time",
        help="BTC time column (default: time)",
    )
    btc_control_parser.add_argument(
        "--btc_price_col",
        default="close",
        help="BTC price/close column (default: close)",
    )
    btc_control_parser.add_argument(
        "--btc_volume_col",
        default=None,
        help="BTC volume column (optional)",
    )
    btc_control_parser.add_argument(
        "--btc_transform",
        default="log_return",
        help="BTC transform (default: log_return)",
    )
    btc_control_parser.add_argument(
        "--btc_shift_days",
        type=int,
        default=13,
        help="Days to shift BTC for control (default: 13)",
    )
    btc_control_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "omni_30day.yaml",
        help="Path to config YAML/JSON",
    )
    btc_control_parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Chunk size for HAPI downloads (days)",
    )
    btc_control_parser.add_argument(
        "--freq",
        default=None,
        help="Override frequency (default from config)",
    )
    btc_control_parser.add_argument(
        "--top_p",
        type=float,
        default=None,
        help="Override top_p (default from config)",
    )
    btc_control_parser.add_argument(
        "--window_sizes",
        nargs="+",
        type=int,
        default=None,
        help="Override window sizes (space-separated)",
    )
    btc_control_parser.add_argument(
        "--null_shifts_count",
        type=int,
        default=None,
        help="Override null_shifts_count (default from config)",
    )
    btc_control_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    btc_control_parser.set_defaults(func=_cmd_omni_btc_control)

    usgs_parser = subparsers.add_parser("usgs_demo", help="Run USGS hydrology demo")
    usgs_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    usgs_parser.add_argument("--days", type=int, default=30, help="Number of days")
    usgs_parser.add_argument(
        "--sites",
        nargs="+",
        required=True,
        help="USGS site IDs (e.g. 01646500 02037500)",
    )
    usgs_parser.add_argument(
        "--params",
        nargs="+",
        required=True,
        help="USGS parameter codes (e.g. 00060 00065)",
    )
    usgs_parser.add_argument(
        "--transform",
        default="identity",
        help="Value transform (identity, log_return, or detrend)",
    )
    usgs_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=None,
        help="Holdout ratio for test split (override config)",
    )
    usgs_parser.add_argument(
        "--holdout-mode",
        default=None,
        help="Holdout mode (override config, e.g. time)",
    )
    usgs_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "usgs_30day.yaml",
        help="Path to USGS config YAML/JSON",
    )
    usgs_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    usgs_parser.set_defaults(func=_cmd_usgs_demo)

    meteo_parser = subparsers.add_parser("meteo_demo", help="Run Open-Meteo demo")
    meteo_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    meteo_parser.add_argument("--days", type=int, default=30, help="Number of days")
    meteo_parser.add_argument(
        "--latlon",
        nargs="+",
        required=True,
        help="Latitude/longitude pairs (e.g. 52.5 13.4 35.7 -78.6)",
    )
    meteo_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "meteo_30day.yaml",
        help="Path to Meteo config YAML/JSON",
    )
    meteo_parser.add_argument(
        "--transform",
        default="identity",
        help="Value transform (identity or detrend)",
    )
    meteo_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=None,
        help="Holdout ratio for test split (override config)",
    )
    meteo_parser.add_argument(
        "--holdout-mode",
        default=None,
        help="Holdout mode (override config, e.g. time)",
    )
    meteo_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    meteo_parser.set_defaults(func=_cmd_meteo_demo)

    geomag_parser = subparsers.add_parser("geomag_demo", help="Run USGS geomag demo")
    geomag_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    geomag_parser.add_argument("--days", type=int, default=30, help="Number of days")
    geomag_parser.add_argument(
        "--stations",
        nargs="+",
        required=True,
        help="Geomag station IDs (e.g. BOU FRD)",
    )
    geomag_parser.add_argument(
        "--elements",
        nargs="+",
        required=True,
        help="Geomag elements (e.g. H Z)",
    )
    geomag_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "geomag_30day.yaml",
        help="Path to geomag config YAML/JSON",
    )
    geomag_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=None,
        help="Holdout ratio for test split (override config)",
    )
    geomag_parser.add_argument(
        "--holdout-mode",
        default=None,
        help="Holdout mode (override config, e.g. time)",
    )
    geomag_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    geomag_parser.set_defaults(func=_cmd_geomag_demo)

    pageviews_parser = subparsers.add_parser(
        "pageviews_demo", help="Run Wikimedia Pageviews demo"
    )
    pageviews_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    pageviews_parser.add_argument("--days", type=int, default=30, help="Number of days")
    pageviews_parser.add_argument(
        "--articles",
        nargs="+",
        required=True,
        help="Article titles (e.g. Bitcoin Main_Page)",
    )
    pageviews_parser.add_argument(
        "--project",
        default="en.wikipedia",
        help="Wikimedia project (default: en.wikipedia)",
    )
    pageviews_parser.add_argument(
        "--access",
        default="all-access",
        help="Access channel (default: all-access)",
    )
    pageviews_parser.add_argument(
        "--agent",
        default="all-agents",
        help="Agent type (default: all-agents)",
    )
    pageviews_parser.add_argument(
        "--granularity",
        default="daily",
        help="Granularity (default: daily)",
    )
    pageviews_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=None,
        help="Holdout ratio for test split (override config)",
    )
    pageviews_parser.add_argument(
        "--holdout-mode",
        default=None,
        help="Holdout mode (override config, e.g. time)",
    )
    pageviews_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "pageviews_30day.yaml",
        help="Path to pageviews config YAML/JSON",
    )
    pageviews_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    pageviews_parser.set_defaults(func=_cmd_pageviews_demo)

    earth_parser = subparsers.add_parser(
        "earth_demo", help="Run USGS + Open-Meteo control (REAL vs SHIFT)"
    )
    earth_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    earth_parser.add_argument("--days", type=int, default=30, help="Number of days")
    earth_parser.add_argument(
        "--sites",
        nargs="+",
        required=True,
        help="USGS site IDs (e.g. 01646500 02037500)",
    )
    earth_parser.add_argument(
        "--params",
        nargs="+",
        required=True,
        help="USGS parameter codes (e.g. 00060 00065)",
    )
    earth_parser.add_argument(
        "--latlon",
        nargs="+",
        required=True,
        help="Latitude/longitude pairs (e.g. 52.5 13.4 35.7 -78.6)",
    )
    earth_parser.add_argument(
        "--meteo_shift_days",
        type=int,
        default=13,
        help="Days to shift Open-Meteo for control (default: 13)",
    )
    earth_parser.add_argument(
        "--meteo_shift_hours",
        type=int,
        default=None,
        help="Hours to shift Open-Meteo for control (overrides days)",
    )
    earth_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "earth_30day.yaml",
        help="Path to Earth config YAML/JSON",
    )
    earth_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    earth_parser.set_defaults(func=_cmd_earth_demo)

    quality_parser = subparsers.add_parser(
        "quality_scan", help="Scan source quality intervals by rolling valid_fraction"
    )
    quality_parser.add_argument("--run", required=True, help="Run directory to analyze")
    quality_parser.add_argument(
        "--sources",
        nargs="+",
        required=True,
        help="Source patterns (e.g. nmdb_*)",
    )
    quality_parser.add_argument(
        "--profile",
        default=None,
        help="Quality profile (strict or relaxed). Overrides min-valid/min-duration.",
    )
    quality_parser.add_argument(
        "--window-hours",
        type=float,
        default=24,
        help="Rolling window size in hours (default: 24)",
    )
    quality_parser.add_argument(
        "--min-valid",
        type=float,
        default=0.9,
        help="Minimum valid fraction in window (default: 0.9)",
    )
    quality_parser.add_argument(
        "--min-duration-hours",
        type=float,
        default=72,
        help="Minimum interval duration in hours (default: 72)",
    )
    quality_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    quality_parser.set_defaults(func=_cmd_quality_scan)

    nmdb_quality_parser = subparsers.add_parser(
        "nmdb_quality_scan_raw",
        help="Scan NMDB station quality without OMNI alignment",
    )
    nmdb_quality_parser.add_argument(
        "--stations",
        nargs="+",
        required=True,
        help="NMDB station codes (e.g. OULU JUNG)",
    )
    nmdb_quality_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    nmdb_quality_parser.add_argument("--days", type=int, default=90, help="Number of days")
    nmdb_quality_parser.add_argument(
        "--window-hours",
        type=float,
        default=24,
        help="Rolling window size in hours (default: 24)",
    )
    nmdb_quality_parser.add_argument(
        "--min-valid",
        type=float,
        default=0.9,
        help="Minimum valid fraction in window (default: 0.9)",
    )
    nmdb_quality_parser.add_argument(
        "--min-duration-hours",
        type=float,
        default=72,
        help="Minimum interval duration in hours (default: 72)",
    )
    nmdb_quality_parser.add_argument(
        "--top-k",
        type=int,
        default=None,
        help="Limit to top-K intervals (default: all)",
    )
    nmdb_quality_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    nmdb_quality_parser.set_defaults(func=_cmd_nmdb_quality_scan_raw)

    holdout_parser = subparsers.add_parser(
        "holdout_catalog",
        help="Build holdout catalog from events.csv (is_holdout + q_value)",
    )
    holdout_parser.add_argument("--run", required=True, help="Run directory")
    holdout_parser.add_argument(
        "--q-threshold",
        type=float,
        default=0.05,
        help="q_value threshold (default: 0.05)",
    )
    holdout_parser.set_defaults(func=_cmd_holdout_catalog)

    campaign_parser = subparsers.add_parser(
        "campaign_run",
        help="Run rolling holdout campaigns and summarize results",
    )
    campaign_parser.add_argument("--start", required=True, help="Start time (YYYY-MM-DD)")
    campaign_parser.add_argument("--end", required=True, help="End time (YYYY-MM-DD)")
    campaign_parser.add_argument(
        "--window-days",
        type=int,
        required=True,
        help="Window size in days",
    )
    campaign_parser.add_argument(
        "--step-days",
        type=int,
        required=True,
        help="Step size in days",
    )
    campaign_parser.add_argument(
        "--stack",
        nargs="+",
        required=True,
        help="Stacks to run (omni_nmdb, geomag)",
    )
    campaign_parser.add_argument(
        "--omni-nmdb-config",
        default=None,
        help="Config path for OMNI+NMDB",
    )
    campaign_parser.add_argument(
        "--geomag-config",
        default=None,
        help="Config path for geomag",
    )
    campaign_parser.add_argument(
        "--nmdb-stations",
        nargs="+",
        default=["OULU", "JUNG"],
        help="NMDB station codes (default: OULU JUNG)",
    )
    campaign_parser.add_argument(
        "--geomag-stations",
        nargs="+",
        default=["BOU", "FRD"],
        help="Geomag stations (default: BOU FRD)",
    )
    campaign_parser.add_argument(
        "--geomag-elements",
        nargs="+",
        default=["H", "Z"],
        help="Geomag elements (default: H Z)",
    )
    campaign_parser.add_argument(
        "--holdout-ratio",
        type=float,
        default=None,
        help="Holdout ratio for test split",
    )
    campaign_parser.add_argument(
        "--holdout-mode",
        default=None,
        help="Holdout mode (e.g. time)",
    )
    campaign_parser.add_argument(
        "--q-threshold",
        type=float,
        default=0.05,
        help="Holdout q_value threshold (default: 0.05)",
    )
    campaign_parser.add_argument(
        "--overlap-window-hours",
        type=float,
        default=6.0,
        help="Overlap gap tolerance in hours (default: 6)",
    )
    campaign_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    campaign_parser.set_defaults(func=_cmd_campaign_run)

    pageviews_control_parser = subparsers.add_parser(
        "omni_pageviews_control",
        help="Run OMNI + Pageviews negative control (REAL vs SHIFT)",
    )
    pageviews_control_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    pageviews_control_parser.add_argument(
        "--days", type=int, default=30, help="Number of days"
    )
    pageviews_control_parser.add_argument(
        "--articles",
        nargs="+",
        required=True,
        help="Article titles (e.g. Bitcoin Main_Page)",
    )
    pageviews_control_parser.add_argument(
        "--project",
        default="en.wikipedia",
        help="Wikimedia project (default: en.wikipedia)",
    )
    pageviews_control_parser.add_argument(
        "--access",
        default="all-access",
        help="Access channel (default: all-access)",
    )
    pageviews_control_parser.add_argument(
        "--agent",
        default="all-agents",
        help="Agent type (default: all-agents)",
    )
    pageviews_control_parser.add_argument(
        "--granularity",
        default="daily",
        help="Granularity (default: daily)",
    )
    pageviews_control_parser.add_argument(
        "--pageviews_shift_days",
        type=int,
        default=13,
        help="Days to shift pageviews for control (default: 13)",
    )
    pageviews_control_parser.add_argument(
        "--pageviews_shift_list",
        default=None,
        help="Comma-separated day shifts for multi-shift control (e.g. 7,13,19,29)",
    )
    pageviews_control_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "pageviews_30day.yaml",
        help="Path to pageviews config YAML/JSON",
    )
    pageviews_control_parser.add_argument(
        "--chunk-days",
        type=int,
        default=7,
        help="Chunk size for HAPI downloads (days)",
    )
    pageviews_control_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    pageviews_control_parser.set_defaults(func=_cmd_omni_pageviews_control)

    seismic_parser = subparsers.add_parser("seismic_demo", help="Run USGS seismic demo")
    seismic_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    seismic_parser.add_argument("--days", type=int, default=30, help="Number of days")
    seismic_parser.add_argument(
        "--min-magnitude",
        "--min_mag",
        dest="min_magnitude",
        type=float,
        default=2.5,
        help="Minimum magnitude (default: 2.5)",
    )
    seismic_parser.add_argument(
        "--bbox",
        nargs="+",
        default=None,
        help="Bounding box: minlat maxlat minlon maxlon (optional)",
    )
    seismic_parser.add_argument(
        "--transform",
        default="identity",
        help="Seismic transform (identity or log1p)",
    )
    seismic_parser.add_argument(
        "--seismic_zero_as_nan",
        action="store_true",
        help="Convert zero seismic bins to NaN",
    )
    seismic_parser.add_argument(
        "--seismic_min_nonzero_fraction",
        type=float,
        default=None,
        help="Minimum rolling nonzero fraction to keep values (optional)",
    )
    seismic_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "seismic_30day.yaml",
        help="Path to seismic config YAML/JSON",
    )
    seismic_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    seismic_parser.set_defaults(func=_cmd_seismic_demo)

    omni_seismic_parser = subparsers.add_parser(
        "omni_seismic_control", help="Run OMNI + seismic control (REAL vs SHIFT)"
    )
    omni_seismic_parser.add_argument(
        "--start",
        required=True,
        help="Start date (YYYY-MM-DD or ISO time)",
    )
    omni_seismic_parser.add_argument("--days", type=int, default=30, help="Number of days")
    omni_seismic_parser.add_argument(
        "--min-magnitude",
        "--min_mag",
        dest="min_magnitude",
        type=float,
        default=2.5,
        help="Minimum magnitude (default: 2.5)",
    )
    omni_seismic_parser.add_argument(
        "--bbox",
        nargs="+",
        default=None,
        help="Bounding box: minlat maxlat minlon maxlon (optional)",
    )
    omni_seismic_parser.add_argument(
        "--seismic_shift_days",
        type=int,
        default=13,
        help="Days to shift seismic for control (default: 13)",
    )
    omni_seismic_parser.add_argument(
        "--seismic_shift_hours",
        type=int,
        default=None,
        help="Hours to shift seismic for control (overrides days)",
    )
    omni_seismic_parser.add_argument(
        "--seismic_shift_list",
        default=None,
        help="Comma-separated day shifts for multi-shift control (e.g. 7,13,19,29)",
    )
    omni_seismic_parser.add_argument(
        "--repeat",
        type=int,
        default=1,
        help="Repeat shifts with multiples of shift_days/shift_hours (default: 1)",
    )
    omni_seismic_parser.add_argument(
        "--seismic_transform",
        default="identity",
        help="Seismic transform (identity or log1p)",
    )
    omni_seismic_parser.add_argument(
        "--seismic_zero_as_nan",
        action="store_true",
        help="Convert zero seismic bins to NaN",
    )
    omni_seismic_parser.add_argument(
        "--seismic_min_nonzero_fraction",
        type=float,
        default=None,
        help="Minimum rolling nonzero fraction to keep values (optional)",
    )
    omni_seismic_parser.add_argument(
        "--config",
        default=Path(__file__).resolve().parents[1] / "configs" / "seismic_30day.yaml",
        help="Path to seismic config YAML/JSON",
    )
    omni_seismic_parser.add_argument(
        "--project-root",
        default=Path(__file__).resolve().parents[1],
        help="Project root directory",
    )
    omni_seismic_parser.set_defaults(func=_cmd_omni_seismic_control)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
