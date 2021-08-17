
from typing import List, Text

import ai_flow_plugins.job_plugins.flink as flink_plugin
from ai_flow.util.json_utils import Jsonable
from ai_flow_plugins.job_plugins.flink.flink_env import FlinkBatchEnv
from pyflink.table import Table
from pyflink.table.catalog import HiveCatalog
from pyflink.table.sql_dialect import SqlDialect

HIVE_USER_FEATURE_GEN_CONFIG_KEY = "gen_config"

class HiveUserFeatureGeneratorConfig(Jsonable):
    def __init__(self,
                 catalog_name: Text,
                 default_database: Text,
                 hive_conf_dir: Text,
                 user_num: int,
                 ) -> None:
        self.catalog_name = catalog_name
        self.default_database = default_database
        self.hive_conf_dir = hive_conf_dir
        self.user_num = user_num


class HiveUserFeatureGenerator(flink_plugin.FlinkPythonProcessor):
    def process(self,
                execution_context: flink_plugin.ExecutionContext,
                input_list: List[Table] = None,
                ) -> List[Table]:
        """
        Generate two random user feature tables into hive
        """
        gen_config: HiveUserFeatureGeneratorConfig = execution_context.config[
            HIVE_USER_FEATURE_GEN_CONFIG_KEY]
        t_env = execution_context.table_env
        s_set = execution_context.statement_set

        # setup catalog
        hive_catalog = HiveCatalog(
            gen_config.catalog_name, gen_config.default_database, gen_config.hive_conf_dir)
        t_env.register_catalog(gen_config.catalog_name, hive_catalog)
        t_env.use_catalog("myhive")

        # Create source tables with Flink datagen connector
        t_env.execute_sql(f"""
        CREATE TEMPORARY TABLE TEMP_USER_FEATURE_A (
        user_id BIGINT,
        a FLOAT
        ) WITH (
        'connector' = 'datagen',
        'rows-per-second' = '10000',

        'fields.user_id.kind'='sequence',
        'fields.user_id.start'='1',
        'fields.user_id.end'='{gen_config.user_num}',

        'fields.a.min'='0',
        'fields.a.max'='1'
        )
        """)

        t_env.get_config().set_sql_dialect(SqlDialect.HIVE)
        t_env.execute_sql(f"""
        CREATE TABLE IF NOT EXISTS USER_FEATURE_A  (
        user_id BIGINT,
        a FLOAT
        )
        """)

        t_env.get_config().set_sql_dialect(SqlDialect.DEFAULT)

        # forced to use statement set to execute sql together to fix current flink-ai-flow implementation
        
        # work version 
        # s_set.add_insert_sql(f"""
        # INSERT INTO USER_FEATURE_A
        # SELECT user_id, a
        # FROM TEMP_USER_FEATURE_A
        # """)

        # error version
        t_env.execute_sql(f"""
        INSERT INTO USER_FEATURE_A
        SELECT user_id, a
        FROM TEMP_USER_FEATURE_A
        """)

        return []
