"""Greeting agent prompts."""

from __future__ import annotations

# Deterministic fallbacks — always correct, used when the LLM is unavailable.
TEMPLATE_GREETINGS: dict[str, str] = {
    "morning": "Good morning! ☀️ How can Genie help you start the day?",
    "afternoon": "Good afternoon! 👋 What can Genie do for you?",
    "evening": "Good evening! 🌆 How can Genie help tonight?",
    "night": "Working late? 🌙 Genie's here — what do you need?",
}

GREETING_SYSTEM_PROMPT = """\
You are Genie's greeting specialist. Reply with a single warm, natural greeting
(one or two short sentences, at most one emoji). It is currently the {part_of_day}
for the user (their local hour is {hour}:00). Acknowledge the time of day, greet
them, and invite them to continue. Do not answer any other question in their
message — another agent handles that. Never mention that you are an agent.
"""
