# Admin Overhaul — Design

Branch `admin-overhaul`, cut from `worktree-contact-page-revamp` with `worktree-team-page-revamp` merged in.

## Goals

1. Fewer forms. Common admin edits happen in place and save themselves.
2. Self sign-up, gated by admin approval.
3. Drag and drop people between teams.
4. Team members maintain their own team's page.

## Decisions (confirmed with the user)

- **Sign-up:** public `/signup` (username, email, password, optional requested team). The account is
  `status: 'pending'` and cannot sign in until an admin approves it. Approving sets the role and,
  optionally, the team in one step. Rejecting deletes the request.
- **Self-edit scope:** a member of a team can edit that team's nickname, tagline, robot specs, goals,
  notebook link and hero image, plus their own roster card (name, role, sub-team, photo). Team
  number, season/division/history fields, CAD file, awards, other members' cards and deletion stay
  with editors and admins.

## Data model

- `users.status`: `'active'` (missing = active, so existing accounts keep working) or `'pending'`.
  `users.requested_team`, `users.created_at` are set on sign-up.
- `teams.members[].member_id`: stable hex id per roster entry, backfilled on first admin load, so a
  drag can name one member without relying on list position.
- A user account sits on at most one roster. Moving a linked member removes them from every other
  team.

## Roles

`member < editor < admin`, now hierarchical (`role_required('member')` admits editors, which it did not
before). Editors can use the team editor on any team; only admins see `/admin`.

## Surfaces

- **`/admin`**
  - *People* tab (replaces *Users*): an approvals queue at the top, with a role select, a team select,
    and Approve/Reject buttons. Below it, a roster board: one column per team plus *Unassigned*.
    Cards drag between columns, with a keyboard fallback ("Move to…" select on each card). Every move
    shows a toast with **Undo**. The role select on each user row saves on change. The create-user
    form moves into a collapsible "Add someone manually" section.
  - *Statistics* and *Awards* numbers become steppers that autosave. The *Update* buttons go away.
  - *Events* rows edit in place: click a field, type, and it saves on blur.
  - *Teams* tab becomes a list of team cards linking to the shared team editor, plus a small
    "new team" form that only needs the team number.
- **`/manage/team/<id>`** is the shared team editor for team members, editors and admins. Fields are
  inline inputs that autosave on blur and show a "Saved" tick. Goals, members and journey rows are
  added and removed in place. Admin-only fields render only for editors and admins, and the server
  enforces the same whitelist.
- **Nav:** logged-in users on a roster get a **My Team** link. The login page links to **Create account**.

## API (JSON, CSRF header, same-origin)

| Method | Path | Who |
|---|---|---|
| POST | `/signup` | public (rate limited, form post) |
| POST | `/admin/api/users/<id>/approve` `{role, team_id?}` | admin |
| POST | `/admin/api/users/<id>/reject` | admin |
| POST | `/admin/api/users/<id>/role` `{role}` | admin |
| POST | `/admin/api/roster/move` `{member_id?, user_id?, to_team_id?}` | admin |
| POST | `/admin/api/stats` `{field, value}` | admin |
| POST | `/admin/api/awards/<id>` `{count}` | admin |
| POST | `/admin/api/events/<id>` `{field, value}` | admin |
| POST | `/api/team/<id>/field` `{field, value}` | team member (whitelist) / editor / admin |
| POST | `/api/team/<id>/list/<goals\|journey>` `{items}` | team member / editor / admin |
| POST | `/api/team/<id>/member/<member_id>` `{field, value}` | self, or editor / admin |
| POST | `/api/team/<id>/member` `{name}` / DELETE `/api/team/<id>/member/<member_id>` | editor / admin |
| POST | `/api/team/<id>/image` multipart `hero_image` / `stl_file` / `member_photo` + `member_id` | per field |

Every write is logged to `activities`.
