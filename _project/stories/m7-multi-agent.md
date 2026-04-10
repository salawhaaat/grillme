# M7 — Multi-Agent Architecture

## User Story
As a candidate using grillme across multiple sessions,
I want the system to remember my weak areas from past interviews
so that each new session's prep plan targets my actual gaps.

## Acceptance Criteria
- [ ] JD pipeline uses specialized agents (Parser → Persona → Scorer)
- [ ] Agents communicate via typed Pydantic schemas
- [ ] After each scored interview, weak areas are extracted and stored
- [ ] Next session's prep plan references stored weaknesses
- [ ] Profile page shows tracked weak areas and score trends
