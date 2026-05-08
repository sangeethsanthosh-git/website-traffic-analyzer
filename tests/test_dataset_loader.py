from pathlib import Path

import pytest

from app import DatasetImportError, load_traffic_dataset


def test_load_traffic_dataset_sorts_rows_by_date(tmp_path: Path):
    csv_path = tmp_path / "traffic.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Date,Combined Users",
                "08/07/2017,579",
                "04/21/2017,469",
                "02/26/2018,955",
            ]
        ),
        encoding="utf-8",
    )

    records = load_traffic_dataset(csv_path)

    assert len(records) == 3
    assert records[0].visit_date.isoformat() == "2017-04-21"
    assert records[-1].user_count == 955


def test_load_traffic_dataset_requires_expected_columns(tmp_path: Path):
    csv_path = tmp_path / "traffic.csv"
    csv_path.write_text("Date,Count\n08/07/2017,579\n", encoding="utf-8")

    with pytest.raises(DatasetImportError):
        load_traffic_dataset(csv_path)


def test_load_traffic_dataset_falls_back_to_available_user_columns(tmp_path: Path):
    csv_path = tmp_path / "traffic.csv"
    csv_path.write_text(
        "\n".join(
            [
                "Date,Socrata Users,Geohub Users,Combined Users",
                "09/25/2014,203,,",
                "08/07/2017,386,193,579",
            ]
        ),
        encoding="utf-8",
    )

    records = load_traffic_dataset(csv_path)

    assert records[0].visit_date.isoformat() == "2014-09-25"
    assert records[0].user_count == 203
    assert records[1].user_count == 579
