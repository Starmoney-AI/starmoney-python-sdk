from starmoney import PaymentResponseStatus


def test_members_compare_equal_to_raw_json_values():
    assert PaymentResponseStatus.ALREADY_FAILED == "already_failed"
    assert PaymentResponseStatus("already_in_progress") is PaymentResponseStatus.ALREADY_IN_PROGRESS


def test_parse_is_case_insensitive():
    assert PaymentResponseStatus.parse("ALREADY_COMPLETED") is PaymentResponseStatus.ALREADY_COMPLETED


def test_is_stored_outcome():
    assert PaymentResponseStatus.VALIDATED.is_stored_outcome is False
    assert all(
        s.is_stored_outcome
        for s in PaymentResponseStatus
        if s is not PaymentResponseStatus.VALIDATED
    )


def test_account_type_is_the_closed_wire_set():
    from starmoney import AccountType

    assert [t.value for t in AccountType] == ["individual", "business"]
    assert AccountType("individual") is AccountType.INDIVIDUAL
