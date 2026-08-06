from kaoyan_ai.question_enrichment import (
    question_is_displayable,
    question_needs_image,
)


def test_plain_graph_wording_does_not_require_an_image():
    question = {"content": "在有向图中，顶点的入度与出度之和是什么？"}
    assert question_needs_image(question) is False
    assert question_is_displayable(question) is True


def test_image_dependent_question_is_hidden_without_an_image():
    question = {"content": "根据下图回答该网络中有几个冲突域。"}
    assert question_needs_image(question) is True
    assert question_is_displayable(question) is False


def test_image_dependent_question_is_visible_with_an_image():
    question = {
        "content": "根据下图回答该网络中有几个冲突域。",
        "image_url": "/static/question_images/example.png",
    }
    assert question_is_displayable(question) is True
