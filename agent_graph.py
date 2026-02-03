import os
import sys
from typing import Annotated, TypedDict
from dotenv import load_dotenv

from langgraph.graph import StateGraph, START, END
from langgraph.prebuilt import ToolNode
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters.tools import load_mcp_tools
from mcp import StdioServerParameters
from langchain_core.messages import SystemMessage, HumanMessage, AIMessage, ToolMessage

load_dotenv()

# 2. 导出 MCP 连接参数，供外部生命周期管理使用
server_params = StdioServerParameters(
    command=sys.executable,
    args=[os.path.join(os.path.dirname(__file__), "server_db.py")],
    env=os.environ.copy()
)

from langgraph.graph.message import add_messages
from langchain_core.messages import SystemMessage

# 1. 使用 add_messages reducer，这是处理对话流的标准方式
class AgentState(TypedDict):
    messages: Annotated[list, add_messages]

def create_agent_graph(mcp_tools):
    llm = ChatOpenAI(
        model=os.getenv("MODEL_NAME", "deepseek-chat"),
        # ... 其他配置
    ).bind_tools(mcp_tools)

    def call_model(state: AgentState):
        # 1. 定义系统消息
        sys_prompt = SystemMessage(content="你是一个 MySQL 专家。必须先调用 get_db_schema 获取表结构。")
        
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
        
        return {"messages": [response]}

    # 构建图
    workflow = StateGraph(AgentState)
    workflow.add_node("agent", call_model)
    # ToolNode 会自动处理 state["messages"] 中最后的 tool_calls 并返回 ToolMessage
    workflow.add_node("tools", ToolNode(mcp_tools))

    workflow.add_edge(START, "agent")
    
    def route_logic(state: AgentState):
        last_message = state["messages"][-1]
        if last_message.tool_calls:
            return "tools"
        return END

    workflow.add_conditional_edges("agent", route_logic)
    workflow.add_edge("tools", "agent")

    return workflow.compile()