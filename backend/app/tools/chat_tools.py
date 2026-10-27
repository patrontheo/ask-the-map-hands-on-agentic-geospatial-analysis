"""Chat tools: shape the conversation UI. They never compute or change the map."""

from pydantic import Field

from backend.app.tools.registry import ToolArgs, ToolContext, tool
from backend.app.tools.result import ToolResult


class FollowUpArgs(ToolArgs):
    questions: list[str] = Field(min_length=1, max_length=2,
                                 description="Two short follow-up questions in the user's voice, each under 120 characters.")
    answer: str | None = Field(None, min_length=1, description="Final answer to the user in Markdown. "
                              "Include to finish the turn once all tools in this batch succeed.")


@tool(FollowUpArgs, description="""
Offer the user two short follow-up questions that build on your latest answer. The chat shows them as
buttons under your reply. Include answer with your final Markdown reply to finish without another model call.
Can accompany independent map calls in the same batch. It does not compute or change the map.
""")
def suggest_follow_ups(args: FollowUpArgs, ctx: ToolContext) -> ToolResult:
    questions = [q.strip()[:160] for q in args.questions if q.strip()]
    data = {"follow_ups": questions}
    if args.answer:
        data["answer"] = args.answer.strip()
    return ToolResult.ok(f"Offered {len(questions)} follow-up question(s).", data=data)
