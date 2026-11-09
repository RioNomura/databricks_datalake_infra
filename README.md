# databricks_datalake_infra

趣味用 Databricks ワークスペース（Free Edition）の中身を Terraform で管理するリポジトリ。
カタログ・スキーマ、IP 許可リスト、シークレットスコープ、権限などをここで定義する。

データ取り込みのジョブ（DABs）は [datalake_databricks_homes](https://github.com/RioNomura/datalake_databricks_homes) で管理する。

## 構成

```
envs/prod/                       ワークスペースに適用するルート設定（state は HCP Terraform）
modules/                         再利用する Terraform モジュール（カタログ、シークレットスコープなど）
.github/workflows/terraform.yml  PR で plan、main へのマージで apply、apply 後に Notion の台帳を更新
scripts/notion_sync.py           apply 結果を Notion「リソース台帳」に反映するスクリプト
```

## CI/CD の流れ

1. feature ブランチで `envs/` または `modules/` を編集して PR を作る
2. GitHub Actions が `fmt` → `validate` → `plan` を実行し、結果を PR にコメントする
3. PR の plan を確認して main にマージすると、`apply` が走る（Environment `production`、main からのみ）
4. apply 後、変更のあったリソースが Notion のリソース台帳に反映される

## 必要な設定（GitHub の Settings → Secrets and variables → Actions）

| 種類 | 名前 | 内容 |
|---|---|---|
| Secret | `DATABRICKS_HOST` | ワークスペース URL |
| Secret | `DATABRICKS_CLIENT_ID` | サービスプリンシパル `github-actions-terraform` の Application ID |
| Secret | `DATABRICKS_CLIENT_SECRET` | 同 OAuth シークレット |
| Secret | `TF_API_TOKEN` | HCP Terraform の API トークン |
| Secret | `NOTION_TOKEN` | Notion インテグレーションのトークン |
| Variable | `TF_CLOUD_ORGANIZATION` | HCP Terraform の Organization 名 |
| Variable | `NOTION_DATABASE_ID` | Notion「リソース台帳」のデータベース ID |

## Notion 同期スクリプトの確認

```bash
python3 scripts/notion_sync.py --plan plan.json --state state.json --dry-run
```
