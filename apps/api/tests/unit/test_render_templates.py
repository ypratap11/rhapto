from __future__ import annotations

import html
import re
import zipfile
from io import BytesIO

from helpers import demo_resume

from rhapto.engine.render.docx import render_docx
from rhapto.engine.render.templates import DEFAULT_TEMPLATE, TEMPLATES, template_for
from rhapto.models.profile.blocks import Block


def _blocks() -> dict[str, Block]:
    ids = {e.source_block_id for s in demo_resume().sections for e in s.entries}
    ids |= {b.source_block_id for s in demo_resume().sections for e in s.entries for b in e.bullets}
    ids |= {b.source_block_id for b in demo_resume().summary}
    return {i: Block(id=i, type="achievement", content="x") for i in ids}


def _paragraphs(data: bytes) -> list[tuple[str, str, bool]]:
    """(text, alignment, any-bold) per non-empty paragraph, in document order."""
    x = zipfile.ZipFile(BytesIO(data)).read("word/document.xml").decode("utf-8")
    out: list[tuple[str, str, bool]] = []
    for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S):
        text = html.unescape("".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", p, re.S))).strip()
        if not text:
            continue
        align = re.search(r'<w:jc w:val="([^"]+)"', p)
        out.append((text, align.group(1) if align else "left", "<w:b/>" in p))
    return out


def test_no_style_renders_the_classic_layout() -> None:
    """A profile that asks for nothing must render exactly as it did before templates existed."""
    plain = _paragraphs(render_docx(demo_resume(), _blocks()))
    classic = _paragraphs(render_docx(demo_resume(), _blocks(), {"template": "classic"}))
    assert plain == classic


def test_an_unknown_template_falls_back_rather_than_failing_the_run() -> None:
    """A typo in a profile must not fail a run that already spent its LLM calls and passed every
    guardrail -- by the time the renderer runs, everything expensive is done."""
    assert template_for({"template": "no-such-layout"}) is TEMPLATES[DEFAULT_TEMPLATE]
    assert template_for(None) is TEMPLATES[DEFAULT_TEMPLATE]
    assert template_for({"template": 7}) is TEMPLATES[DEFAULT_TEMPLATE]


def test_classic_headings_are_uppercase_and_left_aligned() -> None:
    paras = _paragraphs(render_docx(demo_resume(), _blocks(), {"template": "classic"}))
    assert any(t == "EXPERIENCE" for t, _a, _b in paras)
    assert paras[0][1] == "left"


def test_executive_centres_the_name_in_caps() -> None:
    paras = _paragraphs(render_docx(demo_resume(), _blocks(), {"template": "executive"}))
    name, align, bold = paras[0]
    assert align == "center"
    assert bold
    assert name == name.upper()


def test_executive_renames_the_sections() -> None:
    paras = [
        t
        for t, _a, _b in _paragraphs(
            render_docx(demo_resume(), _blocks(), {"template": "executive"})
        )
    ]
    assert "Professional Experience" in paras
    assert "EXPERIENCE" not in paras


def test_executive_bolds_the_bullet_lead_in() -> None:
    """The label the composer writes is what makes this layout scan; the template bolds it."""
    resume = demo_resume()
    entry = resume.sections[0].entries[0]
    entry.bullets[0].text = "Executive decisions. Drove the go/no-go with the VP Finance."
    data = render_docx(resume, _blocks(), {"template": "executive"})
    x = zipfile.ZipFile(BytesIO(data)).read("word/document.xml").decode("utf-8")
    para = next(p for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S) if "Executive decisions." in p)
    runs = re.findall(r"<w:r>(.*?)</w:r>", para, re.S)
    lead = next(r for r in runs if "Executive decisions." in r)
    assert "<w:b/>" in lead, "the label sentence should be bold"
    rest = next(r for r in runs if "VP Finance" in r)
    assert "<w:b/>" not in rest, "the detail should not be bold"


def test_a_bullet_without_a_label_is_not_arbitrarily_bolded() -> None:
    """A long first clause is prose, not a label -- bolding it would look like a mistake."""
    resume = demo_resume()
    entry = resume.sections[0].entries[0]
    entry.bullets[0].text = (
        "Led a very long opening clause that runs well past any reasonable label length "
        "before it ever reaches a full stop. And then continues."
    )
    data = render_docx(resume, _blocks(), {"template": "executive"})
    x = zipfile.ZipFile(BytesIO(data)).read("word/document.xml").decode("utf-8")
    para = next(p for p in re.findall(r"<w:p[ >].*?</w:p>", x, re.S) if "very long opening" in p)
    assert "<w:b/>" not in para
