"""MCP tool for recording tool usage feedback and problem-solving experiences."""

import json
import re
import uuid
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


def read_all_experiences() -> list[dict]:
    """Read all experiences from file."""
    experiences = []
    if EXPERIENCE_FILE.exists():
        with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    try:
                        experiences.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue
    return experiences


def write_all_experiences(experiences: list[dict]) -> None:
    """Write all experiences to file."""
    with open(EXPERIENCE_FILE, "w", encoding="utf-8") as f:
        for entry in experiences:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def build_index() -> dict[str, list[str]]:
    """Build inverted index for experience file using UUIDs."""
    index: dict[str, list[str]] = {}
    if not EXPERIENCE_FILE.exists():
        return index

    with open(EXPERIENCE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue

            entry_id = entry.get("id")
            if not entry_id:
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
                if entry_id not in index[token]:
                    index[token].append(entry_id)

    return index


def save_index(index: dict[str, list[str]]) -> None:
    """Save index to file."""
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False)


def load_index() -> dict[str, list[str]]:
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
        Tool(
            name="vote_experience",
            description=(
                "Vote for an experience that was helpful. Use this when you search and find "
                "an experience useful for your task. The experience with more votes will appear "
                "higher in search results. "
                "Fields: id (required) - the id of the experience to vote for (get from search_experience results)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "The id of the experience to vote for (from search_experience results)"},
                },
                "required": ["id"],
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
    elif name == "vote_experience":
        return await vote_experience(arguments)
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

    entry_id = str(uuid.uuid4())
    entry = {
        "id": entry_id,
        "timestamp": datetime.now().isoformat(),
        "title": title,
        "problem": problem,
        "solution": solution,
        "keywords": keywords,
        "context": context,
        "votes": 0,
    }

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
        if entry_id not in index[token]:
            index[token].append(entry_id)
    save_index(index)

    return [TextContent(type="text", text=f"Experience recorded: '{title}' - stored for future reference")]


async def search_experience(args: dict) -> list[TextContent]:
    """Search through recorded experiences using inverted index."""
    query = args.get("query", "")
    limit = args.get("limit", 5)

    if not EXPERIENCE_FILE.exists():
        return [TextContent(
            type="text",
            text=json.dumps({"results": []}, ensure_ascii=False),
            mimeType="application/json"
        )]

    query_tokens = tokenize(query)
    if not query_tokens:
        return [TextContent(
            type="text",
            text=json.dumps({"results": []}, ensure_ascii=False),
            mimeType="application/json"
        )]

    # Build index on every search to ensure real-time updates
    index = build_index()
    if not index:
        return await linear_search(query, limit)

    # Find matching entries using UUIDs
    entry_scores: dict[str, int] = {}
    for token in query_tokens:
        if token in index:
            for entry_id in index[token]:
                entry_scores[entry_id] = entry_scores.get(entry_id, 0) + 1

    if not entry_scores:
        return [TextContent(
            type="text",
            text=json.dumps({"results": []}, ensure_ascii=False),
            mimeType="application/json"
        )]

    # Read all experiences to get vote counts for sorting
    all_experiences = read_all_experiences()
    # Build a map of id -> votes
    votes_map: dict[str, int] = {}
    id_to_entry: dict[str, dict] = {}
    for entry in all_experiences:
        entry_id = entry.get("id")
        if entry_id:
            votes_map[entry_id] = entry.get("votes", 0)
            id_to_entry[entry_id] = entry

    # Sort by: 1) relevance score (descending), 2) votes (descending)
    sorted_entries = sorted(entry_scores.items(), key=lambda x: (-x[1], -votes_map.get(x[0], 0)))
    top_entries = dict(sorted_entries[:limit])

    results = []
    for entry_id, score in top_entries.items():
        if entry_id in id_to_entry:
            entry = id_to_entry[entry_id].copy()
            entry["score"] = score
            results.append(entry)

    response_data = {"results": results}
    return [TextContent(
        type="text",
        text=json.dumps(response_data, ensure_ascii=False),
        mimeType="application/json"
    )]


async def linear_search(query: str, limit: int) -> list[TextContent]:
    """Fallback linear search returning JSON format."""
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

    # Sort by votes (descending)
    results.sort(key=lambda x: x.get("votes", 0), reverse=True)
    results = results[:limit]

    response_data = {"results": results}
    return [TextContent(
        type="text",
        text=json.dumps(response_data, ensure_ascii=False),
        mimeType="application/json"
    )]


async def vote_experience(args: dict) -> list[TextContent]:
    """Vote for an experience by its id."""
    entry_id = args.get("id")

    if not entry_id:
        return [TextContent(type="text", text="Experience id is required to vote.")]

    experiences = read_all_experiences()
    voted = False

    for entry in experiences:
        if entry.get("id") == entry_id:
            entry["votes"] = entry.get("votes", 0) + 1
            voted = True

    if voted:
        write_all_experiences(experiences)
        return [TextContent(type="text", text=f"Voted for experience id: '{entry_id}' - thank you for your feedback!")]
    else:
        return [TextContent(type="text", text=f"No experience found with id: '{entry_id}'")]


async def main():
    """Main entry point."""
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
