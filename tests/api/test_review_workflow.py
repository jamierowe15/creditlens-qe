"""Underwriter workflow and audit trail: a state machine. REFERRED is the only state that can move;
every move is recorded. Tests cover each valid transition and each forbidden one."""
import threading
from decimal import Decimal

import pytest

from testdata.builders import an_applicant

pytestmark = pytest.mark.api


@pytest.mark.req("CL-US11", "CL-US12")
def test_approve_referred_application(api, referred_application):
    app_id = referred_application["id"]
    r = api.review(app_id, approve=True, underwriter="  J. Rowe  ", note="Verified two recent pay stubs")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["status"] == "APPROVED"
    assert body["decidedBy"] == "J. Rowe", "underwriter name should be trimmed"
    assert Decimal(str(body["approvedAmount"])) == Decimal(str(referred_application["requestedAmount"]))

    trail = api.audit(app_id).json()
    assert [e["action"] for e in trail] == ["AUTO_DECISION", "MANUAL_REVIEW"]
    assert trail[1]["fromStatus"] == "REFERRED" and trail[1]["toStatus"] == "APPROVED"
    assert trail[1]["note"] == "Verified two recent pay stubs"
    assert all(e["rulesVersion"] == "2026.11-v1" for e in trail)


@pytest.mark.req("CL-US11", "CL-US12")
def test_decline_referred_application_clears_amount(api, referred_application):
    r = api.review(referred_application["id"], approve=False, note="Income could not be verified")
    assert r.status_code == 200
    assert r.json()["status"] == "DECLINED"
    assert r.json()["approvedAmount"] is None
    assert api.audit(referred_application["id"]).json()[-1]["toStatus"] == "DECLINED"


@pytest.mark.req("CL-US11")
@pytest.mark.parametrize("persona,status", [("prime borrower", "APPROVED"), ("subprime borrower", "DECLINED")])
def test_only_referred_can_be_reviewed(api, persona, status):
    created = api.submit(an_applicant().persona(persona).build()).json()
    assert created["status"] == status
    r = api.review(created["id"], approve=True)
    assert r.status_code == 409
    assert r.json()["title"] == "Invalid state"
    assert len(api.audit(created["id"]).json()) == 1, "a rejected review must not write an audit row"


@pytest.mark.req("CL-US11")
def test_application_cannot_be_reviewed_twice(api, referred_application):
    assert api.review(referred_application["id"], approve=True).status_code == 200
    assert api.review(referred_application["id"], approve=False).status_code == 409


@pytest.mark.req("CL-US11", "CL-US13")
@pytest.mark.parametrize("body,field", [
    ({"approve": True, "underwriter": "J. Rowe", "note": "   "}, "note"),
    ({"approve": True, "underwriter": "", "note": "ok"}, "underwriter"),
    ({"underwriter": "J. Rowe", "note": "ok"}, "approve"),
    ({"approve": True, "underwriter": "J. Rowe", "note": "x" * 501}, "note"),
])
def test_review_requires_name_and_note(api, referred_application, body, field):
    r = api.post(f"/api/applications/{referred_application['id']}/review", body)
    assert r.status_code == 400
    assert field in r.json()["errors"]
    assert api.get_application(referred_application["id"]).json()["status"] == "REFERRED"


@pytest.mark.req("CL-US11", "CL-US12")
def test_concurrent_reviews_exactly_one_wins(api, referred_application):
    """Two underwriters click at the same moment. Optimistic locking must let exactly one through."""
    results = []
    barrier = threading.Barrier(2)

    def worker(approve):
        barrier.wait()
        results.append(api.review(referred_application["id"], approve=approve,
                                  underwriter=f"UW-{'A' if approve else 'D'}").status_code)

    threads = [threading.Thread(target=worker, args=(a,)) for a in (True, False)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    assert sorted(results) == [200, 409], results
    assert len(api.audit(referred_application["id"]).json()) == 2


@pytest.mark.req("CL-US12")
def test_auto_decision_audit_row_explains_itself(api):
    created = api.submit(an_applicant().persona("thin-file student").build()).json()
    trail = api.audit(created["id"]).json()
    assert len(trail) == 1
    assert trail[0]["action"] == "AUTO_DECISION" and trail[0]["fromStatus"] is None
    assert trail[0]["actor"].startswith("CreditLens Engine")
    assert "EMP2" in trail[0]["note"]
