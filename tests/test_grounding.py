from src.job_agent.grounding import extract_numbers, ungrounded_numbers


def test_extract_numbers_normalises():
    assert extract_numbers("Grew 30% in 2019, 1,000 users, 2.5 avg, eighteen years, 1st, 2m") == \
        {"30", "2019", "1000", "2.5", "18"}
    assert extract_numbers(None) == set() and extract_numbers("") == set()


def test_ungrounded_numbers_finds_only_unsupported_figures():
    cv = "Led 30 engineers. Eighteen years of delivery."
    posting = "Salary 60,000 and 5 days a week"
    out = "Led 30 engineers for 18 years, cut costs by 40% and 25% for a 60000 role in 5 days"
    assert ungrounded_numbers(out, [cv, posting, None]) == ["25", "40"]


def test_ungrounded_numbers_empty_when_all_supported():
    assert ungrounded_numbers("Led 30 engineers", ["30 engineers"]) == []
    assert ungrounded_numbers("no figures at all", []) == []


def test_unsupported_when_no_sources():
    assert ungrounded_numbers("grew 12%", []) == ["12"]
