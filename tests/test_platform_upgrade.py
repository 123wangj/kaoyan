from pathlib import Path

from kaoyan_ai import api


ROOT = Path(__file__).resolve().parents[1]


def test_question_paging_returns_catalog_metadata_and_favorite_filter(monkeypatch):
    questions = [
        {"id": "q1", "subject": "数据结构", "year": "2025"},
        {"id": "q2", "subject": "数据结构", "year": "2024"},
        {"id": "q3", "subject": "操作系统", "year": "2025"},
    ]
    monkeypatch.setattr(api, "_load_questions_cached", lambda: questions)

    result = api.get_questions_paged(
        page=1,
        page_size=10,
        subject="数据结构",
        year="all",
        status="all",
        favorite_ids="q2",
        user_id="ignored",
        user="alice",
    )

    assert [item["id"] for item in result["items"]] == ["q2"]
    assert result["total"] == 1
    assert result["filter_options"]["catalog_total"] == 3
    assert result["filter_options"]["subject_counts"]["数据结构"] == 2
    assert result["filter_options"]["years"] == ["2025", "2024"]


def test_frontend_uses_paged_questions_and_security_runtime():
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    runtime_js = (ROOT / "static" / "app-runtime.js").read_text(encoding="utf-8")
    index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    assert "/question-bank/paged?" in app_js
    assert "fetch('/question-bank/all')" not in app_js
    assert "KaoyanRuntime.renderMarkdown" in app_js
    assert "scheduleQuestionNoteAutosave" in app_js
    assert "allowedTags" in runtime_js
    assert "compactDrawing" in runtime_js
    assert "questionPagination" in index_html
    assert "app-runtime.js" in index_html


def test_chat_stream_does_not_buffer_the_whole_model_response():
    source = (ROOT / "kaoyan_ai" / "api.py").read_text(encoding="utf-8")
    runtime_source = (ROOT / "kaoyan_ai" / "agent_runtime.py").read_text(encoding="utf-8")
    assert "return list(llm.generate_stream" not in source
    assert "answer_chunk_sink=emit_answer_chunk" in source
    assert "with stream_llm_chunks(" in runtime_source
    assert "await asyncio.to_thread(stream_queue.get)" in source


def test_offline_shell_and_browser_regression_suite_exist():
    service_worker = (ROOT / "static" / "sw.js").read_text(encoding="utf-8")
    browser_test = (ROOT / "tests" / "browser" / "responsive.spec.mjs").read_text(
        encoding="utf-8"
    )

    assert "caches.open" in service_worker
    assert "notificationclick" in service_worker
    assert "desktop" in (ROOT / "playwright.config.mjs").read_text(encoding="utf-8")
    assert "question cards keep a stable non-overlapping grid" in browser_test


def test_school_selection_has_a_first_class_navigation_and_sourced_result_ui():
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")
    styles = (ROOT / "static" / "styles.css").read_text(encoding="utf-8")

    assert 'data-view="school-selection"' in index_html
    assert 'id="schoolSelectionForm"' in index_html
    assert "/school-selection/runs" in app_js
    assert "EventSource" in app_js
    assert "取消任务" in app_js
    assert "生成 14 天提升计划" in app_js
    assert 'data-controller-url="/static/views/school-selection.js' in index_html
    assert "source_type" in app_js
    assert ".school-selection-layout" in styles


def test_daily_push_is_backed_by_persistent_daily_store():
    api_source = (ROOT / "kaoyan_ai" / "api.py").read_text(encoding="utf-8")
    store_source = (ROOT / "kaoyan_ai" / "daily_push_store.py").read_text(encoding="utf-8")

    assert "daily_push_store.get_or_create" in api_source
    assert '"generated_for": today' in api_source
    assert "os.O_EXCL" in store_source
    assert "os.replace" in store_source


def test_simulator_prediction_prompts_follow_the_current_knowledge_type():
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")

    assert "predictionPrompts" in app_js
    assert "先预测排序过程" in app_js
    assert "先预测缺页变化" in app_js
    assert "先预测调度结果" in app_js
    assert "先预测地址划分" in app_js
    assert "先预测编码结果" in app_js
    assert "先预测子网范围" in app_js
    assert "先预测流水线性能" in app_js
    assert "先预测输出顺序" in app_js
    assert "页框增加后，缺页率会下降" not in app_js


def test_knowledge_check_opens_questions_inside_the_visible_question_view():
    app_js = (ROOT / "static" / "app.js").read_text(encoding="utf-8")
    index_html = (ROOT / "static" / "index.html").read_text(encoding="utf-8")

    click_handler = app_js.split(
        "body.querySelectorAll('[data-kv-question]')", 1
    )[1].split("function initKnowledgeVisualization", 1)[0]
    assert click_handler.index("switchView('question-bank-detail')") < click_handler.index(
        "openQuestion(question)"
    )
    assert "关联题目检验" in index_html
    assert ">真题检验</button>" not in index_html
