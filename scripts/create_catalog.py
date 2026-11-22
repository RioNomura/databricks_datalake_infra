#!/usr/bin/env python3
"""Unity Catalog のカタログ本体を、サービスプリンシパル（SP）の権限で SQL から作る。

なぜ必要か:
  Free Edition の既定のストレージ（Default Storage）に置くカタログは、Terraform（カタログ作成 API）では作れない。
  SQL の CREATE CATALOG なら作れるが、実行した人が作成者（created_by）として残り、あとから変えられない。
  個人のアカウントで作るとメールアドレスが残り、公開リポジトリの plan に表示されてしまう。
  そこで GitHub Actions（create-catalog.yml）から SP の認証情報でこのスクリプトを実行し、作成者・持ち主を必ず SP にする。
  作ったあとは envs/prod/ に import ブロックを書いて Terraform に取り込む（README「新しいカタログを作る」）。

使い方:
  python3 scripts/create_catalog.py --name <カタログ名> --comment "<説明>" [--dry-run]

環境変数:
  DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET  SP の OAuth（GitHub Actions の Secrets）
  DATABRICKS_TOKEN                                                   ローカルで試すとき（client 情報の代わり）
  DATABRICKS_WAREHOUSE_ID                                            SQL を実行する SQL ウェアハウスの ID
  NOTION_TOKEN / NOTION_DATABASE_ID                                  設定されていればリソース台帳に記録する

ログには SP の ID やメールアドレスを出さない（公開リポジトリの Actions ログは誰でも見られるため）。
"""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# 小文字・数字・アンダースコアだけ。SQL に埋め込むので、それ以外は受け付けない
NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
JST = dt.timezone(dt.timedelta(hours=9))


def fail(msg: str) -> None:
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def http_json(req: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        fail(f"HTTP {exc.code} on {req.get_method()} {urllib.parse.urlparse(req.full_url).path}: "
             f"{exc.read().decode(errors='replace')}")
    return {}


class Databricks:
    def __init__(self):
        host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
        if not host:
            fail("DATABRICKS_HOST を設定してください")
        self.host = host if host.startswith("https://") else f"https://{host}"
        self.warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID") or fail("DATABRICKS_WAREHOUSE_ID を設定してください")
        self.token = os.environ.get("DATABRICKS_TOKEN") or self._oauth_token()

    def _oauth_token(self) -> str:
        cid = os.environ.get("DATABRICKS_CLIENT_ID")
        secret = os.environ.get("DATABRICKS_CLIENT_SECRET")
        if not (cid and secret):
            fail("DATABRICKS_TOKEN か DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET を設定してください")
        basic = base64.b64encode(f"{cid}:{secret}".encode()).decode()
        req = urllib.request.Request(
            f"{self.host}/oidc/v1/token",
            data=urllib.parse.urlencode({"grant_type": "client_credentials", "scope": "all-apis"}).encode(),
            headers={"Authorization": f"Basic {basic}", "Content-Type": "application/x-www-form-urlencoded"},
            method="POST",
        )
        return http_json(req)["access_token"]

    def sql(self, statement: str) -> list[list]:
        """SQL を実行して結果の行を返す（Statement Execution API）。失敗したら終了する。"""
        def call(method: str, path: str, body: dict | None = None) -> dict:
            req = urllib.request.Request(
                f"{self.host}/api/2.0/sql/statements{path}",
                data=json.dumps(body).encode() if body is not None else None,
                method=method,
                headers={"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"},
            )
            return http_json(req)

        res = call("POST", "", {"warehouse_id": self.warehouse_id, "statement": statement, "wait_timeout": "50s"})
        # ウェアハウスが起動中などで 50 秒以内に終わらなかったときは、終わるまで待つ
        deadline = time.monotonic() + 600
        while res.get("status", {}).get("state") in ("PENDING", "RUNNING"):
            if time.monotonic() > deadline:
                fail("SQL が 10 分以内に終わりませんでした")
            time.sleep(5)
            res = call("GET", f"/{res['statement_id']}")
        status = res.get("status", {})
        if status.get("state") != "SUCCEEDED":
            fail(f"SQL が失敗しました: {status.get('error', {}).get('message', status)}")
        return res.get("result", {}).get("data_array") or []


def sql_string(value: str) -> str:
    return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'"


def record_notion(name: str, comment: str) -> None:
    token, db_id = os.environ.get("NOTION_TOKEN"), os.environ.get("NOTION_DATABASE_ID")
    if not (token and db_id):
        print("NOTION_TOKEN / NOTION_DATABASE_ID が無いので、リソース台帳は更新しません")
        return
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    repo, run_id = os.environ.get("GITHUB_REPOSITORY"), os.environ.get("GITHUB_RUN_ID")
    run = f"（run: {server}/{repo}/actions/runs/{run_id}）" if repo and run_id else ""
    # 行のキーは Terraform 同期と同じ「Terraformアドレス」。import 時のリソース名をカタログ名と同じにする前提
    address = f"databricks_catalog.{name}"

    def notion(method: str, path: str, body: dict) -> dict:
        return http_json(urllib.request.Request(
            f"https://api.notion.com/v1{path}",
            data=json.dumps(body).encode(),
            method=method,
            headers={"Authorization": f"Bearer {token}", "Notion-Version": "2022-06-28",
                     "Content-Type": "application/json"},
        ))

    props = {
        "リソース名": {"title": [{"text": {"content": name}}]},
        "Terraformアドレス": {"rich_text": [{"text": {"content": address}}]},
        "種類": {"select": {"name": "Unity Catalog"}},
        "サービス": {"select": {"name": "Databricks"}},
        "管理方法": {"select": {"name": "Terraform"}},
        "状態": {"status": {"name": "稼働中"}},
        "ID": {"rich_text": [{"text": {"content": name}}]},
        "権限・設定": {"rich_text": [{"text": {"content": f"カタログ（Default Storage）。作成者・持ち主は SP。{comment}"[:2000]}}]},
        "変更内容": {"rich_text": [{"text": {"content": f"create-catalog ワークフローで作成{run}。envs/prod/ で import する"}}]},
        "最終更新": {"date": {"start": dt.datetime.now(JST).date().isoformat()}},
    }
    found = notion("POST", f"/databases/{db_id}/query",
                   {"filter": {"property": "Terraformアドレス", "rich_text": {"equals": address}}, "page_size": 1})
    if found.get("results"):
        notion("PATCH", f"/pages/{found['results'][0]['id']}", {"properties": props})
        print(f"リソース台帳を更新しました: {address}")
    else:
        notion("POST", "/pages", {"parent": {"database_id": db_id}, "properties": props})
        print(f"リソース台帳に追加しました: {address}")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--name", required=True, help="カタログ名（小文字・数字・アンダースコア）")
    p.add_argument("--comment", required=True, help="カタログの説明")
    p.add_argument("--dry-run", action="store_true", help="実行する SQL を表示するだけ")
    p.add_argument("--no-notion", action="store_true", help="リソース台帳を更新しない（動作確認用）")
    args = p.parse_args()

    name, comment = args.name.strip(), args.comment.strip()
    if not NAME_RE.match(name):
        fail(f"カタログ名は小文字で始まり、小文字・数字・アンダースコアだけ（64 文字以内）にしてください: {name!r}")
    if not comment:
        fail("説明（comment）を入れてください")

    # IF NOT EXISTS は付けない。同じ名前が既にあれば失敗させ、他人が作ったカタログを誤って取り込まないようにする
    statement = f"CREATE CATALOG `{name}` COMMENT {sql_string(comment)}"
    print(f"実行する SQL: {statement}")
    if args.dry_run:
        return 0

    db = Databricks()
    db.sql(statement)

    # 作成者と持ち主が、いま実行している ID（CI では SP）になっているか確かめる。値そのものはログに出さない
    me = db.sql("SELECT current_user()")[0][0]
    info = {row[0]: row[1] for row in db.sql(f"DESCRIBE CATALOG EXTENDED `{name}`")}
    owner_ok = info.get("Owner") == me
    creator_ok = info.get("Created By") == me
    print(f"作成しました: {name}（持ち主 = 実行した ID: {owner_ok} / 作成者 = 実行した ID: {creator_ok}）")
    if not (owner_ok and creator_ok):
        fail("持ち主か作成者が、実行した ID と一致しません。カタログを確認してください")

    if not args.no_notion:
        record_notion(name, comment)
    print("次: envs/prod/ に import ブロックと databricks_catalog / スキーマ / GRANT を書いて PR を作る")
    return 0


if __name__ == "__main__":
    sys.exit(main())
