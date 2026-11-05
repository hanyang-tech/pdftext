import dataclasses

import pytest

from pdftext import model
from pdftext.model import BBox, Figure, union_bbox
from pdftext.xmlwriter import PageEntry

CONTENT_TYPES = [
    model.RawPage,
    model.Word,
    model.Line,
    model.Region,
    model.Figure,
    model.Cell,
    model.Row,
    model.Table,
    model.Page,
    model.GridCell,
    model.GridNode,
    PageEntry,
]


@pytest.mark.parametrize("content_type", [*CONTENT_TYPES, model.RawChar], ids=lambda t: t.__name__)
def test_bbox_is_the_first_field_and_has_no_default(content_type):
    first = dataclasses.fields(content_type)[0]

    assert first.name == "bbox"
    assert first.default is dataclasses.MISSING
    assert first.default_factory is dataclasses.MISSING


@pytest.mark.parametrize("content_type", CONTENT_TYPES, ids=lambda t: t.__name__)
def test_model_types_are_frozen(content_type):
    assert content_type.__dataclass_params__.frozen


def test_a_figure_cannot_be_changed():
    figure = Figure(BBox(0, 0, 1, 1))

    with pytest.raises(dataclasses.FrozenInstanceError):
        figure.bbox = BBox(0, 0, 2, 2)  # type: ignore[misc]


def test_union_bbox_covers_all_boxes():
    boxes = [BBox(0, 5, 10, 20), BBox(-3, 6, 4, 30)]

    assert union_bbox(boxes) == (-3, 5, 10, 30)


def test_union_bbox_rejects_no_boxes():
    with pytest.raises(ValueError, match="no boxes"):
        union_bbox([])
