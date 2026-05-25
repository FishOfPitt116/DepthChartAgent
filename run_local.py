"""
Interactive CLI for DepthChartAgent.

Usage:
    python run_local.py
    python run_local.py "New York Yankees"   # pre-loads first message
"""

import sys

from agents import Runner
from dotenv import load_dotenv

load_dotenv()

from depth_chart_agent.agent import make_agent
from depth_chart_agent.logging_config import configure_logging

configure_logging()

if __name__ == "__main__":
    print("DepthChartAgent — type 'exit' to quit\n")

    messages = []

    # Optionally seed the first message from the command line
    agent = make_agent()

    if len(sys.argv) > 1:
        first_message = " ".join(sys.argv[1:])
        print(f"You: {first_message}")
        messages.append({"role": "user", "content": first_message})
        result = Runner.run_sync(agent, messages, max_turns=50)
        messages = result.to_input_list()
        print(f"\nAgent: {result.final_output}\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye.")
            break

        if not user_input:
            continue
        if user_input.lower() in ("exit", "quit"):
            break

        messages.append({"role": "user", "content": user_input})
        result = Runner.run_sync(agent, messages, max_turns=50)
        messages = result.to_input_list()
        print(f"\nAgent: {result.final_output}\n")
