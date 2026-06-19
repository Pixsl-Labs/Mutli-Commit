# Multi-Commit — Next Stage Handoff

> Updated: 2026-06-14
> Purpose: Plan the next major stage of Multi-Commit as a Linux desktop project cockpit.

---

## Current Product Direction

Multi-Commit is no longer just a Git GUI.

It is becoming a **Linux desktop project cockpit** for developers, students, and project-heavy workflows.

The app should help users:

* manage multiple coding projects
* run project-specific commands
* commit/push/pull safely
* track project health
* manage roadmaps/checklists
* generate code reviews
* keep notes and activity history
* launch project sessions quickly
* eventually update itself from proper releases

---

## Current Layout Direction

The preferred future layout is:

```text
┌────────────────────┬─────────────────────────────┬──────────────────────────────┐
│ Project Sidebar    │ Project Dashboard            │ Git / Tools Panel             │
│                    │                             │                              │
│ Groups             │ Project commands             │ git add / commit / push        │
│ Projects           │ Repo health                  │ branch / stash / tag / pull    │
│ Pinned commands    │ Activity log                 │ notes / diff / history         │
│ Quick actions      │ Metrics                      │ output log                     │
└────────────────────┴─────────────────────────────┴──────────────────────────────┘
```

### Design principle

Keep the sidebar fast and simple.

Do **not** hide common actions behind right-click menus only.

The user likes one-click sidebar buttons, so preserve that ease of use. Add hover descriptions/tooltips to improve clarity.

---

## User Preferences

* Keep patches small and staged.
* Think first, then code.
* Do not implement everything at once.
* Work file-by-file.
* Preserve existing working features.
* Avoid large rewrites unless needed.
* GTK3 native Linux Mint/Cinnamon feel.
* Store data in JSON under:

```text
~/.config/multi-commit/
```

* Avoid heavy dependencies.
* End completed implementation patches with:

```bash
python3 main.py
git add <files>
git commit -m "<message>"
```

---

# Final Feature Roadmap

## 1. Self-update system

### Goal

Multi-Commit should detect when a real app update is available and offer to update itself.

### UX

Show a top-right coloured popup/banner when a new version/release exists.

Buttons:

```text
Update Now
Update Later
Close / Ignore
```

### Update Now

When clicked:

* open a centred update/progress dialog
* show progress/download/update bar
* run the update safely
* restart Multi-Commit automatically

### Update Later

Dropdown options:

```text
In 3 hours
When PC comes back online
When app closes
```

### Important

Do **not** update on every code change.

Use proper version tags/releases, for example:

```text
v1.1.0
v1.2.0
v1.3.0
```

Preferred flow:

```text
Check local version
Compare latest GitHub release/tag
Prompt if newer
Update via git pull/rebase or release download
Restart app
```

---

## 2. Sidebar hover help + optional advanced right-click

### Goal

Keep one-click sidebar buttons, but make them clearer.

### Add hover descriptions/tooltips

Examples:

```text
📁 Folder — Opens this project folder in file manager
💻 VSCode — Opens this project in VSCode
🖥 Terminal — Opens a terminal in this project folder
📋 Review — Generates a markdown code review
✅ Checklist — Opens this project roadmap/checklist
```

### Optional advanced right-click menu

Right-click should be for advanced actions only:

```text
Update project path
Move up
Move down
Assign to group
Remove from list
Pin project
```

### Important

Do not remove the simple one-click project buttons unless replacing them with something equally fast.

---

## 3. Per-project commands panel

### Goal

Each project should have its own commands, separate from global favourites.

This should live in the new **middle Project Dashboard** area, between the sidebar and the Git panel.

### Features

Each command should support:

```text
Add command
Edit command
Delete command
Copy command
Run silently
Run in terminal
Set as default
Pin command
Move up/down
```

### Pinned commands

Pinned commands should appear under the relevant project in the sidebar.

Example:

```text
▾ SentinelIR
  ⭐ Run app
  ⭐ Run tests
  ⭐ Generate logs
```

### Example commands

For SentinelIR:

```bash
python3 -m app.main generated.log
pytest
python3 -m app.main brute_force.log
```

For Multi-Commit:

```bash
python3 main.py
git status
git log --oneline -5
```

### Notes

This is one of the highest-value next features.

It makes Multi-Commit useful beyond Git.

---

## 4. Project Session Manager

### Goal

Each project should have a project/session launcher that opens a small control centre.

### Possible button name

```text
🚀 Launch Project Manager
```

or:

```text
🚀 Launch Session
```

### What it opens

A small window or middle-dashboard panel with:

```text
Open VSCode
Open terminal
Open checklist
Open notes
Open README
Run default command
Run pinned command
Generate code review
Start session
```

### Terminal session options

Add a number incrementer for terminals:

```text
Terminals to open:  [ - ] 2 [ + ]
```

Allow:

```text
Default command
Copy command
Run command
Open terminal layout
```

### Benefit

The user can start a project workflow in one click.

For example:

```text
Open VSCode
Open 2 terminals
Run pytest
Open checklist
Open notes
```

---

## 5. Commit message validator

### Goal

Help the user write cleaner commits.

### Behaviour

Validator updates live as the user types in the commit box.

Use **light/subtle colours**, not strong colours.

Examples:

```text
✅ Good commit: feat: add project command panel
⚠ Better with prefix: add command panel
❌ Commit message is empty
```

### Colour style

Use subtle background/border/label colouring:

```text
light green = good
light amber = warning
light red = empty/invalid
```

### Important

Do not block commits by default.

This should guide the user, not annoy them.

---

## 6. Repo health dashboard

### Goal

Show project status at a glance.

This should live in the **middle Project Dashboard** area, alongside per-project commands.

### Possible stats

```text
Branch: main
Changed files: 4
Untracked files: 2
Ahead/behind: +1 / -0
Latest commit: fix: restore command manager
Remotes: origin, uni
Stashes: 1
Tags: 3
```

### Benefit

The user can understand project state without terminal commands.

### Layout idea

Middle dashboard:

```text
Project Commands
Repo Health
Recent Activity
Metrics
```

---

## 7. Activity / audit log

### Goal

Track local actions performed through Multi-Commit.

This could appear at the bottom of the new middle dashboard, underneath project commands and repo health.

### Store in

```text
~/.config/multi-commit/activity.json
```

### Events to track

```text
Project opened
Commit created
Push success
Push failure
Command copied
Command run
Checklist opened
Checklist exported
Code review generated
Config exported
App updated
```

### UX

Display grouped by time:

```text
Today
Yesterday
Older
```

Example:

```text
10:32 committed: feat: add command colours
10:35 pushed to origin
10:40 generated code review
```

---

## 8. Config backup / restore

### Goal

Allow the user to move Multi-Commit settings to another machine.

### Include

```text
settings.json
recent.json
favourites.json
checklists.json
notes.json
project commands
project groups
custom commit templates
themes
activity log
```

### UX

Settings menu:

```text
Export Config Backup
Restore Config Backup
```

Export as:

```text
multi-commit-backup-YYYY-MM-DD.zip
```

Restore should warn before overwriting current config.

---

## 9. Checklist UX improvements

### Goal

Make checklist features clearer and easier to discover.

### Add selected-count label

Example:

```text
3 selected — Ctrl+Shift+Delete to delete
```

### Add shortcut help popup

Example:

```text
Ctrl-click = multi-select
Right-click = actions
Ctrl+Shift+Delete = bulk delete
Export = save checklist as markdown
Import = paste roadmap/checklist
```

### Add stronger selection visibility

Use clearer but still clean selected-state styling.

### Reordering

Consider:

```text
Move up/down buttons
Right-click move up/down
Drag-and-drop if safe in GTK3
```

---

## 10. Code Review Manager

### Goal

Add a dedicated manager for generated code reviews.

### Menu bar option

```text
Code Reviews
```

### Window features

```text
List code review markdown files
Open in VSCode
Reveal in folder
Copy path
Delete review
Regenerate review
Add review folder
Remove review folder
```

### Add review folder

Allow the user to add additional folders to scan.

Use a file chooser:

```text
Add Review Folder
```

This means the app can scan more than just:

```text
~/Projects/Code Reviews
```

### Benefit

This fits the user’s workflow because they frequently generate code reviews for Claude/ChatGPT.

---

## 11. Release builder

### Goal

Make proper releases for Multi-Commit.

### Features

```text
Version input: v1.2.0
Generate release notes
Create git tag
Push tag
Copy release notes
```

### Benefit

Pairs with self-update system.

The app can update from proper releases rather than random commits.

---

## 12. Background project status refresh

### Goal

Keep project state fresh while the app is open.

### Behaviour

Refresh periodically:

```text
sidebar git status
selected project dashboard
ahead/behind count
branch name
changed files count
```

### Setting

```text
Auto-refresh: Off / 30s / 1m / 5m
```

### Important

Avoid heavy refresh behaviour.

Pause or delay refresh while commands are running.

---

## 13. Smart command templates

### Goal

Allow commands to use variables.

### Variables

```text
{project}
{branch}
{name}
{venv}
```

### Example

```bash
cd {project} && source venv/bin/activate && pytest
```

### Benefit

Makes per-project commands much more reusable.

---

## 14. Project groups / folders

### Goal

Organise projects into collapsible groups in the sidebar.

### Sidebar top buttons

```text
+ Add Group
+ Add Project
```

### Example

```text
▾ Dissertation
  SentinelIR
  Log Analyser

▾ Tools
  Multi-Commit

▸ LifeWise
```

### Features

```text
Create group
Rename group
Delete group
Move project into group
Collapse/expand group
Reorder groups
```

### Benefit

Cleaner sidebar as the user adds more projects.

---

## 15. Pinned projects

### Goal

Important projects stay at the top.

### Example

```text
⭐ Pinned
  Multi-Commit
  SentinelIR
```

### Note

This may be optional if project groups are good enough, but it can still be useful.

---

## 16. Command palette

### Goal

Fast keyboard-first launcher.

### Shortcut

```text
Ctrl+K
```

### Searchable actions

```text
Open checklist
Run tests
Generate code review
Open terminal
Push all remotes
Open settings
Open command manager
Open project session
```

### Benefit

Power-user feature that makes the app feel modern.

---

## 17. Git safety guardrails

### Goal

Warn harder before destructive actions.

### Dangerous examples

```bash
git reset --hard
git clean -fd
git push --force
git branch -D
git stash drop
```

### UX

Show warning:

```text
This command can permanently remove work. Continue?
```

### Important

Do not make normal commands annoying.

Only warn for genuinely risky operations.

---

## 18. Project notes upgrade

### Goal

Upgrade simple notes into project note tabs.

### Tabs

```text
TODO
Ideas
Bugs
Handoff
```

### Removed idea

Do not add a dedicated Claude Prompt tab for now.

Keep the notes general and project-focused.

---

## 19. Handoff generator

### Goal

Generate a clean `handoff.md` for a project.

### UX

User clicks:

```text
Generate Handoff
```

A form/window opens with fields:

```text
Project purpose
Current features
Known bugs
Next steps
Useful commands
Recent changes
```

### Output

```text
handoff.md
```

### Auto-fill ideas

Can pull from:

```text
project notes
checklist
project commands
activity log
repo status
recent commits
```

### Benefit

Very useful for handing projects between ChatGPT/Claude chats or for documenting project state.

---

## 20. Local metrics dashboard

### Goal

Make progress visible and motivating.

### Best location

Include it in the middle Project Dashboard, likely under repo health/activity.

### Stats

```text
Commits this week
Pushes this week
Commands run
Checklist items completed
Code reviews generated
Most active project
```

### Benefit

Makes Multi-Commit feel alive and gives useful project progress feedback.

---

## 21. AI-friendly checklist import descriptions

### Goal

Improve checklist import so AI-generated roadmap/checklist tasks can include optional expandable descriptions.

### Current issue

When asking ChatGPT/Claude for a checklist, checkbox syntax like:

```text
- [ ] Build dashboard
```

can be awkward for the importer or cause formatting issues.

### New import instruction

When asking AI for a Multi-Commit checklist, instruct it:

```text
Do not use checkbox syntax like [ ] or [x].
Use normal bullets or numbered items only.
For extra detail under a task, use the indicator:
Descript:
```

### Preferred import format

Example:

```text
# Stage 1 — Project Dashboard

- Build middle dashboard layout
Descript: Add a new middle panel between the project sidebar and Git tools. It should show project commands, repo health, recent activity, and metrics in one visible view.

- Add repo health cards
Descript: Show branch, changed files, untracked files, ahead/behind, latest commit, remotes, stash count, and tag count.

- Add per-project commands section
Descript: Allow commands to be added, edited, copied, run silently, run in terminal, pinned, and reordered per project.
```

### UI behaviour

Imported checklist items should support an optional description field.

Checklist rows should stay clean by default:

```text
Build middle dashboard layout        ▸
```

When clicked or expanded:

```text
Build middle dashboard layout        ▾
Add a new middle panel between the project sidebar and Git tools. It should show project commands, repo health, recent activity, and metrics in one visible view.
```

### Data structure update

Current item structure is likely:

```python
{"text": "Build dashboard", "done": False}
```

Update to:

```python
{
    "text": "Build dashboard",
    "done": False,
    "description": "Optional longer explanation here."
}
```

### Parser behaviour

Update markdown import parser so:

* heading lines still become stages
* normal bullets/numbered lines become checklist items
* `Descript:` directly after an item becomes that item’s description
* multi-line descriptions should be supported if possible
* descriptions should not become separate checklist items
* old checklists without descriptions should still work

### Export behaviour

When exporting checklist markdown, include descriptions like:

```text
- [ ] Build middle dashboard layout
  Descript: Add a new middle panel between the project sidebar and Git tools.
```

### Benefit

This makes Multi-Commit checklists much better for AI workflows:

* short visible tasks
* hidden extra context
* cleaner imported roadmaps
* no need for checkbox syntax during import
* better handoff between ChatGPT/Claude and Multi-Commit

---

# Recommended Updated Build Order

## Stage 1 — Sidebar clarity + project organisation

Implement:

```text
Sidebar button tooltips
Advanced right-click menu for project management
Project groups
Add Group
Add Project
Optional pinned projects
```

Reason:

This improves navigation without touching risky Git logic.

---

## Stage 2 — Middle Project Dashboard foundation

Implement the new middle dashboard between sidebar and Git panel.

Initial sections:

```text
Project Commands
Repo Health
Recent Activity
Metrics
```

Reason:

This creates the core layout needed for most future features.

---

## Stage 3 — Per-project commands + pinned commands

Implement:

```text
project_commands.json
Add/edit/delete/copy/run commands
Pin command
Default command
Move commands up/down
Show pinned commands under project in sidebar
```

Reason:

This is one of the most useful features and fits the project cockpit direction.

---

## Stage 4 — Checklist import descriptions

Implement:

```text
Item description field
Descript: parser support
Expandable checklist item descriptions
Export descriptions back to markdown
AI checklist instructions in import dialog
```

Reason:

This is small-to-medium scope but very high value for AI-generated roadmaps.

---

## Stage 5 — Commit validator

Implement:

```text
Live commit message validation
Light green/amber/red feedback
Tooltip/help for conventional commits
No blocking by default
```

Reason:

Small, useful, low-risk, improves Git quality.

---

## Stage 6 — Repo health + background refresh

Implement:

```text
Repo health cards
Changed/untracked files
Ahead/behind
Latest commit
Remotes
Status refresh timer
Configurable refresh interval
```

Reason:

Makes the dashboard genuinely useful.

---

## Stage 7 — Activity log + metrics

Implement:

```text
activity.json
Activity timeline
Local metrics
Counts for commits/pushes/commands/checklists/code reviews
```

Reason:

Adds memory/history to the app.

---

## Stage 8 — Code Review Manager

Implement:

```text
Code Reviews menu
Review list window
Open/reveal/copy/delete/regenerate
Add review folder
```

Reason:

Strong match for user workflow.

---

## Stage 9 — Config backup / restore

Implement:

```text
Export zip backup
Restore zip backup
Confirm overwrite
Include settings/favourites/checklists/notes/project commands/groups/themes
```

Reason:

Mature app feature, useful before big updates.

---

## Stage 10 — Session Manager

Implement:

```text
Launch Project Manager
Number of terminals spinner
Default command
Open VSCode/checklist/notes/README
Start session button
```

Reason:

Powerful workflow feature once commands/dashboard exist.

---

## Stage 11 — Release builder + self-update system

Implement last:

```text
Release builder
Git tag creation
Release notes generation
Update checker
Update popup
Progress dialog
Restart app
```

Reason:

Powerful but risky. Better after core project structure is stable.

---

# Highest Priority Next Bundle

Recommended next implementation bundle:

```text
1. Sidebar tooltips + advanced project actions
2. Project groups / Add Group / Add Project
3. Middle Project Dashboard skeleton
```

This gives the app the right structure before adding more advanced behaviour.

---

# Notes For Claude / ChatGPT

Before coding, inspect the current files:

```text
ui/main_window.py
ui/project_list.py
ui/commit_panel.py
ui/checklist_window.py
core/checklists.py
core/project_manager.py
core/settings.py
```

Potential new files later:

```text
core/project_groups.py
core/project_commands.py
core/activity.py
ui/project_dashboard.py
ui/code_review_manager.py
ui/session_manager.py
ui/update_dialog.py
```

Implementation rules:

* Do not remove existing one-click project buttons yet.
* Add hover tooltips first.
* Keep project sidebar easy to use.
* Build the middle dashboard as a new component rather than bloating `main_window.py`.
* Avoid breaking checklist, command manager, and Git panels.
* Add checklist descriptions carefully with backward compatibility.
* Existing checklist items without descriptions must still work.
* Do not start self-update until release/version structure exists.
