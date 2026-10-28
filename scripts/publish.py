# -*- coding: utf-8 -*-
"""
GitHub Actions で動く Instagram 自動投稿プログラム

queue/<ID>/meta.json の publish_at（投稿日時）を過ぎたものを、Instagram API（Instagramログイン）で公開する。
公開した結果は posted/<ID>.json に記録し、同じ投稿を二度出さない。

必要な GitHub Secret:
  IG_ACCESS_TOKEN … Instagram のアクセストークン（長期トークン）

使い方:
  python scripts/publish.py            … 時刻を過ぎたものを公開
  python scripts/publish.py --dry-run  … 公開せずに、何が公開されるかだけ表示
  python scripts/publish.py --only <ID> … 指定した投稿だけ（時刻に関係なく）公開
"""
import os, sys, json, time, glob, urllib.request, urllib.parse, urllib.error
from datetime import datetime, timezone

API = os.environ.get("IG_API_BASE", "https://graph.instagram.com/v25.0")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAX_PER_RUN = 2          # 1回の実行で公開する最大件数（失敗時の連投を防ぐ）


class ApiError(Exception):
    pass


def call(method, path, token, params=None):
    url = API + path
    data = None
    headers = {"Authorization": "Bearer " + token}
    if method == "GET" and params:
        url += "?" + urllib.parse.urlencode(params)
    elif params is not None:
        data = json.dumps(params).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        raise ApiError(f"{method} {path} → {e.code}: {body}")


def raw_url(rel_path):
    """リポジトリ内のファイルの公開URL（GitHubの raw URL）"""
    repo = os.environ["GITHUB_REPOSITORY"]
    branch = os.environ.get("GITHUB_REF_NAME", "main")
    return f"https://raw.githubusercontent.com/{repo}/{branch}/" + urllib.parse.quote(rel_path)


def wait_ready(cid, token, tries=10, interval=30):
    for _ in range(tries):
        st = call("GET", f"/{cid}", token, {"fields": "status_code"}).get("status_code")
        if st == "FINISHED":
            return
        if st in ("ERROR", "EXPIRED"):
            raise ApiError(f"コンテナ {cid} の状態が {st} です")
        time.sleep(interval)
    raise ApiError(f"コンテナ {cid} の準備が時間内に終わりませんでした")


def publish(item, token, ig_id):
    meta, base = item["meta"], item["rel"]
    caption = open(os.path.join(ROOT, base, "caption.txt"), encoding="utf-8").read().strip()
    kind = meta.get("type", "carousel")
    if kind == "carousel":
        children = []
        for f in meta["images"]:
            r = call("POST", f"/{ig_id}/media", token,
                     {"image_url": raw_url(f"{base}/{f}"), "is_carousel_item": True})
            children.append(r["id"])
        for c in children:
            wait_ready(c, token, tries=6, interval=10)
        r = call("POST", f"/{ig_id}/media", token,
                 {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption})
        cid = r["id"]
        wait_ready(cid, token, tries=6, interval=10)
    elif kind == "image":
        r = call("POST", f"/{ig_id}/media", token,
                 {"image_url": raw_url(f"{base}/{meta['images'][0]}"), "caption": caption})
        cid = r["id"]
        wait_ready(cid, token, tries=6, interval=10)
    elif kind == "reel":
        p = {"media_type": "REELS", "video_url": raw_url(f"{base}/{meta['video']}"), "caption": caption,
             "share_to_feed": True}
        if meta.get("cover"):
            p["cover_url"] = raw_url(f"{base}/{meta['cover']}")
        r = call("POST", f"/{ig_id}/media", token, p)
        cid = r["id"]
        wait_ready(cid, token, tries=20, interval=30)   # 動画は処理に時間がかかる
    else:
        raise ApiError(f"未対応の種類です: {kind}")
    res = call("POST", f"/{ig_id}/media_publish", token, {"creation_id": cid})
    media_id = res["id"]
    link = ""
    try:
        link = call("GET", f"/{media_id}", token, {"fields": "permalink"}).get("permalink", "")
    except ApiError:
        pass
    return media_id, link


def load_queue():
    items = []
    for m in sorted(glob.glob(os.path.join(ROOT, "queue", "*", "meta.json"))):
        meta = json.load(open(m, encoding="utf-8"))
        qid = os.path.basename(os.path.dirname(m))
        items.append({"id": qid, "meta": meta, "rel": f"queue/{qid}"})
    return items


def main():
    dry = "--dry-run" in sys.argv
    only = sys.argv[sys.argv.index("--only") + 1] if "--only" in sys.argv else None
    now = datetime.now(timezone.utc)
    due = []
    for it in load_queue():
        done = os.path.join(ROOT, "posted", it["id"])
        if os.path.exists(done + ".json") or os.path.exists(done + ".error.json"):
            continue   # 公開済み、または失敗して確認待ち（二重投稿を防ぐため自動では再挑戦しない）
        if not it["meta"].get("approved"):
            continue
        if only:
            if it["id"] == only:
                due.append(it)
            continue
        at = datetime.fromisoformat(it["meta"]["publish_at"])
        if at <= now:
            due.append(it)
    if not due:
        print("公開する投稿はありません")
        return
    for it in due[:MAX_PER_RUN]:
        print(f"公開予定: {it['id']}（{it['meta'].get('title', '')}）")
    if dry:
        print("※ --dry-run のため公開していません")
        return
    token = os.environ.get("IG_ACCESS_TOKEN", "").strip()
    if not token:
        sys.exit("IG_ACCESS_TOKEN が設定されていません（GitHub の Secrets を確認してください）")
    me = call("GET", "/me", token, {"fields": "user_id,username"})
    ig_id = me.get("user_id") or me.get("id")
    failed = False
    for it in due[:MAX_PER_RUN]:
        rec = {"id": it["id"], "title": it["meta"].get("title", ""), "tried_at": now.isoformat()}
        try:
            media_id, link = publish(it, token, ig_id)
            rec.update({"status": "posted", "media_id": media_id, "permalink": link,
                        "posted_at": datetime.now(timezone.utc).isoformat()})
            print(f"公開しました: {it['id']} {link}")
            json.dump(rec, open(os.path.join(ROOT, "posted", it["id"] + ".json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
        except ApiError as e:
            failed = True
            rec.update({"status": "error", "error": str(e)})
            print(f"失敗しました: {it['id']}\n{e}")
            json.dump(rec, open(os.path.join(ROOT, "posted", it["id"] + ".error.json"), "w", encoding="utf-8"),
                      ensure_ascii=False, indent=2)
    if failed:
        sys.exit(1)   # 失敗したら GitHub からメールで通知が届く


if __name__ == "__main__":
    main()
