# 賃貸物件データ（HOME'S など）を置くカタログと、bronze / silver / gold / semantic の 4 スキーマ
# - bronze: スクレイピングなどで取得したデータをそのまま保存する層
#   （datalake_databricks_homes の homes_rental_ingest ジョブが書き込む）
# Free Edition はメタストアにストレージの場所が無く、既定のストレージ（Default Storage）に置かれるため storage_root は指定しない

# Terraform を実行するサービスプリンシパルが持ち主になる
# force_destroy = false: 中にテーブルがあるときは destroy で一緒に消さない
resource "databricks_catalog" "rental_property" {
  name          = "rental_property"
  comment       = "賃貸物件データ。Terraform（databricks_datalake_infra）で管理"
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
# ここではオーナー本人が dev ターゲットでジョブを試したり、中身を確認したりできるようにする
# databricks_grants はこのカタログの付与内容をここに書いたものだけにする（画面で足した権限は次の apply で消える）
resource "databricks_grants" "rental_property" {
  catalog = databricks_catalog.rental_property.name

  grant {
    principal  = "grio3031@gmail.com"
    privileges = ["ALL_PRIVILEGES"]
  }
}
