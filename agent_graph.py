import os
import sys
import logging
from typing import Annotated, TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from mcp import StdioServerParameters
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage
from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import MemorySaver  # 导入内存存储组件
from typing import Dict

load_dotenv()

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# 2. 导出 MCP 连接参数，供外部生命周期管理使用
server_params = StdioServerParameters(
    command=sys.executable,
    args=[os.path.join(os.path.dirname(__file__), "server_db.py")],
    env=os.environ.copy()
)


# 1. 使用 add_messages reducer，这是处理对话流的标准方式
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    # 用于存储累计的 token 使用情况
    usage: Dict[str, int]

def create_agent_graph(mcp_tools):
    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        # ... 其他配置
    ).bind_tools(mcp_tools)

    # 实例化内存存储组件
    memory = MemorySaver()

    def call_model(state: AgentState):
        # 1. 定义系统消息
        sys_prompt = SystemMessage(content="""你是一个 MySQL 专家。
        由于数据库表非常多，请遵循以下检索策略：
        1. 首先调用 list_all_tables 了解有哪些表，或者调用 search_tables_by_keyword 搜索相关业务关键词（如'订单'、'用户'）。
        2. 根据第一步的结果，调用 get_table_details 获取你认为相关的几张表的详细结构。
        3. 最后基于详细结构编写 SQL。
        禁止一次性猜测不存在的表名。""")
        
        # 2. 严格清洗并重新构建消息序列
        cleaned_messages = []
        for m in state["messages"]:
            # 提取 content 并强制转为字符串
            curr_content = m.content
            if isinstance(curr_content, list):
                # 针对 LangChain 常见的列表格式进行提取
                text_parts = [item.get("text", str(item)) if isinstance(item, dict) else str(item) for item in curr_content]
                curr_content = "".join(text_parts)
            else:
                curr_content = str(curr_content)

            # 根据消息类型重新实例化，确保没有冗余字段
            if m.type == "human":
                cleaned_messages.append(HumanMessage(content=curr_content))
            elif m.type == "ai":
                # AI 消息必须保留 tool_calls，否则后续的 ToolMessage 会失效
                cleaned_messages.append(AIMessage(content=curr_content, tool_calls=getattr(m, 'tool_calls', [])))
            elif m.type == "tool":
                # Tool 消息必须保留 tool_call_id
                cleaned_messages.append(ToolMessage(content=curr_content, tool_call_id=m.tool_call_id))

        # 3. 组合最终发送的消息
        full_messages = [sys_prompt] + cleaned_messages

        # 4. 调用模型
        response = llm.invoke(full_messages)

        # 5. 更新 token 使用情况
        token_usage = response.response_metadata.get("token_usage", {})
        
        return {"messages": [response],
                "usage": {
                "input_tokens": token_usage.get("prompt_tokens", 0),
                "output_tokens": token_usage.get("completion_tokens", 0)
            }}

    def print_messages(state: AgentState):
        # 逐行打印messages，并注明消息类型
        for msg in state["messages"]:
            msg_type = msg.type.upper()
            msg_content = msg.content
            if isinstance(msg_content, list):
                msg_content = "".join([item.get("text", str(item)) if isinstance(item, dict) else str(item) for item in msg_content])
            logger.info(f"[{msg_type}] {msg_content}")

    # 构建图
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    # ToolNode 会自动处理 state["messages"] 中最后的 tool_calls 并返回 ToolMessage
    workflow.add_node("tools", ToolNode(mcp_tools))
    workflow.add_node("print_messages", print_messages)

    workflow.add_edge(START, "agent")
    
    def route_logic(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return "print_messages"

    workflow.add_conditional_edges("agent", route_logic)
    workflow.add_edge("tools", "agent")
    workflow.add_edge("print_messages", END)

    return workflow.compile(checkpointer=memory)