"""Paging, filtering and dashboard numbers. The key idea: two endpoints that describe the same data
must reconcile (stats counts == list totals), just like balancing a till at the end of a shift."""
import math

import pytest

from testdata.builders import an_applicant

pytestmark = pytest.mark.api


@pytest.mark.req("CL-US14")
def test_newest_first(api):
    ids = [api.submit(an_applicant().build()).json()["id"] for _ in range(3)]
    first_page = [a["id"] for a in api.list(page=0, size=3).json()["content"]]
    assert first_page == list(reversed(ids))


@pytest.mark.req("CL-US14")
@pytest.mark.parametrize("status", ["APPROVED", "REFERRED", "DECLINED"])
def test_filter_by_status(api, status):
    page = api.list(status=status, size=100).json()
    assert page["content"], f"expected seeded {status} applications"
    assert {a["status"] for a in page["content"]} == {status}


@pytest.mark.req("CL-US14")
@pytest.mark.parametrize("asked,expected", [(1000, 100), (0, 1), (-5, 1)])
def test_page_size_is_clamped(api, asked, expected):
    assert api.list(size=asked).json()["size"] == expected


@pytest.mark.req("CL-US14")
def test_negative_page_is_treated_as_first_page(api):
    assert api.list(page=-3).json()["page"] == 0


@pytest.mark.req("CL-US14", "CL-US13")
def test_unknown_status_filter_is_400(api):
    assert api.list(status="PENDING").status_code == 400


@pytest.mark.req("CL-US14")
def test_paging_visits_every_application_once(api):
    total = api.list(size=7).json()["totalElements"]
    seen, page = [], 0
    while True:
        p = api.list(page=page, size=7).json()
        seen += [a["id"] for a in p["content"]]
        page += 1
        if page >= p["totalPages"]:
            break
    assert len(seen) == len(set(seen)) == total


@pytest.mark.req("CL-US15")
def test_stats_reconcile_with_list(api):
    s = api.stats().json()
    counts = {st: api.list(status=st, size=1).json()["totalElements"] for st in ("APPROVED", "REFERRED", "DECLINED")}
    assert s["approved"] == counts["APPROVED"]
    assert s["referred"] == counts["REFERRED"]
    assert s["declined"] == counts["DECLINED"]
    assert s["total"] == sum(counts.values()) == api.list(size=1).json()["totalElements"]
    assert s["approvalRatePercent"] == math.floor(s["approved"] * 1000 / s["total"] + 0.5) / 10  # Java-style half-up


@pytest.mark.req("CL-US15")
def test_submitting_moves_the_right_counter(api):
    before = api.stats().json()
    api.submit(an_applicant().persona("subprime borrower").build())
    after = api.stats().json()
    assert after["declined"] == before["declined"] + 1
    assert after["total"] == before["total"] + 1
    assert after["approved"] == before["approved"]
