[#1] fixed: in `_cut` (src/pdftext/reading_order.py) the horizontal cut now needs `y_gap > 0` as well as `y_gap >= 1.0*size`. The vertical cut already implies a real gap, since `x_gap > y_gap >= 0`. With size 0 and no gap there is no cut, so `_partition` can't return an empty half and `_widest_gap` is never called on an empty list. The docstring of `_cut` says why. Cause confirmed: with size 0, `0 >= 0` made the cut happen with `y_mid = 0.0`.

CHANGED FILES:
- /Users/wiragamahantareja/Claude/Github/pdftext.worktrees/pdf-layout-xml-02c/src/pdftext/reading_order.py

CHECKS:
- uv run ruff format . then uv run ruff format --check .: pass
- uv run ruff check .: pass (All checks passed!)
- uv run mypy src: pass (no issues found)
- uv run pytest tests/test_reading_order.py tests/test_reading_order_edges.py tests/test_stage_stubs.py tests/test_pipeline.py tests/test_pipeline_order.py: pass, including the 3 previously failing tests (66 passed)
