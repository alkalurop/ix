# Mac automation scripts

Small, read-only helpers for Apple Contacts and similar macOS-only tasks. **Run on the Mac**, not in a cloud agent terminal.

## Install to `~/automation`

From your ix clone:

```bash
cd ~/github/ixamal/ix
./automation/install.sh
```

That copies scripts into `${HOME}/automation` (default). Override destination:

```bash
AUTOMATION_HOME=~/automation ./automation/install.sh
```

## Contacts

| Script | Purpose |
|--------|---------|
| `contacts/list-first.sh` | Print the first N cards (AppleScript order); default N=2 |
| `contacts/duplicate-by-name.sh` | Groups cards with the same First + Last name |

Examples:

```bash
~/automation/contacts/list-first.sh
~/automation/contacts/list-first.sh 5
~/automation/contacts/duplicate-by-name.sh
```

Grant **Terminal → Contacts** in System Settings if macOS prompts.

## Cloud agents

Cursor cloud projects **cannot** execute these (Linux, no Contacts). Use Mac Terminal, or connect a [self-hosted worker](https://cursor.com/docs/cloud-agent/self-hosted/my-machines) so an agent can run commands on your Mac.
