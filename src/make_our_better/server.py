"""MCP tool for recording tool usage feedback and problem-solving experiences."""

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import Tool, TextContent

# Storage files - relative to the server location
BASE_DIR = Path(__file__).parent.parent.parent
FEEDBACK_FILE = BASE_DIR / "feedback-tools.jsonl"
EXPERIENCE_FILE = BASE_DIR / "experience.jsonl"
INDEX_FILE = BASE_DIR / "experience-index.json"

app = server = Server("make-our-better")


def tokenize(text: str) -> set:
    """Extract search tokens from text."""
    text = text.lower()
    tokens = set(re.findall(r'[\w\u4e00-\u9fff]+', text))
    return {t for t in tokens if len(t) >= 2}


def build_index() -> dict[str, list[int]]:
    """Build inverted index for experience file."""
    index: dict[str, list[int]] = {}
    if not EXPERIENCE_FILE.exists():
        return index

    with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            search_text = " ".join([
                entry.get("title", ""),
                entry.get("problem", ""),
                entry.get("solution", ""),
                entry.get("keywords", ""),
                entry.get("context", ""),
            ])
            tokens = tokenize(search_text)
            for token in tokens:
                if token not in index:
                    index[token] = []
                if line_num not in index[token]:
                    index[token].append(line_num)

    return index


def save_index(index: dict[str, list[int]]) -> None:
    """Save index to file."""
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)


def load_index() -> dict[str, list[int]]:
    """Load index from file."""
    if INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available tools."""
    return [
        Tool(
            name="record_tool_feedback",
            description=(
                "Record feedback about tool usage experience. Use this whenever you complete "
                "a task or encounter tool-related issues. Stores in feedback-tools.jsonl "
                "for reviewing and improving MCP tools. "
                "Fields: tool_name (required), rating 1-5 (required), feedback (required), context (optional)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "tool_name": {"type": "string", "description": "The name of the tool being reviewed"},
                    "rating": {"type": "integer", "description": "Rating from 1-5 (1=poor, 5=excellent)", "minimum": 1, "maximum": 5},
                    "feedback": {"type": "string", "description": "Detailed feedback about the tool experience"},
                    "context": {"type": "string", "description": "Optional: what task you were doing"},
                },
                "required": ["tool_name", "rating", "feedback"],
            },
        ),
        Tool(
            name="record_experience",
            description=(
                "Record problem-solving experience for future reference. Use this after "
                "solving a complex or difficult problem. Stores in experience.jsonl "
                "so the experience can be searched and reused later. "
                "Fields: title (required), problem (required), solution (required), keywords (optional), context (optional)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "title": {"type": "string", "description": "Brief title summarizing the problem/solution"},
                    "problem": {"type": "string", "description": "Description of the problem encountered"},
                    "solution": {"type": "string", "description": "How the problem was solved, key insights"},
                    "keywords": {"type": "string", "description": "Optional: comma-separated keywords for searching"},
                    "context": {"type": "string", "description": "Optional: additional context or project info"},
                },
                "required": ["title", "problem", "solution"],
            },
        ),
        Tool(
            name="search_experience",
            description=(
                "Search through recorded experiences using inverted index. "
                "Supports multi-term search with relevance ranking. "
                "Supports Chinese and English queries. "
                "Fields: query (required), limit (optional, default: 5)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query (supports multiple terms, e.g., 'mcp server')"},
                    "limit": {"type": "integer", "description": "Maximum number of results (default: 5)", "default": 5},
                },
                "required": ["query"],
            },
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: Any) -> list[TextContent]:
    """Handle tool calls."""
    if name == "record_tool_feedback":
        return await record_tool_feedback(arguments)
    elif name == "record_experience":
        return await record_experience(arguments)
    elif name == "search_experience":
        return await search_experience(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def record_tool_feedback(args: dict) -> list[TextContent]:
    """Record tool usage feedback."""
    tool_name = args.get("tool_name")
    rating = args.get("rating")
    feedback_text = args.get("feedback")
    context = args.get("context", "")

    if not isinstance(rating, int) or not (1 <= rating <= 5):
        return [TextContent(type="text", text="Rating must be an integer between 1 and 5")]

    entry = {
        "timestamp": datetime.now().isoformat(),
        "tool_name": tool_name,
        "rating": rating,
        "feedback": feedback_text,
        "context": context,
    }

    with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    return [
        TextContent(
            type="text",
            text=f"Feedback recorded for '{tool_name}': {rating}/5 - {feedback_text[:100]}{'...' if len(feedback_text) > 100 else ''}",
        )
    ]


async def record_experience(args: dict) -> list[TextContent]:
    """Record problem-solving experience."""
    title = args.get("title")
    problem = args.get("problem")
    solution = args.get("solution")
    keywords = args.get("keywords", "")
    context = args.get("context", "")

    entry = {
        "timestamp": datetime.now().isoformat(),
        "title": title,
        "problem": problem,
        "solution": solution,
        "keywords": keywords,
        "context": context,
    }

    # Find line number for index
    line_num = 1
    if EXPERIENCE_FILE.exists():
        with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
            line_num = sum(1 for _ in f if _.strip()) + 1

    # Write entry
    with open(EXPERIENCE_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Update index
    index = load_index()
    search_text = " ".join([title, problem, solution, keywords, context])
    tokens = tokenize(search_text)
    for token in tokens:
        if token not in index:
            index[token] = []
        if line_num not in index[token]:
            index[token].append(line_num)
    save_index(index)

    return [TextContent(type="text", text=f"Experience recorded: '{title}' - stored for future reference")]


async def search_experience(args: dict) -> list[TextContent]:
    """Search through recorded experiences using inverted index."""
    query = args.get("query", "")
    limit = args.get("limit", 5)

    if not EXPERIENCE_FILE.exists():
        return [TextContent(type="text", text="No experiences recorded yet.")]

    query_tokens = tokenize(query)
    if not query_tokens:
        return [TextContent(type="text", text="No valid search terms found.")]

    index = load_index()
    if not index:
        return await linear_search(query, limit)

    # Find matching entries
    entry_scores: dict[int, int] = {}
    for token in query_tokens:
        if token in index:
            for line_num in index[token]:
                entry_scores[line_num] = entry_scores.get(line_num, 0) + 1

    if not entry_scores:
        return [TextContent(type="text", text=f"No experiences found matching '{query}'.")]

    sorted_entries = sorted(entry_scores.items(), key=lambda x: (-x[1], -x[0]))
    top_entries = dict(sorted_entries[:limit])

    results = []
    with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if line_num in top_entries:
                try:
                    entry = json.loads(line)
                    entry["_score"] = top_entries[line_num]
                    results.append(entry)
                except json.JSONDecodeError:
                    continue

    if not results:
        return [TextContent(type="text", text=f"No experiences found matching '{query}'.")]

    output_lines = [f"Found {len(results)} matching experiences:\n"]
    for i, entry in enumerate(results, 1):
        output_lines.append("=" * 60)
        output_lines.append(f"[{i}] {entry.get('title', 'Untitled')}")
        output_lines.append(f"Keywords: {entry.get('keywords', 'N/A')}")
        output_lines.append(f"Problem: {entry.get('problem', '')}")
        output_lines.append(f"Solution: {entry.get('solution', '')}")
        output_lines.append(f"Context: {entry.get('context', 'N/A')}")
        output_lines.append(f"Date: {entry.get('timestamp', '')}")
        output_lines.append("")

    return [TextContent(type="text", text="\n".join(output_lines))]


async def linear_search(query: str, limit: int) -> list[TextContent]:
    """Fallback linear search."""
    query_lower = query.lower()
    results = []

    with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            search_text = " ".join([
                entry.get("title", ""),
                entry.get("problem", ""),
                entry.get("solution", ""),
                entry.get("keywords", ""),
            ]).lower()

            if query_lower in search_text:
                results.append(entry)

    if not results:
        return [TextContent(type="text", text=f"No experiences found matching '{query}'.")]

    output_lines = [f"Found {len(results)} matching experiences:\n"]
    for i, entry in enumerate(results, 1):
        output_lines.append("=" * 60)
        output_lines.append(f"[{i}] {entry.get('title', 'Untitled')}")
        output_lines.append(f"Keywords: {entry.get('keywords', 'N/A')}")
        output_lines.append(f"Problem: {entry.get('problem', '')}")
        output_lines.append(f"Solution: {entry.get('solution', '')}")
        output_lines.append(f"Context: {entry.get('context', 'N/A')}")
        output_lines.append(f"Date: {entry.get('timestamp', '')}")
        output_lines.append("")

    return [TextContent(type="text", text="\n".join(output_lines))]


async def main():
    """Main entry point."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
