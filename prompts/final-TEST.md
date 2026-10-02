# Final TEST — cross-batch regression + goal acceptance

Gate for DONE. Builder runs ALL, writes `prompts/final-TEST-RESULT.md` (cmds+raw output).

## 1. Regression (must all hold)
```bash
python3 -m pytest tests/ -q
rm -rf /tmp/final && bash demo/run.sh /tmp/final
bash demo/run.sh /tmp/final --append
python3 -m src.security.scan
python3 -m src.cli.main run --task "" ; echo rc=$?
```

## 2. Goal acceptance (hiring brief)
- [ ] Natural task → completed work (not explanation): cold demo posts invoice, ERP count 1.
- [ ] Plan→Execute→Observe→Adapt→Verify→Complete visible in evidence (8/8 predicates).
- [ ] Failure recovery: downed-ERP fail rc=1 → resume pass, no double post.
- [ ] Human approval: unapproved post blocked with next action; approved posts once.
- [ ] Verification + evidence: `evidence.json` verdict + steps + totals; `replayed=N` honest.
- [ ] Submission pack: README, SUBMISSION.md, requirements, .gitignore, video script (+URL).

## 3. Known limits restated (do not re-litigate)
Company Y `.txt` planner glob; LLM path unexercised; single-operator scope. Video URL placeholder must be filled before form submit.
