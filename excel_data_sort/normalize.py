from .models import NormalizedSheet, is_empty


def normalize(sheet, template):
    """Unmerge, remove empty rows/columns, then apply visibility options.

    The input is never mutated. Original coordinates and blank boundaries remain
    available for extraction after compaction.
    """
    width = max((len(row) for row in sheet.rows), default=0)
    rows = [list(row) + [None] * (width - len(row)) for row in sheet.rows]
    if template.merge_mode == "fill":
        for first_row, last_row, first_column, last_column in sheet.merges:
            value = rows[first_row - 1][first_column - 1]
            for row in range(first_row - 1, min(last_row, len(rows))):
                for column in range(first_column - 1, min(last_column, width)):
                    rows[row][column] = value
    # In anchor mode only the original top-left value remains after unmerging.
    blank_rows = {index + 1 for index, row in enumerate(rows) if all(is_empty(value) for value in row)}
    row_numbers = [index + 1 for index in range(len(rows)) if index + 1 not in blank_rows]
    column_numbers = [column + 1 for column in range(width)
                      if any(not is_empty(rows[row - 1][column]) for row in row_numbers)]
    if not template.include_hidden_rows:
        row_numbers = [row for row in row_numbers if row not in sheet.hidden_rows]
    if not template.include_hidden_columns:
        column_numbers = [column for column in column_numbers if column not in sheet.hidden_columns]
    return NormalizedSheet(
        sheet.name,
        [[rows[row - 1][column - 1] for column in column_numbers] for row in row_numbers],
        row_numbers, column_numbers, blank_rows,
    )
