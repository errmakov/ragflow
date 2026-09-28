import asyncio
import types

import pytest

"""Regression tests for issue #18293.

HierarchyTitleChunker flushes its text run on every non-text record
(image/table). Body text that follows the media under the same heading
must keep its ancestor heading path, and headings carried over the
media must not be re-emitted as heading-only chunks.
"""

from test_title_chunker_position_int import _load_title_chunker_with_stubs

TWO_LEVELS = [[r"^# ", r"^## "]]


def _text(text):
    return {"text": text, "doc_type_kwd": "text"}


def _image(text):
    return {"text": text, "doc_type_kwd": "image", "img_id": text}


def _chunk_texts(items, *, hierarchy, include_heading_content):
    with _load_title_chunker_with_stubs() as (common_module, hierarchy_module):

        async def _restore_previews(*_a, **_k):
            return None

        common_module.restore_pdf_text_previews = _restore_previews

        from_upstream = types.SimpleNamespace(
            output_format="chunks",
            json_result=None,
            markdown_result=None,
            text_result=None,
            html_result=None,
            chunks=items,
            file=None,
            name="doc",
        )

        param = common_module.TitleChunkerParam()
        param.method = "hierarchy"
        param.hierarchy = hierarchy
        param.levels = TWO_LEVELS
        param.include_heading_content = include_heading_content
        param.root_chunk_as_heading = False
        param.chunk_token_cap = 0

        process = common_module.ProcessBase(None, "title_chunker", param)
        process._canvas = types.SimpleNamespace(_doc_id="doc", _tenant_id="tenant")
        process._outputs = {}

        asyncio.run(hierarchy_module.HierarchyTitleChunker(process, from_upstream).invoke())
        return [chunk["text"] for chunk in process._outputs.get("chunks", [])]


@pytest.mark.parametrize(
    ("hierarchy", "include_heading_content", "items", "expected"),
    [
        pytest.param(
            1,
            True,
            [_text("# Chapter 1"), _text("before figure"), _image("figure"), _text("after figure")],
            ["# Chapter 1\nbefore figure\n", "figure", "# Chapter 1\nafter figure\n"],
            id="single-level",
        ),
        pytest.param(
            2,
            True,
            [
                _text("# Chapter 1"),
                _text("## 1.1 Background"),
                _text("before figure"),
                _image("figure"),
                _text("after figure"),
                _text("## 1.2 Goals"),
                _text("goals body"),
            ],
            [
                "# Chapter 1\n## 1.1 Background\nbefore figure\n",
                "figure",
                "# Chapter 1\n## 1.1 Background\nafter figure\n",
                "# Chapter 1\n## 1.2 Goals\ngoals body\n",
            ],
            id="nested-ancestors-and-following-sibling",
        ),
        pytest.param(
            2,
            False,
            [
                _text("# Chapter 1"),
                _text("chapter intro"),
                _text("## 1.1 Background"),
                _text("before figure"),
                _image("figure"),
                _text("after figure"),
            ],
            [
                "# Chapter 1\nchapter intro\n## 1.1 Background\nbefore figure\n",
                "figure",
                "# Chapter 1\n## 1.1 Background\nafter figure\n",
            ],
            id="leaf-only-without-include-heading-content",
        ),
        pytest.param(
            2,
            True,
            [
                _text("# Chapter 1"),
                _text("## 1.1 Background"),
                _text("before figures"),
                _image("figure A"),
                _image("figure B"),
                _text("after figures"),
            ],
            [
                "# Chapter 1\n## 1.1 Background\nbefore figures\n",
                "figure A",
                "figure B",
                "# Chapter 1\n## 1.1 Background\nafter figures\n",
            ],
            id="consecutive-media-emit-no-heading-only-chunk",
        ),
        pytest.param(
            1,
            True,
            [_image("cover"), _text("# Chapter 1"), _text("body")],
            ["cover", "# Chapter 1\nbody\n"],
            id="media-before-first-heading",
        ),
        pytest.param(
            1,
            True,
            [_text("# Chapter 1"), _image("figure"), _text("after figure")],
            ["# Chapter 1\n", "figure", "# Chapter 1\nafter figure\n"],
            id="media-directly-after-heading",
        ),
        pytest.param(
            1,
            True,
            [_text("# Chapter 1"), _text("body one"), _image("figure"), _text("# Chapter 2"), _text("body two")],
            ["# Chapter 1\nbody one\n", "figure", "# Chapter 2\nbody two\n"],
            id="new-top-level-heading-after-media",
        ),
        pytest.param(
            1,
            True,
            [
                _text("# Chapter 1"),
                _text("## 1.1 Background"),
                _text("background body"),
                _text("## 1.2 Goals"),
                _text("goals body"),
                _image("figure"),
                _text("after figure"),
            ],
            [
                "# Chapter 1\n## 1.1 Background\nbackground body\n## 1.2 Goals\ngoals body\n",
                "figure",
                "# Chapter 1\n## 1.2 Goals\nafter figure\n",
            ],
            id="closed-sibling-heading-is-not-carried",
        ),
    ],
)
def test_heading_path_survives_media(hierarchy, include_heading_content, items, expected):
    assert _chunk_texts(items, hierarchy=hierarchy, include_heading_content=include_heading_content) == expected
