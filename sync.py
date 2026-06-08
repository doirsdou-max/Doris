"""
每次运行从飞书多维表格拉取所有测评记录，生成 data.json
由 GitHub Action 定时触发
"""
import requests, json, os

APP_ID     = "cli_aa86aab221d19cc3"
APP_SECRET = "MekRJEDBLG8P5l1iDIPife5r4SEeRdV6"
APP_TOKEN  = "RGnGbWwcta1faasBMVOcc33Wnmc"
TABLE_ID   = "tblFvZE6KEjkIuBo"

def get_token():
    r = requests.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": APP_ID, "app_secret": APP_SECRET}
    )
    return r.json()["tenant_access_token"]

def get_field(f, k):
    v = f.get(k)
    if not v: return ""
    if isinstance(v, dict) and "value" in v:
        val = v["value"]
        if not val: return ""
        if isinstance(val[0], dict) and "text" in val[0]: return val[0]["text"]
        return str(val[0])
    if isinstance(v, list) and v:
        if isinstance(v[0], dict) and "text" in v[0]: return v[0]["text"]
        return str(v[0])
    return str(v)

def get_date(f):
    ts_field = f.get("填表时间")
    if not ts_field: return ""
    ts = None
    if isinstance(ts_field, dict) and "value" in ts_field:
        val = ts_field["value"]
        if val: ts = val[0]
    elif isinstance(ts_field, (int, float)):
        ts = ts_field
    if not ts: return ""
    from datetime import datetime, timezone
    d = datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    return f"{d.year}-{d.month:02d}-{d.day:02d}"

def fetch_all(token):
    records = []
    page_token = None
    while True:
        body = {"page_size": 100}
        if page_token:
            body["page_token"] = page_token
        r = requests.post(
            f"https://open.feishu.cn/open-apis/bitable/v1/apps/{APP_TOKEN}/tables/{TABLE_ID}/records/search",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            json=body
        )
        d = r.json()
        if d["code"] != 0:
            print(f"Error: {d}")
            break
        items = d.get("data", {}).get("items", [])
        for item in items:
            f = item["fields"]
            records.append({
                "name":      get_field(f, "姓名"),
                "team":      get_field(f, "团队类型"),
                "base":      get_field(f, "基地"),
                "level":     get_field(f, "等级"),
                "title":     get_field(f, "称号"),
                "total":     get_field(f, "总分"),
                "breadth":   get_field(f, "广度得分"),
                "control":   get_field(f, "可控性得分"),
                "form":      get_field(f, "形态得分"),
                "influence": get_field(f, "影响力得分"),
                "weak":      get_field(f, "短板维度"),
                "action":    get_field(f, "对应动作"),
                "date":      get_date(f),
            })
        if not d.get("data", {}).get("has_more"):
            break
        page_token = d["data"].get("page_token")
    return records

if __name__ == "__main__":
    token = get_token()
    records = fetch_all(token)
    print(f"拉取到 {len(records)} 条记录")
    with open("data.json", "w", encoding="utf-8") as fp:
        json.dump(records, fp, ensure_ascii=False, indent=2)
    print("data.json 已生成")
