def safe_csv_cell(value):
    text = "" if value is None else str(value)
    # Spreadsheet programs may execute cells that begin with formula characters.
    return "'" + text if text.lstrip().lstrip("\ufeff").lstrip().startswith(("=", "+", "-", "@")) else text
