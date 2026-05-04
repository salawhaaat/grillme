"""Pre-rendered interview scenario phrases organized by interview phase."""
from typing import TypedDict


class ScenarioPhrase(TypedDict):
    phase: str
    index: int
    text: str


SCENARIO_PHRASES: list[ScenarioPhrase] = [
    {"phase": "intro", "index": 0, "text": "Hey, I'm Elon. I'll be running your technical interview today. Let's not waste time — tell me about yourself."},
    {"phase": "intro", "index": 1, "text": "Welcome. I'm Elon, your interviewer. Give me the thirty-second version of who you are."},
    {"phase": "intro", "index": 2, "text": "Hi there. I'm Elon. Before we dive into code, tell me what you've been working on lately."},
    {"phase": "intro", "index": 3, "text": "Alright, I'm Elon. Let's skip the pleasantries — what's the most interesting thing you've built?"},
    {"phase": "intro", "index": 4, "text": "I'm Elon. We've got a lot to cover, so let's jump right in. Tell me about yourself."},
    {"phase": "behavioral", "index": 0, "text": "Interesting. Tell me more about that."},
    {"phase": "behavioral", "index": 1, "text": "What was the hardest technical decision you made on that project?"},
    {"phase": "behavioral", "index": 2, "text": "How did you handle disagreements with your team on the approach?"},
    {"phase": "behavioral", "index": 3, "text": "Walk me through your thought process on that."},
    {"phase": "behavioral", "index": 4, "text": "What would you do differently if you started over?"},
    {"phase": "behavioral", "index": 5, "text": "That's a good point. Can you go deeper on the technical side?"},
    {"phase": "behavioral", "index": 6, "text": "How did you measure success on that?"},
    {"phase": "behavioral", "index": 7, "text": "What was the biggest risk and how did you mitigate it?"},
    {"phase": "behavioral", "index": 8, "text": "Okay, I've heard enough on that. Let's move on."},
    {"phase": "behavioral", "index": 9, "text": "Fair enough. Next question."},
    {"phase": "coding_intro", "index": 0, "text": "Alright, let's get to the real stuff. I'm going to give you a coding problem."},
    {"phase": "coding_intro", "index": 1, "text": "Time for coding. Take a look at the problem on your screen."},
    {"phase": "coding_intro", "index": 2, "text": "Okay, here's your coding challenge. Read through it and tell me your initial thoughts."},
    {"phase": "coding_intro", "index": 3, "text": "Let's see how you think. Here's a problem — walk me through your approach before you start coding."},
    {"phase": "coding_feedback", "index": 0, "text": "What's your initial approach?"},
    {"phase": "coding_feedback", "index": 1, "text": "Think about the time complexity of that."},
    {"phase": "coding_feedback", "index": 2, "text": "Have you considered edge cases?"},
    {"phase": "coding_feedback", "index": 3, "text": "That's one way to do it. Is there a more efficient approach?"},
    {"phase": "coding_feedback", "index": 4, "text": "Good start. Keep going."},
    {"phase": "coding_feedback", "index": 5, "text": "Walk me through what this function does."},
    {"phase": "coding_feedback", "index": 6, "text": "What happens when the input is empty?"},
    {"phase": "coding_feedback", "index": 7, "text": "You're on the right track."},
    {"phase": "coding_feedback", "index": 8, "text": "That's not quite right. Think about it again."},
    {"phase": "coding_feedback", "index": 9, "text": "Can you optimize that?"},
    {"phase": "coding_feedback", "index": 10, "text": "What's the space complexity?"},
    {"phase": "coding_feedback", "index": 11, "text": "Try running through an example."},
    {"phase": "coding_feedback", "index": 12, "text": "Almost there. What are you missing?"},
    {"phase": "coding_feedback", "index": 13, "text": "Good. Now test it with the edge cases."},
    {"phase": "coding_feedback", "index": 14, "text": "Nice solution. Let's wrap up."},
    {"phase": "closing", "index": 0, "text": "That's all from me. Do you have any questions?"},
    {"phase": "closing", "index": 1, "text": "We're done with the technical part. Any questions for me?"},
    {"phase": "closing", "index": 2, "text": "Good work today. Anything you want to ask about the role or team?"},
    {"phase": "closing", "index": 3, "text": "Alright, we're wrapping up. What questions do you have?"},
]

VALID_PHASES = {"intro", "behavioral", "coding_intro", "coding_feedback", "closing"}


def get_phrases_by_phase(phase: str) -> list[ScenarioPhrase]:
    return [p for p in SCENARIO_PHRASES if p["phase"] == phase]
