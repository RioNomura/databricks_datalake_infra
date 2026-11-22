# 賃貸物件データ（HOME'S など）を置くカタログと、bronze / silver / gold / semantic の 4 スキーマ
# - bronze: スクレイピングなどで取得したデータをそのまま保存する層
#   （datalake_databricks_homes の homes_rental_ingest ジョブが書き込む）
# Free Edition はメタストアにストレージの場所が無く、既定のストレージ（Default Storage）に置かれるため storage_root は指定しない
#
# 注意: 既定のストレージのカタログは、Terraform（カタログ作成 API）では作れない
#   （"Metastore storage root URL does not exist. Default Storage is enabled ..." で失敗する）。
#   そのため、カタログ本体だけは先に SQL で作り、持ち主をサービスプリンシパルに移してから、下の import で取り込む:
#     CREATE CATALOG <名前>;
#     ALTER CATALOG <名前> OWNER TO `<サービスプリンシパルの Application ID>`;
#   取り込んだ後は通常どおり Terraform で管理する（コメント・持ち主・スキーマ・権限）。
import {
  to = databricks_catalog.rental_property
  id = "rental_property"
}

# Terraform を実行している ID（CI ではサービスプリンシパル github-actions-terraform）。user_name は Application ID になる
data "databricks_current_user" "terraform" {}

# 持ち主は Terraform を実行するサービスプリンシパル（本番ジョブの run_as と同じ）
# force_destroy = false: 中にテーブルがあるときは destroy で一緒に消さない
resource "databricks_catalog" "rental_property" {
  name          = "rental_property"
  comment       = "賃貸物件データ。Terraform（databricks_datalake_infra）で管理"
  owner         = data.databricks_current_user.terraform.user_name
  force_destroy = false
}

# スキーマ = データの加工段階（メダリオン構成 + セマンティック層）
locals {
  rental_property_schemas = {
    bronze   = "取得したままのデータ（HOME'S 賃貸一覧など）。DABs のジョブが追記する"
    silver   = "bronze を型変換・重複除去・クレンジングしたデータ"
    gold     = "分析・集計用に整えたデータ（エリア別の賃料相場など）"
    semantic = "メトリクスビューなど、ビジネス上の指標の定義を置く層"
  }
}

resource "databricks_schema" "rental_property" {
  for_each = local.rental_property_schemas

  catalog_name = databricks_catalog.rental_property.name
  name         = each.key
  comment      = each.value
}

# カタログの権限。持ち主のサービスプリンシパル（本番ジョブの run_as）は何もしなくても全権限を持つ
# 人への付与はグループ単位で行い、ここにはグループ名だけを書く（公開リポジトリに個人のメールアドレスを残さないため）
# グループの作成とメンバーの管理は private の databricks_datalake_identity で行う。先にそちらでグループを作ってから apply すること
# databricks_grants はこのカタログの付与内容をここに書いたものだけにする（画面で足した権限は次の apply で消える）
resource "databricks_grants" "rental_property" {
  catalog = databricks_catalog.rental_property.name

  # rental_property カタログの管理者。dev ターゲットでジョブを試したり、中身を確認したりできるようにする
  grant {
    principal  = "rental_property_admin"
    privileges = ["ALL_PRIVILEGES"]
  }
}
