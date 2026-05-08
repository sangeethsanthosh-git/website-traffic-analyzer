from datetime import date

from app import TrafficRecord, build_summary, generate_chart


def test_build_summary_with_records():
    records = [
        TrafficRecord(date(2025, 4, 1), 120),
        TrafficRecord(date(2025, 4, 2), 160),
        TrafficRecord(date(2025, 4, 3), 210),
    ]

    summary = build_summary(records)

    assert summary.total_days == 3
    assert summary.total_users == 490
    assert round(summary.average_users, 2) == 163.33
    assert summary.peak_users == 210
    assert summary.peak_date == "03 Apr 2025"
    assert summary.trend_label == "Increasing"


def test_build_summary_without_records():
    summary = build_summary([])

    assert summary.total_days == 0
    assert summary.total_users == 0
    assert summary.trend_label == "Waiting for data"
    assert summary.change_percent is None


def test_generate_chart_returns_base64_string():
    records = [
        TrafficRecord(date(2025, 4, 1), 80),
        TrafficRecord(date(2025, 4, 2), 100),
        TrafficRecord(date(2025, 4, 3), 130),
        TrafficRecord(date(2025, 4, 4), 125),
    ]

    chart_image = generate_chart(records)

    assert isinstance(chart_image, str)
    assert len(chart_image) > 100
