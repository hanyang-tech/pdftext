"""AC-3: the shipped XSD accepts the documented shape and refuses everything else."""

from importlib.resources import files
from pathlib import Path

import pytest
from lxml import etree

SCHEMA = etree.XMLSchema(etree.parse(Path(str(files("pdftext") / "schema" / "pdftext.xsd"))))

BOX = "1.00 2.00 3.00 4.00"
PAGE = (
    f'<page schema-version="1" number="1" bbox="{BOX}" status="ok"'
    ' replaced-chars="2" overflow="true">'
    f'<region bbox="{BOX}"><line bbox="{BOX}" rotation="90">'
    f'<word bbox="{BOX}" rotation="90">a</word></line></region>'
    f'<table bbox="{BOX}" rows="1" cols="1" detection="text" inferred="true">'
    f'<row bbox="{BOX}" index="0">'
    f'<cell bbox="{BOX}" col="0" colspan="2" rowspan="2" overflow="true">'
    f'<figure bbox="{BOX}"/></cell></row></table>'
    f'<figure bbox="{BOX}"/></page>'
)
DOC_PAGE = f'<page number="1" href="page-0001.xml" status="ok" bbox="{BOX}"/>'
DOCUMENT = f'<document schema-version="1" pages="1">{DOC_PAGE}</document>'


def is_valid(xml: str) -> bool:
    return SCHEMA.validate(etree.fromstring(xml))


@pytest.mark.parametrize("xml", [PAGE, DOCUMENT], ids=["page", "document"])
def test_accepts_a_page_and_a_document_that_use_every_element_and_attribute(xml):
    assert is_valid(xml)


@pytest.mark.parametrize(
    ("valid", "old", "new"),
    [
        (PAGE, f'<word bbox="{BOX}" rotation="90">', '<word rotation="90">'),
        (PAGE, f'<figure bbox="{BOX}"/></cell>', "<figure/></cell>"),
        (PAGE, 'bbox="1.00 2.00 3.00 4.00" status', 'bbox="1.0 2.00 3.00 4.00" status'),
        (PAGE, 'bbox="1.00 2.00 3.00 4.00" status', 'bbox="1.00 2.00 3.00" status'),
        (PAGE, 'bbox="1.00 2.00 3.00 4.00" status', 'bbox="1.00 2.00 3.00 nan" status'),
        (PAGE, 'status="ok"', 'status="done"'),
        (PAGE, 'schema-version="1"', 'schema-version="2"'),
        (PAGE, 'rotation="90">a', 'rotation="0">a'),
        (PAGE, 'rotation="90">a', 'rotation="360">a'),
        (PAGE, 'overflow="true">', 'overflow="false">'),
        (PAGE, 'replaced-chars="2"', 'replaced-chars="0"'),
        (PAGE, 'col="0"', 'col="-1"'),
        (PAGE, 'detection="text"', 'detection="guess"'),
        (PAGE, f'<row bbox="{BOX}" index="0">', f'<row bbox="{BOX}">'),
        (PAGE, f'<figure bbox="{BOX}"/></page>', f'<figure bbox="{BOX}"/><para/></page>'),
        (PAGE, ">a</word>", "><b/></word>"),
        (PAGE, f'<line bbox="{BOX}" rotation="90">', f'<line bbox="{BOX}" rotation="90">text'),
        (PAGE, f'<region bbox="{BOX}">', f'<region bbox="{BOX}" lang="en">'),
        (DOCUMENT, 'href="page-0001.xml"', 'href="../page-0001.xml"'),
        (DOCUMENT, 'href="page-0001.xml"', 'href="page-1.xml"'),
        (DOCUMENT, 'number="1" href', "href"),
        (DOCUMENT, 'pages="1"', 'pages="0"'),
        (DOCUMENT, DOC_PAGE, ""),
    ],
    ids=[
        "word-without-bbox",
        "figure-without-bbox",
        "bbox-one-decimal",
        "bbox-three-numbers",
        "bbox-nan",
        "unknown-status",
        "unknown-schema-version",
        "rotation-zero",
        "rotation-360",
        "overflow-false",
        "replaced-chars-zero",
        "negative-column",
        "unknown-detection",
        "row-without-index",
        "unknown-element",
        "markup-inside-a-word",
        "text-outside-a-word",
        "unknown-attribute",
        "href-with-a-path",
        "href-without-padding",
        "document-page-without-number",
        "zero-pages",
        "no-pages-listed",
    ],
)
def test_refuses_a_page_or_document_that_breaks_the_documented_shape(valid, old, new):
    assert old in valid
    assert not is_valid(valid.replace(old, new, 1))
