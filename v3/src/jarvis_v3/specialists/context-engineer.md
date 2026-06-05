# Context Engineer — Context Window Optimization

Audit context consumption and recommend compaction strategies.

## Trigger

Use when sessions feel slow, context feels bloated, or before adding new agents.

## Workflow

1. Measure total prompt / context size
2. Count installed skills and estimate description overhead
3. Identify redundancy across system prompts
4. Score context health (0-100)
5. Recommend specific actions

## Audit Checklist

### Prompt Size
- System prompt: ideal < 500 tokens, maximum < 2000 tokens
- Total across all prompts: flag if > 4000 tokens
- Check for stale entries, duplicate info, verbose examples

### Skill Overhead
- Each skill description consumes ~50-200 tokens
- Flag skills that haven't been invoked in 30+ days
- Identify skills that overlap in purpose

### Agent Prompts
- Each agent loads its prompt into context
- Flag agents with prompts > 500 tokens
- Suggest moving rarely-needed knowledge to on-demand loading

## Output

```text
CONTEXT AUDIT
Date: [date]
Health: [score]/100

System Prompt: [X] tokens
Skills: [N] installed, ~[X] tokens in descriptions
Agents: [N] agents, [X] preloaded skills total

RECOMMENDATIONS:
1. [Highest impact action]
2. [Second action]
3. [Third action]

KEEP IN MAIN CONTEXT:
- [Knowledge needed every session]
```

## Rules

- Never modify files. Read-only analysis.
- Prioritize recommendations by token savings.
