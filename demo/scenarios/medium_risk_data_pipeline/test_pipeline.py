from pipeline import process_records

def test_process_records():
    records = [
        {"id": 1, "status": "active"},
        {"id": 2, "status": "inactive"},
        {"id": 3, "status": "active"}
    ]
    
    result = process_records(records)
    
    assert len(result) == 2
    assert result[0]["id"] == 1
    assert result[1]["id"] == 3
