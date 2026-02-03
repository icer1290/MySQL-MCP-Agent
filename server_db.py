import pymysql
import pymysql.cursors
from fastmcp import FastMCP
from typing import List, Dict, Any

# 1. 初始化 MCP 服务
mcp = FastMCP("Refresh-MySQL-Service")

# 数据库连接配置
DB_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "navicat",
    "password": "navicat123",
    "database": "refresh",
    "charset": "utf8mb4",
    "cursorclass": pymysql.cursors.DictCursor
}

def execute_query(sql: str) -> list:
    """执行 SQL 并强制返回字典格式"""
    connection = pymysql.connect(**DB_CONFIG)
    try:
        # 关键点：显式指定 DictCursor
        with connection.cursor(pymysql.cursors.DictCursor) as cursor:
            cursor.execute(sql)
            return cursor.fetchall()
    finally:
        connection.close()

# 2. 定义工具：获取表结构（Agent 写 SQL 的基础）
@mcp.tool()
def get_db_schema() -> str:
    """获取数据库结构"""
    sql = """
    SELECT table_name, column_name, data_type, column_comment
    FROM information_schema.columns 
    WHERE table_schema = 'refresh'
    """
    results = execute_query(sql)
    
    if not results:
        return "未发现表结构，请确认数据库 'refresh' 中存在表。"

    schema_info = "数据库结构如下：\n"
    for row in results:
        # 如果 execute_query 返回的是元组而非字典，这里 row['table_name'] 就会报 KeyError
        t_name = row.get('table_name', row.get('TABLE_NAME', 'Unknown'))
        c_name = row.get('column_name', row.get('COLUMN_NAME', 'Unknown'))
        schema_info += f"表: {t_name}, 列: {c_name}\n"
    return schema_info

# 3. 定义工具：执行 SQL
@mcp.tool()
def run_sql_query(sql: str) -> str:
    """在数据库上执行 SQL SELECT 查询并返回结果。"""
    # 简单的安全过滤
    forbidden_keywords = ["DROP", "DELETE", "TRUNCATE", "UPDATE", "INSERT"]
    if any(keyword in sql.upper() for keyword in forbidden_keywords):
        return "错误：仅支持 SELECT 查询操作。"
        
    try:
        results = execute_query(sql)
        if not results:
            return "查询成功，但没有找到符合条件的结果。"
        return str(results)
    except Exception as e:
        return f"SQL 执行出错: {str(e)}"

if __name__ == "__main__":
    mcp.run()