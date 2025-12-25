"""MCP tool for recording tool usage feedback."""

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Feedback storage file - relative to the server location
FEEDBACK_FILE = Path(__file__).parent.parent.parent / "feedback.jsonl"

app = server = Server("make-our-better")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="make_our_better",
            description=(
                "Record feedback about tool usage experience. Use this whenever you want to "
                "capture thoughts about how well a tool worked, suggestions for improvement, "
                "or any observations during development. The feedback is stored in feedback.jsonl "
                "for later review and tool improvement."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {
                        "type": "string",
                        "description": "The name of the tool being reviewed",
                    },
                    "rating": {
                        "type": "integer",
                        "description": "Rating from 1-5 (1=poor, 5=excellent)",
                        "minimum": 1,
                        "maximum": 5,
                    },
                    "feedback": {
                        "type": "string",
                        "description": "Detailed feedback about the tool experience",
                    },
                    "context": {
                        "type": "string",
                        "description": "Optional: what task you were doing",
                    },
                },
                "required": ["tool_name", "rating", "feedback"],
            },
        )
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    if name != "make_our_better":
        return [TextContent(type="text", text=f"Unknown tool: {name}")]

    tool_name = arguments.get("tool_name")
    rating = arguments.get("rating")
    feedback_text = arguments.get("feedback")
    context = arguments.get("context", "")

    if not isinstance(rating, int) or not (1 <= rating <= 5):
        return [TextContent(type="text", text="Rating must be an integer between 1 and 5")]

    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool_name": tool_name,
        "rating": rating,
        "feedback": feedback_text,
        "context": context,
    }

    # Append to feedback file (create if doesn't exist)
    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return [
        TextContent(
            type="text",
            text=f"Feedback recorded for '{tool_name}': {rating}/5 - {feedback_text[:100]}{'...' if len(feedback_text) > 100 else ''}",
        )
    ]


async def main():
    """Main entry point."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
