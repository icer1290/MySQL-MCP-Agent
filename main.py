import uuid
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools
from langchain_core.messages import HumanMessage

# 导入重写后的mcp模块
from agent_graph import server_params, create_agent_graph

# --- 1. 定义 FastAPI 生命周期 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    管理 MCP 连接的生命周期。
    在 Windows 下，这确保了 stdio 管道在同一个事件循环中运行。
    """
    print("🚀 正在建立 MCP 连接...")
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 协议初始化
            await session.initialize()
            # 挂载工具并创建 Graph
            mcp_tools = await load_mcp_tools(session)
            app.state.agent = create_agent_graph(mcp_tools)
            
            print("✅ NL2SQL Agent 已就绪 (MCP 管道已打通)")
            yield 
            # 当 FastAPI 关闭时，代码会执行到这里，自动退出 async with 释放管道
    print("🛑 MCP 连接已关闭")

# --- 2. 初始化应用 ---
app = FastAPI(
    title="Refresh NL2SQL API",
    description="基于 MCP 协议与 LangGraph 的自然语言转 SQL 助手",
    lifespan=lifespan
)

# --- 3. 定义请求体 ---
class ChatRequest(BaseModel):
    query: str
    thread_id: str = None

# --- 4. 编写接口逻辑 ---
@app.post("/chat")
async def chat(request: ChatRequest):
    if not hasattr(app.state, "agent"):
        raise HTTPException(status_code=503, detail="Agent 未初始化，请检查 MCP 连接")

    try:
        # 为每个请求生成唯一的 Thread ID，方便后续扩展对话记忆
        current_thread_id = request.thread_id or str(uuid.uuid4())
        config = {"configurable": {"thread_id": current_thread_id}}
        
        # 构造输入
        inputs = {"messages": [HumanMessage(content=request.query)]}
        
        # 运行 Agent
        # ainvoke 会等待整个图运行完毕并返回最后结果
        result = await app.state.agent.ainvoke(inputs, config)
        
        # 获取 AI 的最后一条回复
        final_answer = result["messages"][-1].content
        
        return {
            "status": "success",
            "query": request.query,
            "thread_id": current_thread_id,
            "response": final_answer
        }
    except Exception as e:
        # 生产环境建议记录详细日志
        print(f"❌ 运行报错: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # 启动服务
    uvicorn.run(app, host="127.0.0.1", port=8000)