from main import _list_detail_suppliers_for_request


def test_detail_suppliers_prefers_awarded_over_invites(monkeypatch):
    monkeypatch.setattr(
        "main.list_awarded_suppliers_for_request",
        lambda _rid: [{"code": "400-P0001", "name": "PROACC", "email": ""}],
    )
    monkeypatch.setattr(
        "main._list_selected_suppliers",
        lambda _rid: [
            {"code": "400-P0001", "name": "PROACC", "email": "a@proacc.com"},
            {"code": "400-J0001", "name": "JASON CORP", "email": "b@jason.com"},
        ],
    )
    monkeypatch.setattr("main._enrich_supplier_display_rows", lambda rows: rows)

    out = _list_detail_suppliers_for_request(58)
    assert len(out) == 1
    assert out[0]["code"] == "400-P0001"
    assert out[0]["name"] == "PROACC"


def test_detail_suppliers_falls_back_to_invites_when_no_award(monkeypatch):
    monkeypatch.setattr("main.list_awarded_suppliers_for_request", lambda _rid: [])
    invites = [
        {"code": "400-P0001", "name": "PROACC", "email": ""},
        {"code": "400-J0001", "name": "JASON CORP", "email": ""},
    ]
    monkeypatch.setattr("main._list_selected_suppliers", lambda _rid: invites)
    monkeypatch.setattr("main._enrich_supplier_display_rows", lambda rows: rows)

    out = _list_detail_suppliers_for_request(58)
    assert len(out) == 2
