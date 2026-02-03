import asyncio
from mcp.client.stdio import stdio_client
from mcp.client.session import ClientSession
from langchain_mcp_adapters.tools import load_mcp_tools
from agent_graph import server_params, create_agent_graph
from langchain_core.messages import HumanMessage

async def test():
    print("🚀 正在启动 MCP 管道并建立会话...")
    
    # 严格的嵌套上下文管理，确保 AnyIO 作用域正确
    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            # 协议初始化
            await session.initialize()
            
            # 1. 加载工具
            mcp_tools = await load_mcp_tools(session)
            
            # 2. 通过工厂函数创建 graph
            app = create_agent_graph(mcp_tools)
            
            # 3. 执行测试
            print("💬 发起查询: 数据库里有哪些表？")
            inputs = {"messages": [HumanMessage(content="帮我查一下数据库里都有哪些表？")]}
            
            async for event in app.astream(inputs):
                for node_name, value in event.items():
                    msg = value["messages"][-1]
                    if node_name == "agent" and msg.content:
                        print(f"\n[AI]: {msg.content}")
                    elif node_name == "tools":
                        print(f"🔧 [系统]: 正在执行数据库工具...")

if __name__ == "__main__":
    asyncio.run(test())