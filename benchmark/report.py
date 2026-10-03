import json
import os

def generate_report():
    if not os.path.exists("benchmark/results.json"):
        print("No results.json found.")
        return
        
    with open("benchmark/results.json") as f:
        results = json.load(f)
        
    total = len(results)
    if total == 0:
        print("No results to report.")
        return
        
    fixed = sum(1 for r in results if r.get("fixed"))
    fix_rate = fixed / total * 100
    
    total_time = sum(r.get("total_time", 0) for r in results)
    avg_time = total_time / total
    
    total_tokens = sum(r.get("tokens", 0) for r in results)
    
    # Decisions breakdown
    decisions = {}
    for r in results:
        dec = r.get("decision", "UNKNOWN")
        decisions[dec] = decisions.get(dec, 0) + 1
        
    md_content = f"""# Benchmark Results

## Summary
- **Total Cases**: {total}
- **Fixed**: {fixed} ({fix_rate:.1f}%)
- **Average Time**: {avg_time:.1f}s
- **Total Tokens**: {total_tokens}

## Decisions
"""
    for dec, count in decisions.items():
        md_content += f"- **{dec}**: {count}\n"
        
    md_content += """
## Case by Case
| Case | Fixed | Decision | Time (s) | Tokens | Retries |
|------|-------|----------|----------|--------|---------|
"""
    for r in results:
        md_content += f"| {r['case']} | {'✅' if r.get('fixed') else '❌'} | {r.get('decision')} | {r.get('total_time', 0)} | {r.get('tokens', 0)} | {r.get('retries', 0)} |\n"
        
    with open("benchmark/RESULTS.md", "w") as f:
        f.write(md_content)
        
    print("Report generated in benchmark/RESULTS.md")
    
if __name__ == "__main__":
    generate_report()
