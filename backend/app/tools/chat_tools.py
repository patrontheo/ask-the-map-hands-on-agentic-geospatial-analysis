"""Chat tools: shape the conversation UI. They never compute or change the map."""

from pydantic import Field

from backend.app.tools.registry import ToolArgs, ToolContext, tool
from backend.app.tools.result import ToolResult


class FollowUpArgs(ToolArgs):
    questions: list[str] = Field(min_length=1, max_length=2,
                                 description="Two short follow-up questions in the user's voice, each under 120 characters.")


@tool(FollowUpArgs, description="""
Offer the user two short follow-up questions that build on your latest answer. The chat shows them as
buttons under your reply. Display only: it does not compute or change anything.
""")
def suggest_follow_ups(args: FollowUpArgs, ctx: ToolContext) -> ToolResult:
    questions = [q.strip()[:160] for q in args.questions if q.strip()]
    return ToolResult.ok(f"Offered {len(questions)} follow-up question(s).", data={"follow_ups": questions})
