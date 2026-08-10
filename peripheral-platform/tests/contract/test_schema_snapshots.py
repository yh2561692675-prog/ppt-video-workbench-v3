from __future__ import annotations

from pathlib import Path

from peripheral_contracts.schemas import write_schema_snapshots


def test_schema_snapshots_match_contract_models(tmp_path):
    write_schema_snapshots(tmp_path)
    repository_snapshots = Path(__file__).resolve().parents[2] / "schemas"

    generated_names = {path.name for path in tmp_path.glob("*.json")}
    repository_names = {path.name for path in repository_snapshots.glob("*.json")}

    assert generated_names == {
        "artifact-manifest-1.0.json",
        "event-envelope-1.0.json",
        "job-envelope-1.0.json",
        "job-result-1.0.json",
        "module-manifest-1.0.json",
    }
    assert repository_names == generated_names
    for filename in sorted(generated_names):
        assert (repository_snapshots / filename).read_bytes() == (tmp_path / filename).read_bytes()
