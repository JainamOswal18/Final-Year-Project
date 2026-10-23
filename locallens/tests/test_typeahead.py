from locallens.nlu.typeahead import complete


def withs(items):
    return [i["with"].lower() for i in items]


def test_finishes_a_column_name(sreg):
    items = complete("show sales by cat", sreg)
    assert "category" in withs(items) and all(i["replace"] == "cat" for i in items)


def test_finishes_two_words_of_a_phrase(sreg):
    items = complete("profit by customer re", sreg)
    assert any(i["with"].lower().startswith("customer region") and i["replace"] == "customer re" for i in items)


def test_finishes_a_category_value(sreg):
    items = complete("sales for tech", sreg)
    assert any(i["with"] == "Technology" and i["kind"] == "value" for i in items)


def test_metric_names_come_before_values(sreg):
    items = complete("sa", sreg)
    kinds = [i["kind"] for i in items]
    assert kinds == sorted(kinds, key=lambda k: {"metric": 0, "category": 1, "date": 2, "value": 3}[k])


def test_nothing_for_short_or_finished_input(sreg):
    assert complete("", sreg) == [] and complete("s", sreg) == [] and complete("sales by ", sreg) == []
    assert complete("category", sreg) == []             # already typed in full: nothing longer to offer
    assert complete("zzzz", sreg) == []


def test_at_most_eight_and_no_repeats(sreg):
    items = complete("co", sreg)
    assert len(items) <= 8 and len(withs(items)) == len(set(withs(items)))
