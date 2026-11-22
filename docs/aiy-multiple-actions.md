# Multiple voice actions and editable reminders

## Prepared behavior

These source changes are not deployed yet. The voice bridge allows up to 18 tool
rounds and 32 actual calls per spoken turn, including lookups and memory writes.
Actions remain sequential so later operations can use earlier results. Every
returned function call receives an individual result; excess calls receive an
explicit unexecuted error rather than disappearing silently. The former two-round
limit prevented lookup plus two shopping completions from fitting one turn.

The OpenBao voice policy for this release must direct the model to:

- Split every clearly requested action, execute all of them, and report partial
  failures accurately. Read the shopping list when matching items; “я купил кофе
  и молоко” completes the two matching entries separately, without deleting them.
- Match each completed reminder by its own ID. “Я покормил рыб и кошек” completes
  both reminders for today. Preserve negations, questions and uncertainty; a
  mixed sentence must not mark its negative clause complete. Ask which task only
  when matching is ambiguous, not merely because several actions were requested.
- Create reminders with the existing creation tool; edit existing reminders in
  place with `update_daily_reminder`. Preserve unspecified fields. Changes can
  include text, times, repeat interval, confirmation phrase, weekdays, jitter and
  first date. A text edit regenerates the cached spoken reminder too.
- For a stated absence with known dates, use `suspend_daily_reminder` separately
  for the relevant tasks requiring presence at home. Do not infer that all tasks,
  medication or unrelated obligations should be suspended. Clarify the affected
  tasks when uncertain, and ask the return date if it is missing. A statement of
  being away is not evidence that any task has been completed.
- `until_date` is the local Europe/Prague date when reminders resume, exclusive
  of the pause. “До 25 ноября” resumes on November 25; explicitly tell the user
  the selected return date. Use `resume_daily_reminder` for an early return.
- Confirm changes only from successful tool results. Do not claim unsupported
  one-time/calendar semantics when using the recurring daily-reminder tool.

## Persistence and scheduling

`reminder_suspensions` is an additive SQLite table on the Pi. Pausing preserves
the enabled flag, acknowledgement history, cached audio and recurrence. Long
pauses still produce the correct next notification date; expiry automatically
restores the normal schedule. An early manual resume skips elapsed slots rather
than playing missed reminders. Changes to one reminder leave others untouched.
An update preserves the reminder ID, pause and daily acknowledgement; changed
schedules skip elapsed slots. No real tasks are completed or paused by tests.

## Release preparation

This release needs the new backend image, an updated secret-backed policy/catalog
and the matching `reminders.py` and `local_resources.py` on the Pi. Updating only
the backend would expose unsupported commands to the old Pi code.

After specific authorization for deployment, back up the Pi SQLite database and
the two matching modules. The existing dotfiles installer already copies these
modules from the reviewed home-k3s source; it does not need a host configuration
change. Install the modules together, restart the Pi client, and verify the
database integrity and existing task/acknowledgement counts.

`tools/aiy/reminder_prompt_upgrade.py` prepares a separate bundle from the current
memory-enabled bundle and operator-supplied policy/descriptions, without printing
or persisting secret content. Preserve the current bundle for rollback. A new
separate prompt ExternalSecret must retain the exact scoped one-minute refresh
exception in runtime-contract validation. Publish the verified image pin and
matching profile reference together through GitOps. Do not commit or push runtime
manifests without authorization.

Verify language behavior with synthetic audio and isolated task/HA consumers:
two shopping items, two feeding tasks, a mixed positive/negative sentence,
creation, an in-place edit, absence with known/unknown dates, automatic resume
and partial consumer failure. Never complete real shopping entries or household
tasks merely to test the feature. Local tool-dispatch tests do not establish
that the deployed voice model selects the right tasks.
