"""Method locations whose bodies intersect changed lines (via PyDriller)."""


def extract_methods(file):
    try:
        if not file.language_supported:
            return {"method_status": "unsupported", "changed_methods": []}
        parsed = file.diff_parsed
        rows = []
        for version, methods, lines in (
            ("before", file.methods_before, {line for line, _ in parsed["deleted"]}),
            ("after", file.methods, {line for line, _ in parsed["added"]}),
        ):
            for method in methods:
                if any(method.start_line <= line <= method.end_line for line in lines):
                    rows.append({"name": method.name, "signature": method.long_name,
                                 "version": version, "start_line": method.start_line,
                                 "end_line": method.end_line})
        rows.sort(key=lambda row: (row["signature"], row["version"], row["start_line"]))
        return {"method_status": "available" if rows else "none", "changed_methods": rows}
    except Exception:
        # Parsing an unsupported source dialect must not discard valid file stats.
        return {"method_status": "error", "changed_methods": []}
