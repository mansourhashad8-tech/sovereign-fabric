from sovereign.intent import parse_intent


def test_arabic_summary_request():
    intent = parse_intent("لخص: هذا نص طويل")
    assert intent["goal_type"] == "summary"
    assert intent["text"] == "هذا نص طويل"


def test_arabic_report_request():
    assert parse_intent("اكتب تقريرا عن الكلمات")["goal_type"] == "markdown"


def test_arabic_count_request():
    assert parse_intent("عدد الكلمات في النص")["goal_type"] == "counts"


def test_arabic_tokenize_request():
    assert parse_intent("قسّم النص إلى كلمات")["goal_type"] == "tokens"


def test_english_request():
    assert parse_intent("summarize this text")["goal_type"] == "summary"


def test_unknown_defaults_to_markdown_and_says_so():
    intent = parse_intent("hello there")
    assert intent["goal_type"] == "markdown"
    assert intent["matched"] is None
