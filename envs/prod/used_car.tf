# 中古車データ（カーセンサーなど）を置くカタログと、bronze / silver / gold / semantic の 4 スキーマ
# 構成は rental_property（catalog.tf）と同じ
# - bronze: スクレイピングで取得したデータをそのまま保存する層
#   （datalake_databricks_homes の carsensor_used_car_ingest ジョブが書き込む）
#
# カタログ本体は Actions の create-catalog ワークフローで SP の権限で作り、下の import で取り込む
# （既定のストレージのカタログは Terraform では作れないため。README「新しいカタログを作る」）
import {
  to = databricks_catalog.used_car
  id = "used_car"
}

# 持ち主は Terraform を実行するサービスプリンシパル（本番ジョブの run_as と同じ）
# force_destroy = false: 中にテーブルがあるときは destroy で一緒に消さない
resource "databricks_catalog" "used_car" {
  name          = "used_car"
  comment       = "中古車データ（カーセンサーなど）。Terraform（databricks_datalake_infra）で管理"
  owner         = data.databricks_current_user.terraform.user_name
  force_destroy = false

  # SQL で作ると storage_root と properties が自動で入る。Terraform には書かない値なので差分にしない
  lifecycle {
    ignore_changes = [storage_root, properties]
  }
}

# スキーマ = データの加工段階（メダリオン構成 + セマンティック層）
locals {
  used_car_schemas = {
    bronze   = "取得したままのデータ（カーセンサーの中古車一覧など）。DABs のジョブが書き込む"
    silver   = "bronze を型変換・重複除去・クレンジングしたデータ"
    gold     = "分析・集計用に整えたデータ（車種別の価格相場など）"
    semantic = "メトリクスビューなど、ビジネス上の指標の定義を置く層"
  }
}

resource "databricks_schema" "used_car" {
  for_each = local.used_car_schemas

  catalog_name = databricks_catalog.used_car.name
  name         = each.key
  comment      = each.value
}

# カタログの権限。持ち主のサービスプリンシパルは何もしなくても全権限を持つ
# 人への付与はグループ単位（公開リポジトリに個人のメールアドレスを残さないため）。
# グループは private の databricks_datalake_identity で作る（used_car_admin）
resource "databricks_grants" "used_car" {
  catalog = databricks_catalog.used_car.name

  # used_car カタログの管理者。dev ターゲットでジョブを試したり、中身を確認したりできるようにする
  # MANAGE: 本番ジョブ（サービスプリンシパル）が作ったテーブルを、取り込みのやり直し時などに削除できるようにする
  #   （ALL_PRIVILEGES には MANAGE が含まれず、持ち主でないテーブルは DROP できない）
  grant {
    principal  = "used_car_admin"
    privileges = ["ALL_PRIVILEGES", "MANAGE"]
  }
}
