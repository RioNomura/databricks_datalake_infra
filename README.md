# databricks_datalake_infra

趣味用 Databricks ワークスペース（Free Edition）の中身を Terraform で管理するリポジトリ。
カタログ・スキーマ、IP 許可リスト、シークレットスコープ、権限などをここで定義する。

データ取り込みのジョブ（DABs）は [datalake_databricks_homes](https://github.com/RioNomura/datalake_databricks_homes) で管理する。
