# -*- coding: utf-8 -*-
"""
Instagram のアクセストークン（約60日で期限切れ）を延長する。GitHub Actions で月2回動く。
新しいトークンが返ってきた場合は、GH_PAT がある場合に限り GitHub Secret を自動で書き換える。
"""
import os, sys, json, subprocess, urllib.request, urllib.parse, urllib.error

token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
if not token:
    sys.exit("IG_ACCESS_TOKEN が設定されていません")
url = "https://graph.instagram.com/refresh_access_token?" + urllib.parse.urlencode(
    {"grant_type": "ig_refresh_token", "access_token": token})
try:
    with urllib.request.urlopen(url, timeout=60) as r:
        res = json.loads(r.read().decode("utf-8"))
except urllib.error.HTTPError as e:
    sys.exit("トークンの延長に失敗しました: " + e.read().decode("utf-8", "replace"))
new = res.get("access_token", "")
days = int(res.get("expires_in", 0)) // 86400
print(f"トークンを延長しました（残り約{days}日）")
if new and new != token:
    print("::add-mask::" + new)
    if os.environ.get("GH_TOKEN"):
        subprocess.run(["gh", "secret", "set", "IG_ACCESS_TOKEN", "--repo", os.environ["GITHUB_REPOSITORY"]],
                       input=new.encode(), check=True)
        print("GitHub Secret の IG_ACCESS_TOKEN を新しいトークンに更新しました")
    else:
        sys.exit("新しいトークンが発行されましたが、GH_PAT がないため Secret を更新できませんでした。手動で更新してください")
