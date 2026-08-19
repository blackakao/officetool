from ui.pages.incomplete_task_page import filter_tasks, normalize_task_data


def test_invalid_task_storage_is_normalized():
    assert normalize_task_data(None) == {"version": 1, "tasks": []}


def test_tasks_are_separated_by_completion_and_searched():
    tasks = [
        {"title": "서류 제출", "content": "구청에 제출", "completed_at": ""},
        {"title": "회의 준비", "content": "자료 정리", "completed_at": "2026-08-19 09:00"},
    ]
    assert filter_tasks(tasks, "구청", completed=False) == [tasks[0]]
    assert filter_tasks(tasks, "자료", completed=True) == [tasks[1]]
    assert filter_tasks(tasks, completed=False) == [tasks[0]]
