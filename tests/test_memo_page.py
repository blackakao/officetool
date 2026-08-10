from ui.pages.memo_page import content_preview, filter_memos, normalize_memo_data


def test_invalid_memo_storage_is_normalized():
    assert normalize_memo_data(None) == {"version": 1, "tags": [], "memos": []}


def test_tags_are_trimmed_and_deduplicated():
    data = normalize_memo_data({"tags": [" 업무 ", "업무", "", "중요"], "memos": []})
    assert data["tags"] == ["업무", "중요"]


def test_content_preview_collapses_whitespace_and_limits_length():
    assert content_preview("짧은\n내용") == "짧은 내용"
    assert content_preview("12345678901") == "1234567890…"


def test_memos_can_be_searched_across_all_fields_and_filtered_by_tag():
    memos = [
        {"title": "회의", "tag": "업무", "content": "다음 주 일정"},
        {"title": "장보기", "tag": "개인", "content": "우유와 계란"},
    ]
    assert filter_memos(memos, "일정") == [memos[0]]
    assert filter_memos(memos, "", "개인") == [memos[1]]
    assert filter_memos(memos, "회의", "개인") == []
