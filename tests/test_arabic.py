from sovereign.arabic import normalize_arabic, split_sentences, tokenize_text


def test_normalize_removes_diacritics_and_unifies_letters():
    assert normalize_arabic("مُحَمَّدٌ") == "محمد"
    assert normalize_arabic("أحمد إبراهيم آدم") == "احمد ابراهيم ادم"
    assert normalize_arabic("مدرسة على مؤمن") == "مدرسه علي مومن"


def test_tokenize_arabic_keeps_words_and_drops_punctuation():
    assert tokenize_text("الذكاءُ الاصطناعي، والتعلّم!") == ["الذكاء", "الاصطناعي", "والتعلم"]


def test_tokenize_english_is_unchanged():
    assert tokenize_text("Hello, World 42") == ["Hello,", "World", "42"]


def test_split_sentences_handles_arabic_question_mark():
    assert split_sentences("ما هذا؟ هذا اختبار. نعم!") == ["ما هذا", "هذا اختبار", "نعم"]
