#!/usr/bin/env bash
# judge.sh — AI judge: reads PR timeline, determines outcome, assigns bounty.
# Usage: judge.sh <pr_number> [slug]
set -euo pipefail

BOUNTY_MONITOR_URL="${BOUNTY_MONITOR_URL:-http://localhost:18792}"
CLAUDE_MODEL="${CLAUDE_MODEL:-claude-sonnet-4-6}"

PR_NUMBER="${1:?Usage: judge.sh <pr_number>}"
SLUG="${2:-${ASDLC_SLUG:-unknown}}"

# ---------------------------------------------------------------------------
# 1. Fetch PR metadata
# ---------------------------------------------------------------------------
PR_JSON=$(gh pr view "$PR_NUMBER" --json \
    title,body,state,mergedAt,labels,comments,reviews,url,closingIssuesReferences,headRefName)

PR_TITLE=$(printf '%s' "$PR_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('title',''))")
PR_STATE=$(printf '%s' "$PR_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('state',''))")
PR_URL=$(printf '%s' "$PR_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('url',''))")
PR_LABELS=$(printf '%s' "$PR_JSON" | python3 -c "
import sys,json
d=json.load(sys.stdin)
print(' '.join(l['name'] for l in d.get('labels',[])))
")
PR_COMMENTS=$(printf '%s' "$PR_JSON" | python3 -c "
import sys,json
d=json.load(sys.stdin)
comments = d.get('comments',[])
out=[]
for c in comments:
    body=c.get('body','').strip()
    author=c.get('author',{}).get('login','?')
    if body:
        out.append(f'[{author}]: {body[:300]}')
print('\n'.join(out[:20]))
")
PR_REVIEWS=$(printf '%s' "$PR_JSON" | python3 -c "
import sys,json
d=json.load(sys.stdin)
reviews=d.get('reviews',[])
out=[]
for r in reviews:
    state=r.get('state','')
    body=r.get('body','').strip()
    author=r.get('author',{}).get('login','?')
    out.append(f'[{author} {state}]: {body[:200]}')
print('\n'.join(out[:10]))
")

# Linked issue numbers
LINKED_ISSUES=$(printf '%s' "$PR_JSON" | python3 -c "
import sys,json
d=json.load(sys.stdin)
issues=d.get('closingIssuesReferences',[])
print(' '.join(str(i.get('number','')) for i in issues))
")

# ---------------------------------------------------------------------------
# 2. Fetch PR timeline events for label history and CI
# ---------------------------------------------------------------------------
REPO=$(gh repo view --json nameWithOwner -q .nameWithOwner)
TIMELINE_JSON=$(gh api "repos/${REPO}/issues/${PR_NUMBER}/timeline" --paginate 2>/dev/null || echo "[]")

CI_STATUS="unknown"
if gh pr checks "$PR_NUMBER" --json name,state 2>/dev/null | python3 -c "
import sys,json
checks=json.load(sys.stdin)
failed=[c for c in checks if c.get('state','').upper() in ('FAILURE','ERROR')]
print('failed' if failed else 'passed')
" 2>/dev/null; then
    CI_STATUS=$(gh pr checks "$PR_NUMBER" --json name,state 2>/dev/null | python3 -c "
import sys,json
checks=json.load(sys.stdin)
if not checks:
    print('none')
elif any(c.get('state','').upper() in ('FAILURE','ERROR') for c in checks):
    print('failed')
else:
    print('passed')
" 2>/dev/null || echo "unknown")
fi

# ---------------------------------------------------------------------------
# 3. Determine outcome: clean / rework / qa-fail-rework / blocked
# ---------------------------------------------------------------------------
REWORK_COUNT=$(printf '%s' "$TIMELINE_JSON" | python3 -c "
import sys,json
events=json.load(sys.stdin)
count=0
for e in events:
    if e.get('event') == 'labeled':
        label=e.get('label',{}).get('name','')
        if label in ('rework','needs-revision','changes-requested'):
            count+=1
print(count)
" 2>/dev/null || echo "0")

HAS_QA_FAIL=$(printf '%s' "$TIMELINE_JSON" | python3 -c "
import sys,json
events=json.load(sys.stdin)
for e in events:
    if e.get('event') == 'labeled':
        label=e.get('label',{}).get('name','')
        if 'qa-fail' in label or 'qa_fail' in label:
            print('true'); sys.exit(0)
print('false')
" 2>/dev/null || echo "false")

HAS_BLOCKED=$(printf '%s' "$PR_LABELS" | grep -q "blocked" && echo "true" || echo "false")

if [ "$HAS_BLOCKED" = "true" ] || { [ "$PR_STATE" = "CLOSED" ] && [ -z "$(printf '%s' "$PR_JSON" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('mergedAt','') or '')")" ]; }; then
    OUTCOME="blocked"
elif [ "$HAS_QA_FAIL" = "true" ]; then
    OUTCOME="qa-fail-rework"
elif [ "$REWORK_COUNT" -gt 0 ]; then
    OUTCOME="rework"
else
    OUTCOME="clean"
fi

# ---------------------------------------------------------------------------
# 4. Parse bounty from linked issue body
# ---------------------------------------------------------------------------
BOUNTY_POINTS=0
for ISSUE_NUM in $LINKED_ISSUES; do
    ISSUE_BODY=$(gh issue view "$ISSUE_NUM" --json body -q .body 2>/dev/null || echo "")
    PARSED=$(printf '%s' "$ISSUE_BODY" | python3 -c "
import sys,re
body=sys.stdin.read()
m=re.search(r'##\s+Bounty:\s+[^\d]*(\d+)\s+points', body, re.IGNORECASE)
print(m.group(1) if m else '0')
" 2>/dev/null || echo "0")
    if [ "$PARSED" -gt "$BOUNTY_POINTS" ] 2>/dev/null; then
        BOUNTY_POINTS="$PARSED"
    fi
done

# ---------------------------------------------------------------------------
# 5. Apply scoring table
# ---------------------------------------------------------------------------
read -r SCORE_PLANNER SCORE_BUILDER SCORE_REVIEWER SCORE_TESTER <<< "$(python3 -c "
outcome='${OUTCOME}'
table = {
    'clean':         (3, 5, 3, 2),
    'rework':        (3, 2, 4, 2),
    'qa-fail-rework':(3, 1, 1, 3),
    'blocked':       (-1,-3, 0, 0),
}
p,b,r,t = table.get(outcome, (0,0,0,0))
print(p, b, r, t)
")"

# Add bounty bonus (even split, clean only)
BONUS_EACH=0
if [ "$OUTCOME" = "clean" ] && [ "$BOUNTY_POINTS" -gt 0 ] 2>/dev/null; then
    BONUS_EACH=$(python3 -c "import math; print(math.floor(${BOUNTY_POINTS}/4))")
    SCORE_PLANNER=$((SCORE_PLANNER + BONUS_EACH))
    SCORE_BUILDER=$((SCORE_BUILDER + BONUS_EACH))
    SCORE_REVIEWER=$((SCORE_REVIEWER + BONUS_EACH))
    SCORE_TESTER=$((SCORE_TESTER + BONUS_EACH))
fi

# ---------------------------------------------------------------------------
# 6. Call claude CLI for AI verdict (2-3 sentences)
# ---------------------------------------------------------------------------
VERDICT_PROMPT="You are the ASDLC Judge. Review the following PR and write exactly 2-3 sentences assessing the quality of each role's contribution (Planner, Builder, Reviewer, Tester). Be specific and concise.

PR: ${PR_TITLE}
URL: ${PR_URL}
Outcome: ${OUTCOME} (rework cycles: ${REWORK_COUNT})
CI: ${CI_STATUS}

Recent comments:
${PR_COMMENTS:-none}

Reviews:
${PR_REVIEWS:-none}

Scores awarded: Planner=${SCORE_PLANNER} Builder=${SCORE_BUILDER} Reviewer=${SCORE_REVIEWER} Tester=${SCORE_TESTER}
Bounty bonus per role: ${BONUS_EACH}

Write a verdict (2-3 sentences) explaining these scores. Do not add headers or bullet points — plain sentences only."

VERDICT_TEXT=$(claude --model "$CLAUDE_MODEL" -p "$VERDICT_PROMPT" 2>/dev/null || echo "Verdict generation failed; scores applied from scoring table based on outcome: ${OUTCOME}.")

# ---------------------------------------------------------------------------
# 7. POST JSON verdict to monitor API
# ---------------------------------------------------------------------------
TIMESTAMP=$(date -u '+%Y-%m-%dT%H:%M:%SZ' 2>/dev/null || date '+%Y-%m-%dT%H:%M:%SZ')

VERDICT_JSON=$(python3 -c "
import json, sys
payload = {
    'pr': int('${PR_NUMBER}'),
    'slug': '${SLUG}',
    'outcome': '${OUTCOME}',
    'rework_cycles': int('${REWORK_COUNT}'),
    'bounty_points': int('${BOUNTY_POINTS}'),
    'bonus_each': int('${BONUS_EACH}'),
    'scores': {
        'planner': int('${SCORE_PLANNER}'),
        'builder': int('${SCORE_BUILDER}'),
        'reviewer': int('${SCORE_REVIEWER}'),
        'tester': int('${SCORE_TESTER}'),
    },
    'verdict': '''${VERDICT_TEXT}''',
    'timestamp': '${TIMESTAMP}',
}
print(json.dumps(payload))
")

curl -sf \
    --max-time 10 \
    --connect-timeout 5 \
    -X POST \
    -H 'Content-Type: application/json' \
    -d "$VERDICT_JSON" \
    "${BOUNTY_MONITOR_URL}/api/verdict" \
    >/dev/null 2>&1 || echo "Warning: could not reach bounty monitor at ${BOUNTY_MONITOR_URL}" >&2

# ---------------------------------------------------------------------------
# 8. Post bounty summary as PR comment
# ---------------------------------------------------------------------------
BOUNTY_LINE=""
if [ "$BOUNTY_POINTS" -gt 0 ] && [ "$OUTCOME" = "clean" ]; then
    BOUNTY_LINE="
**Bounty bonus:** 🏆 ${BOUNTY_POINTS} pts split evenly (+${BONUS_EACH} each role)"
fi

COMMENT_BODY="## Judge Verdict — \`${OUTCOME}\`

${VERDICT_TEXT}

| Role | Score |
|------|-------|
| Planner | ${SCORE_PLANNER:+}${SCORE_PLANNER} |
| Builder | ${SCORE_BUILDER:+}${SCORE_BUILDER} |
| Reviewer | ${SCORE_REVIEWER:+}${SCORE_REVIEWER} |
| Tester | ${SCORE_TESTER:+}${SCORE_TESTER} |
${BOUNTY_LINE}
_Rework cycles: ${REWORK_COUNT} · CI: ${CI_STATUS} · Outcome: ${OUTCOME}_"

gh pr comment "$PR_NUMBER" --body "$COMMENT_BODY"
