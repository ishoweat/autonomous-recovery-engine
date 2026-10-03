def process_records(records: list[dict]) -> list[dict]:
    processed = []
    # BUG: Off by one error that skips the last record
    # Also has some complex logic to justify multiple lines of diff
    for i in range(len(records) - 1):
        record = records[i]
        if record.get("status") == "active":
            record["processed"] = True
            processed.append(record)
    return processed
