from pathlib import Path

import pandas as pd


def build_holdout_catalog(run_dir: Path, q_threshold: float):
    run_dir = Path(run_dir)
    events_path = run_dir / "events.csv"
    if not events_path.exists():
        raise FileNotFoundError(f"Missing events.csv: {events_path}")

    expected_columns = [
        "event_id",
        "start",
        "end",
        "q_value",
        "edge_novelty_sum",
        "cross_domain_edges_count",
        "sources",
        "domains",
        "top_edges",
    ]

    try:
        events = pd.read_csv(events_path)
    except pd.errors.EmptyDataError:
        catalog = pd.DataFrame(columns=expected_columns)
        output_path = run_dir / "holdout_catalog.csv"
        catalog.to_csv(output_path, index=False)
        print("Holdout catalog:", output_path)
        print(f"Holdout events (q <= {q_threshold}): 0")
        return output_path, catalog

    if "is_holdout" not in events.columns or "q_value" not in events.columns:
        catalog = pd.DataFrame(columns=expected_columns)
        output_path = run_dir / "holdout_catalog.csv"
        catalog.to_csv(output_path, index=False)
        print("Holdout catalog:", output_path)
        print(f"Holdout events (q <= {q_threshold}): 0")
        return output_path, catalog

    events["q_value"] = pd.to_numeric(events["q_value"], errors="coerce")
    holdout_mask = events["is_holdout"].map(
        lambda value: str(value).strip().lower() in {"1", "true", "yes", "y"}
    )
    holdout = events[holdout_mask].copy()
    holdout = holdout[holdout["q_value"] <= float(q_threshold)]
    if holdout.empty:
        catalog = holdout
    else:
        holdout = holdout.sort_values("q_value", ascending=True)
        catalog = holdout[
            [
                "event_id",
                "event_start",
                "event_end",
                "q_value",
                "edge_novelty_sum",
                "cross_domain_edges_count",
                "sources_involved",
                "domains_involved",
                "top_edges",
            ]
        ].rename(
            columns={
                "event_start": "start",
                "event_end": "end",
                "sources_involved": "sources",
                "domains_involved": "domains",
            }
        )

    output_path = run_dir / "holdout_catalog.csv"
    catalog.to_csv(output_path, index=False)
    print("Holdout catalog:", output_path)
    print(f"Holdout events (q <= {q_threshold}): {len(catalog)}")
    return output_path, catalog
