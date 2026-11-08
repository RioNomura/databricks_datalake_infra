terraform {
  required_version = ">= 1.9"

  # Organization は環境変数 TF_CLOUD_ORGANIZATION から読む（GitHub の Variables に登録）
  # Workspace 名は旧リポジトリ（datalake_databricks_homes）時代のまま。既存の state をそのまま引き継ぐため
  cloud {
    workspaces {
      name = "datalake-databricks-homes"
    }
  }

  required_providers {
    databricks = {
      source  = "databricks/databricks"
      version = "~> 1.60"
    }
  }
}

# 接続先と認証は環境変数 DATABRICKS_HOST / DATABRICKS_CLIENT_ID / DATABRICKS_CLIENT_SECRET から読む
provider "databricks" {}
