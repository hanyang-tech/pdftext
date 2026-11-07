from collections.abc import Callable
from importlib.resources import files
from pathlib import Path

import pytest
from lxml import etree

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures() -> Path:
    return FIXTURES


@pytest.fixture(scope="session")
def assert_valid() -> Callable[[bytes], None]:
    """Check XML bytes against the XSD shipped with the package."""
    schema_file = Path(str(files("pdftext") / "schema" / "pdftext.xsd"))
    schema = etree.XMLSchema(etree.parse(schema_file))

    def check(xml: bytes) -> None:
        document = etree.fromstring(xml)
        assert schema.validate(document), schema.error_log.last_error

    return check
