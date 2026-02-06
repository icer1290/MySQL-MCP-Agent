import pymysql
import pymysql.cursors
import re
import os
import logging
from fastmcp import FastMCP
from dbutils.pooled_db import PooledDB
from dotenv import load_dotenv

# 加载配置
load_dotenv()

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger("MySQL-MCP-Server")

# 1. 初始化 MCP 服务
mcp = FastMCP("Refresh-MySQL-Service")

# 2. 数据库连接池管理器 (单例模式)
class DatabaseManager:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseManager, cls).__new__(cls)
            cls._instance._init_pool()
        return cls._instance

    def _init_pool(self):
        """初始化 PooledDB 连接池"""
        try:
            self.pool = PooledDB(
                creator=pymysql,
                maxconnections=int(os.getenv("DB_POOL_MAX_CONNECTIONS", 20)),
                mincached=int(os.getenv("DB_POOL_MIN_CACHED", 5)),
                maxcached=int(os.getenv("DB_POOL_MAX_CACHED", 10)),
                blocking=True,
                ping=1, # 取出连接时检查活跃状态
                host=os.getenv("DB_HOST", "localhost"),
                port=int(os.getenv("DB_PORT", 3306)),
                user=os.getenv("DB_USER"),
                password=os.getenv("DB_PASSWORD"),
                database=os.getenv("DB_NAME"),
                charset="utf8mb4",
                cursorclass=pymysql.cursors.DictCursor
            )
            logger.info("✅ 数据库连接池初始化成功")
        except Exception as e:
            logger.error(f"❌ 连接池初始化失败: {str(e)}")
            raise

    def execute(self, sql: str, params: tuple = None) -> list:
        """从池中获取连接并执行查询"""
        conn = self.pool.connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params or ())
                return cursor.fetchall()
        finally:
            conn.close() # 归还连接到池中

db_manager = DatabaseManager()

# 3. 安全校验：强制只读规则
def is_safe_sql(sql: str) -> bool:
    """拦截非 SELECT 语句及敏感操作"""
    forbidden = [r"\bDROP\b", r"\bDELETE\b", r"\bTRUNCATE\b", r"\bUPDATE\b", r"\bINSERT\b", r"\bALTER\b"]
    sql_upper = sql.upper()
    for pattern in forbidden:
        if re.search(pattern, sql_upper):
            return False
    return sql_upper.strip().startswith("SELECT") or sql_upper.strip().startswith("SHOW")

# --- 工具定义 ---

@mcp.tool()
def list_all_tables() -> str:
    """获取数据库表清单。"""
    sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = %s"
    results = db_manager.execute(sql, (os.getenv("DB_NAME"),))
    if not results:
        return "数据库中没有表。"
    tables = [row.get('table_name') or row.get('TABLE_NAME') for row in results]
    return f"表清单: {', '.join(tables)}"

@mcp.tool()
def get_table_details(table_names: list[str]) -> str:
    """获取特定表的字段结构。"""
    # 使用参数化查询防止注入
    placeholders = ', '.join(['%s'] * len(table_names))
    sql = f"""
    SELECT table_name, column_name, data_type, column_comment
    FROM information_schema.columns 
    WHERE table_schema = %s AND table_name IN ({placeholders})
    """
    params = (os.getenv("DB_NAME"), *table_names)
    results = db_manager.execute(sql, params)
    return str(results) if results else "未找到表结构。"

@mcp.tool()
def run_sql_query(sql: str) -> str:
    """执行 SQL 查询。仅限 SELECT。"""
    if not is_safe_sql(sql):
        return "错误：权限拒绝。该工具仅允许执行 SELECT 查询操作。"
        
    try:
        # 限制返回结果集大小，防止大表查询撑爆内存
        if "LIMIT" not in sql.upper():
            sql = sql.rstrip(';') + " LIMIT 100"
            
        results = db_manager.execute(sql)
        return str(results) if results else "查询成功，无数据返回。"
    except Exception as e:
        logger.error(f"SQL 执行异常: {str(e)} | SQL: {sql}")
        return f"执行失败: {str(e)}"

if __name__ == "__main__":
    mcp.run()