# mimitsubo-autopost

Instagram「mimitsubo.sayaka」の自動投稿用リポジトリです。

- `queue/` … 承認済の投稿（画像・キャプション・投稿日時）。Mac の Claude Code が送ってきます
- `posted/` … 公開した結果の記録（GitHub が自動で書き込みます）
- `scripts/publish.py` … 投稿時刻になったものを Instagram に公開するプログラム
- `.github/workflows/` … 15分ごとの投稿確認と、月2回のトークン延長

## Secrets（Settings → Secrets and variables → Actions）
- `IG_ACCESS_TOKEN` … Instagram のアクセストークン（必須）
- `GH_PAT` … トークンの自動延長用（あると便利）

## 失敗したとき
`posted/<ID>.error.json` が作られ、GitHub からメールが届きます。
二重投稿を防ぐため自動では再挑戦しません。原因を直したら、その error.json を削除すると次の確認で再挑戦します。

※ このリポジトリは公開設定です。承認済の画像とキャプション以外は置かないでください。
