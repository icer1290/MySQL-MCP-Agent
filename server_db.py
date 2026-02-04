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

# 1. 定义工具：获取数据库所有表的清单（仅表名）
@mcp.tool()
def list_all_tables() -> str:
    """列出数据库中所有的表名，用于初步了解库结构。"""
    sql = "SELECT table_name FROM information_schema.tables WHERE table_schema = 'refresh'"
    results = execute_query(sql) #
    if not results:
        return "数据库中没有表。"
    tables = [row.get('table_name', row.get('TABLE_NAME')) for row in results]
    return f"数据库 'refresh' 中的表有: {', '.join(tables)}"

# 2. 定义工具：根据关键词搜索相关的表结构
@mcp.tool()
def search_tables_by_keyword(keyword: str) -> str:
    """根据关键词搜索相关的表名或字段名，返回匹配的表结构概要。"""
    sql = f"""
    SELECT table_name, column_name, column_comment 
    FROM information_schema.columns 
    WHERE table_schema = 'refresh' 
    AND (table_name LIKE '%{keyword}%' OR column_name LIKE '%{keyword}%' OR column_comment LIKE '%{keyword}%')
    """
    results = execute_query(sql) #
    if not results:
        return f"未找到与 '{keyword}' 相关的表或字段。"
    
    res_str = "检索到的相关信息：\n"
    for row in results:
        t_name = row.get('table_name', row.get('TABLE_NAME', 'Unknown'))
        c_name = row.get('column_name', row.get('COLUMN_NAME', 'Unknown'))
        c_comment = row.get('column_comment', row.get('COLUMN_COMMENT', '无备注'))
        
        res_str += f"表: {t_name}, 字段: {c_name} ({c_comment})\n"
    return res_str

# 3. 定义工具：获取特定表的详细 DDL/结构
@mcp.tool()
def get_table_details(table_names: list[str]) -> str:
    """获取指定表的详细结构信息（包含列名、类型、备注）。参数为表名列表。"""
    table_list_str = "','".join(table_names)
    sql = f"""
    SELECT table_name, column_name, data_type, column_comment
    FROM information_schema.columns 
    WHERE table_schema = 'refresh' AND table_name IN ('{table_list_str}')
    """
    results = execute_query(sql)

    if not results:
        return "未发现表结构，请确认数据库 'refresh' 中存在表。"

    schema_info = "数据库结构如下：\n"
    
    for row in results:
        t_name = row.get('table_name', row.get('TABLE_NAME', 'Unknown'))
        c_name = row.get('column_name', row.get('COLUMN_NAME', 'Unknown'))
        schema_info += f"表: {t_name}, 列: {c_name}\n"
    return str(results)

# 4. 定义工具：执行 SQL
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