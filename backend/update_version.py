"""
更新版本信息并打 Git tag
用法: python backend/update_version.py "v1.1" "2026年5月21日10:30分 1.1版" "新增批量删除功能"
"""
import sys
import json
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
VERSION_FILE = os.path.join(BASE_DIR, "version.json")


def update(version_tag, label, message):
    with open(VERSION_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    from datetime import datetime
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    new_entry = {
        "version": version_tag,
        "label": label,
        "date": now,
        "message": message,
    }

    # 插入到历史最前面
    data["history"].insert(0, new_entry)
    data["current"] = label

    with open(VERSION_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print(f"版本已更新: {label}")
    print(f"文件: {VERSION_FILE}")
    print(f"请手动执行: git tag -a {version_tag} -m '{label}' && git push origin {version_tag}")


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("用法: python backend/update_version.py <version_tag> <label> <message>")
        print('示例: python backend/update_version.py v1.1 "2026年5月21日10:30分 1.1版" "新增批量删除功能"')
        sys.exit(1)

    update(sys.argv[1], sys.argv[2], sys.argv[3])
