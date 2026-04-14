# from langchain_aws import ChatBedrockConverse
# from langchain.agents import create_agent

# from tools import tools

# # ── LLM ──────────────────────────────────────────────────────────────────────

# llm = ChatBedrockConverse(
#     model="us.meta.llama3-1-70b-instruct-v1:0",
#     region_name="us-east-1",
#     temperature=0,
# )

# # ── System prompt ─────────────────────────────────────────────────────────────

# SYSTEM_PROMPT = """You are a CloudWatch log analyst assistant.
# You help engineers explore and understand AWS Lambda logs using plain English.

# You have 4 tools:
# - tool_get_log_groups: lists all available CloudWatch log groups
# - tool_search_qdrant: semantically searches stored logs (use this first for any question about errors or events)
# - tool_ingest: fetches and stores logs from CloudWatch into Qdrant (call this if search returns empty)
# - tool_fetch_live_logs: fetches latest logs directly from CloudWatch in real time

# Workflow:
# 1. If the user asks what log groups exist → call tool_get_log_groups
# 2. If the user asks about errors or events → call tool_search_qdrant first
#    - If it returns empty → call tool_ingest for that log group, then tool_search_qdrant again
# 3. If the user asks for latest/real-time logs → call tool_fetch_live_logs
# 4. Infer the log group from the user's message (e.g. "CoverLetterGen" → /aws/lambda/CoverLetterGen)
#    If unsure, call tool_get_log_groups first to see what's available.

# Always give clear, concise answers. When explaining errors, include what went wrong,
# when it happened, and the relevant request ID if available.
# """

# # ── Agent ─────────────────────────────────────────────────────────────────────

# agent = create_agent(
#     model=llm,
#     tools=tools,
#     system_prompt=SYSTEM_PROMPT,
# )


# # ── Helper used by api.py ─────────────────────────────────────────────────────

# def run_agent(message: str) -> str:
#     """
#     Runs the agent with a user message and returns the final answer as a string.
#     """
#     result = agent.invoke({
#         "messages": [{"role": "user", "content": message}]
#     })
#     return result["messages"][-1].content


# # ── Local chat loop for testing ───────────────────────────────────────────────

# if __name__ == "__main__":
#     print("CloudWatch Log Agent — type 'quit' to exit\n")
#     while True:
#         query = input("You: ").strip()
#         if not query or query.lower() == "quit":
#             break
#         answer = run_agent(query)
#         print(f"\nAgent: {answer}\n")



from langchain_aws import ChatBedrockConverse
from langchain_core.messages import SystemMessage
from langgraph.graph import StateGraph, MessagesState, START, END
from langgraph.checkpoint.memory import MemorySaver
from langgraph.prebuilt import ToolNode
from tools import tools

llm = ChatBedrockConverse(
    model="us.amazon.nova-pro-v1:0",
    region_name="us-east-1",
    temperature=0,
).bind_tools(tools)

SYSTEM_PROMPT = """You are a CloudWatch log analyst assistant.
You help engineers explore and understand AWS Lambda logs using plain English.

You have 4 tools:
- tool_get_log_groups: lists all available CloudWatch log groups
- tool_search_qdrant: semantically searches stored logs (use this first for any question about errors or events)
- tool_ingest: fetches and stores logs from CloudWatch into Qdrant (call this if search returns empty)
- tool_fetch_live_logs: fetches latest logs directly from CloudWatch in real time

Workflow:
1. If the user asks what log groups exist → call tool_get_log_groups
2. If the user asks about errors or events → call tool_search_qdrant first
   - If it returns empty → call tool_ingest for that log group, then tool_search_qdrant again
3. If the user asks for latest/real-time logs → call tool_fetch_live_logs
4. Infer the log group from the user's message (e.g. "CoverLetterGen" → /aws/lambda/CoverLetterGen)
   If unsure, call tool_get_log_groups first to see what's available.

Always give clear, concise answers. When explaining errors, include what went wrong,
when it happened, and the relevant request ID if available.
"""
# ── Nodes ─────────────────────────────────────────────────────────────────────

def call_llm(state: MessagesState):
    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm.invoke(messages)
    return {"messages": [response]}

tool_node = ToolNode(tools)

# ── Routing logic ─────────────────────────────────────────────────────────────

def should_continue(state: MessagesState):
    last = state["messages"][-1]
    if last.tool_calls:
        return "tools"
    return END

# ── Build graph ───────────────────────────────────────────────────────────────

graph = StateGraph(MessagesState)

graph.add_node("llm", call_llm)
graph.add_node("tools", tool_node)

graph.add_edge(START, "llm")
graph.add_conditional_edges("llm", should_continue)
graph.add_edge("tools", "llm")  # after tool runs, go back to LLM

agent = graph.compile(checkpointer = MemorySaver())

# ── Run ───────────────────────────────────────────────────────────────────────
def run_agent(message: str, thread_id: str = "default") -> str:
    result = agent.invoke(
        {"messages": [{"role": "user", "content": message}]},
        config={"configurable": {"thread_id": thread_id}},
    )
    return result["messages"][-1].content

if __name__ == "__main__":
    print("CloudWatch Log Agent — type 'quit' to exit\n")
    while True:
        query = input("You: ").strip()
        if not query or query.lower() == "quit":
            break
        print(f"\nAgent: {run_agent(query)}\n")