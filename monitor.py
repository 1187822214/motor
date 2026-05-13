#!/usr/bin/env python3
"""
山西招生考试网 - 考试公告监控脚本
监控 http://www.sxkszx.cn/index.html 的"考试公告"板块
发现新公告时通过 Webhook 推送通知（支持钉钉/飞书）
"""

import os
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime

# ==================== 配置区 ====================
TARGET_URL = "http://www.sxkszx.cn/index.html"
STATE_FILE = "state.json"

# Webhook 地址从环境变量读取（GitHub Secrets 里设置）
WEBHOOK_URL = os.environ.get("WEBHOOK_URL", "")
# ===============================================


def fetch_announcements():
    """抓取首页的"考试公告"列表，返回 [(标题, 链接, 日期), ...]"""
    try:
        resp = requests.get(TARGET_URL, timeout=15)
        resp.encoding = "utf-8"
    except requests.RequestException as e:
        print(f"[错误] 请求失败: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")

    # 考试公告在 .right1-content 下的第一个表格
    right1 = soup.select_one(".right1-content")
    if not right1:
        print("[错误] 页面结构异常，未找到 .right1-content")
        return []

    first_table = right1.find("table")
    if not first_table:
        print("[错误] 未找到考试公告表格")
        return []

    announcements = []
    rows = first_table.select("tr")
    for row in rows:
        link_tag = row.select_one("td.newsbody a")
        date_tag = row.select_one("td.newsbodydate")
        if link_tag and date_tag:
            title = link_tag.get_text(strip=True)
            href = link_tag.get("href", "")
            # 补全相对路径
            if href and not href.startswith("http"):
                href = "http://www.sxkszx.cn" + href
            date = date_tag.get_text(strip=True).strip("[]")
            announcements.append((title, href, date))

    return announcements


def load_state():
    """读取上次保存的已推送记录"""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"seen_urls": []}


def save_state(seen_urls):
    """保存已推送记录（最多保留 50 条）"""
    unique = list(dict.fromkeys(seen_urls))[:50]
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump({"seen_urls": unique}, f, ensure_ascii=False, indent=2)


def push_notification(new_items):
    """通过 Webhook 推送（自动适配钉钉/飞书）"""
    if not WEBHOOK_URL:
        print("[跳过] 未设置 WEBHOOK_URL 环境变量")
        return

    is_lark = any(k in WEBHOOK_URL.lower() for k in ["feishu", "larksuite", "open.feishu.cn"])

    lines = ["📢 山西招生考试网 — 新公告\n"]
    for title, url, date in new_items:
        lines.append(f"▸ {title}")
        lines.append(f"  日期: {date}")
        lines.append(f"  链接: {url}")
        lines.append("")

    text = "\n".join(lines)

    try:
        if is_lark:
            resp = requests.post(
                WEBHOOK_URL,
                json={"msg_type": "text", "content": {"text": text}},
                timeout=10,
            )
        else:
            resp = requests.post(
                WEBHOOK_URL,
                json={"msgtype": "text", "text": {"content": text}},
                timeout=10,
            )
        print(f"[推送] 状态码: {resp.status_code}")
        if resp.status_code != 200:
            print(f"[推送] 响应: {resp.text[:200]}")
    except requests.RequestException as e:
        print(f"[错误] 推送失败: {e}")


def main():
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{now}] 开始抓取考试公告...")

    current = fetch_announcements()
    if not current:
        print("[结束] 未抓取到任何公告，等待下次运行")
        return

    print(f"当前页面共有 {len(current)} 条公告")

    state = load_state()
    seen = set(state.get("seen_urls", []))

    new_items = []
    for title, url, date in current:
        if url not in seen:
            new_items.append((title, url, date))

    if new_items:
        print(f"发现 {len(new_items)} 条新公告，准备推送")
        push_notification(new_items)
    else:
        print("无新公告")

    current_urls = [url for _, url, _ in current]
    updated_seen = current_urls + [u for u in state.get("seen_urls", []) if u not in current_urls]
    save_state(updated_seen)


if __name__ == "__main__":
    main()
