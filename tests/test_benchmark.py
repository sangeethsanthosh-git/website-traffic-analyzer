from pathlib import Path

from app import (
    build_website_benchmark_summary,
    build_website_search_analysis,
    load_website_benchmark_dataset,
    search_website_benchmark,
)


def test_load_website_benchmark_dataset(tmp_path: Path):
    csv_path = tmp_path / "benchmark.csv"
    csv_path.write_text(
        "\n".join(
            [
                "source_rank,website,monthly_visits_display,monthly_visits_estimate,mom_change_pct,yearly_change_pct,data_month,source",
                "1,google.com,78.2B,78200000000,-8.78,3.88,February 2025,Similarweb",
                "2,chatgpt.com,5.4B,5400000000,-6.50,36.00,February 2025,Similarweb",
            ]
        ),
        encoding="utf-8",
    )

    records = load_website_benchmark_dataset(csv_path)

    assert len(records) == 2
    assert records[0].website == "google.com"
    assert records[1].monthly_visits_estimate == 5_400_000_000


def test_build_website_benchmark_summary():
    records = load_website_benchmark_dataset(
        Path("data/top_websites_worldwide_feb_2025.csv")
    )

    summary = build_website_benchmark_summary(records)

    assert summary.site_count == 20
    assert summary.data_month == "February 2025"
    assert summary.top_website == "google.com"
    assert summary.top_yearly_gainer == "gemini.google.com"


def test_search_website_benchmark_supports_partial_match():
    records = load_website_benchmark_dataset(
        Path("data/top_websites_worldwide_feb_2025.csv")
    )

    matches = search_website_benchmark(records, "amazon")

    assert matches
    assert matches[0].website == "amazon.com"


def test_build_website_search_analysis_returns_selected_site():
    records = load_website_benchmark_dataset(
        Path("data/top_websites_worldwide_feb_2025.csv")
    )

    analysis = build_website_search_analysis(records, "https://www.reddit.com/")

    assert analysis.selected_website == "reddit.com"
    assert analysis.selected_rank == 7
    assert analysis.matching_count == 1
