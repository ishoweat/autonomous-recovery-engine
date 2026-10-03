import re

with open("backend/orchestration/nodes.py", "r") as f:
    content = f.read()

# triage
content = re.sub(
    r'llm\.complete_json\(\s*system_prompt=',
    r'llm.complete_json(\n                model=get_settings().active_fast_model,\n                system_prompt=',
    content,
    count=1
)

# root_cause
content = re.sub(
    r'llm\.complete_json\(\s*system_prompt=',
    r'llm.complete_json(\n                model=get_settings().active_strong_model,\n                system_prompt=',
    content,
    count=1 # replace first match, which is root_cause now
)

with open("backend/orchestration/nodes.py", "w") as f:
    f.write(content)
