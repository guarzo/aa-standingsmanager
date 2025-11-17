# AA Standings Manager

Alliance Auth app for managing and synchronizing EVE Online standings across characters.

[![release](https://img.shields.io/pypi/v/aa-standingsmanager?label=release)](https://pypi.org/project/aa-standingsmanager/)
[![python](https://img.shields.io/pypi/pyversions/aa-standingsmanager)](https://pypi.org/project/aa-standingsmanager/)
[![django](https://img.shields.io/pypi/djversions/aa-standingsmanager?label=django)](https://pypi.org/project/aa-standingsmanager/)
[![license](https://img.shields.io/badge/license-MIT-green)](https://github.com/guarzo/aa-standingsmanager/blob/main/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Version 0.0.1** - Initial release. Complete architectural rewrite with persistent standings database, request/approval workflow, and character-level synchronization.

## Overview

AA Standings Manager is a comprehensive standings management system for Alliance Auth that enables organizations to:
- Manage a persistent database of approved standings (characters, corporations, alliances)
- Implement a request/approval workflow for new standings
- Automatically synchronize standings to member characters via ESI
- Track and audit all standings changes
- Support flexible organizational structures (alliances, coalitions, corporations)

This is a complete refactor that combines and improves upon features from:
- [aa-standingssync](https://gitlab.com/ErikKalkoken/aa-standingssync) by Erik Kalkoken
- [aa-standingsrequests](https://gitlab.com/colcrunch/standingsrequests) by colcrunch



## Key Features

### Persistent Standings Database
- **Centralized Management**: Single source of truth for all approved standings
- **Entity Types**: Support for characters, corporations, and alliances
- **Flexible Standing Values**: Configurable standing values (-10 to +10)
- **Audit Trail**: Complete history of all standings changes

### Request/Approval Workflow
- **User Requests**: Users can request standings for their characters or corporations
- **Approver Queue**: Designated approvers review and process requests
- **Validation**: Automatic validation of ESI scopes and token coverage
- **Revocations**: Support for removing standings with approval workflow

### Automated Synchronization
- **Character-Level Sync**: Each user's characters sync independently
- **ESI Integration**: Direct integration with EVE Online ESI API
- **Contact Labels**: Uses configurable contact labels for organization
- **Automatic Updates**: Periodic synchronization keeps contacts current
- **Error Handling**: Robust retry logic with exponential backoff

### Flexible Configuration
- **State-Based Scopes**: Different ESI scope requirements per Auth state
- **Configurable Labels**: Set your organization's contact label name
- **Sync Intervals**: Control how often syncs occur
- **Auto-Validation**: Automatic removal of ineligible characters

### Security & Permissions
- **Three Permission Levels**: Basic users, approvers, and administrators
- **Token Validation**: Ensures users own all characters in corporation requests
- **Eligibility Checking**: Automatic deactivation when users lose access
- **Comprehensive Auditing**: All actions logged with user attribution

## How It Works

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                    Persistent Standings DB                   │
│  (Characters, Corporations, Alliances with Standing Values) │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Request/Approval Workflow                       │
│  User Requests → Approver Reviews → Standing Added/Removed  │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│              Character Synchronization                       │
│  Each User's Characters Sync Standings to ESI Contacts      │
└─────────────────────────────────────────────────────────────┘
```

### Workflow Example

1. **User Requests Standing**
   - User navigates to "Request Standings" page
   - Selects their character or corporation
   - System validates ESI scopes and ownership
   - Request created in PENDING state

2. **Approver Reviews Request**
   - Approver sees request in "Manage Requests" queue
   - Reviews requester information and affiliations
   - Approves or rejects the request
   - On approval: Standing entry created in database

3. **Automatic Synchronization**
   - All synced characters receive the update
   - ESI API updates contact lists
   - Contacts marked with organization label
   - Users see updated standings in-game

4. **Ongoing Management**
   - Users can request removal of standings (revocation)
   - System automatically removes ineligible characters
   - Audit log tracks all changes
   - Periodic sync keeps everything current

## Requirements

- **Alliance Auth**: v4.0.0 or higher
- **Python**: 3.11, 3.12, or 3.13
- **ESI Scopes Required**:
  - `esi-characters.read_contacts.v1` (read character contacts)
  - `esi-characters.write_contacts.v1` (manage character contacts)
  - Additional scopes configurable per Auth state

## Installation

### 1. Install the Package

```bash
pip install aa-standingsmanager
```

### 2. Add to Django Settings

Edit your Alliance Auth `local.py` settings file:

```python
INSTALLED_APPS = [
    # ... other apps ...
    'standingsmanager',
]
```

### 3. Run Migrations

```bash
python manage.py migrate standingsmanager
```

### 4. Restart Services

```bash
# Restart Gunicorn/UWSGI
systemctl restart allianceauth

# Restart Celery workers
systemctl restart allianceauth-worker
systemctl restart allianceauth-beat
```

### 5. Configure Celery Beat (if not using systemd timers)

Add to your `local.py`:

```python
from celery.schedules import crontab

CELERYBEAT_SCHEDULE = {
    # ... other tasks ...
    'standingsmanager_sync_all': {
        'task': 'standingsmanager.tasks.run_regular_sync',
        'schedule': crontab(minute='*/30'),  # Every 30 minutes
    },
    'standingsmanager_validate_all': {
        'task': 'standingsmanager.tasks.run_regular_validation',
        'schedule': crontab(hour='*/6'),  # Every 6 hours
    },
}
```

### 6. Load Static Files

```bash
python manage.py collectstatic --noinput
```

## Configuration

### Required Settings

```python
# Organization's contact label name (users create this in-game)
STANDINGS_LABEL_NAME = "MY_ORG"  # Change to your org name
```

### Optional Settings

```python
# Sync interval in minutes (default: 30)
STANDINGS_SYNC_INTERVAL = 30

# Sync timeout in minutes (default: 180)
STANDINGS_SYNC_TIMEOUT = 180

# Default standing value for new standings (default: 5.0)
STANDINGS_DEFAULT_STANDING = 5.0

# Auto-validation interval in minutes (default: 360)
STANDINGS_AUTO_VALIDATE_INTERVAL = 360

# ESI scope requirements per Auth state (default: {})
STANDINGS_SCOPE_REQUIREMENTS = {
    "Member": [],  # No additional scopes for members
    "Blue": ["esi-killmails.read_killmails.v1"],  # Example: Blues need killmail access
}
```

### Settings Validation

The app validates all settings on startup and will raise errors for invalid configurations:
- `STANDINGS_LABEL_NAME` must be a non-empty string
- `STANDINGS_SYNC_INTERVAL` must be greater than 0
- `STANDINGS_DEFAULT_STANDING` must be between -10 and +10
- `STANDINGS_SCOPE_REQUIREMENTS` must be a dictionary

## Permissions

The app uses three permission levels:

| Permission | Code Name | Description |
|------------|-----------|-------------|
| **Basic User** | `standingsmanager.add_syncedcharacter` | Request standings, manage own synced characters |
| **Approver** | `standingsmanager.approve_standings` | Approve/reject standing requests and revocations |
| **Administrator** | `standingsmanager.manage_standings` | Full access to standings database via Django admin |
| **Auditor** | `standingsmanager.view_auditlog` | View audit log (read-only) |

### Granting Permissions

**Via Django Admin:**
1. Go to Admin → Authentication and Authorization → Groups
2. Select or create a group
3. Add desired permissions
4. Assign users to the group

**Recommended Setup:**
- All members: `add_syncedcharacter` (basic access)
- Directors/Leadership: `approve_standings` (approval queue)
- IT/Admin: `manage_standings` (database management)
- Compliance: `view_auditlog` (audit access)

## User Guide

### Requesting Standings

1. **Navigate to Standings Menu**
   - Click "Standings Sync" in Alliance Auth menu
   - Select "Request Standings"

2. **Select Character or Corporation**
   - Character requests: Click "Request Standing" next to your character
   - Corporation requests: Ensure you have tokens for ALL characters in corp

3. **Wait for Approval**
   - Your request appears in the approver queue
   - You'll receive a notification when processed

4. **Add Character to Sync**
   - Navigate to "My Synced Characters"
   - Click "Add to Sync" for characters you want to sync
   - **Important**: Create the contact label in-game first!

### Creating Contact Label In-Game

**CRITICAL STEP**: Before adding characters to sync, create the contact label in EVE:

1. Open your in-game "People & Places" window (Alt+E)
2. Click the "Contacts" tab
3. Right-click in the labels section → "Add Label"
4. Enter the exact label name from settings (e.g., "MY_ORG")
5. Click "OK"

Now you can add the character to sync in Alliance Auth.

### Managing Your Standings

**View Status:**
- Green checkmark: Sync working correctly
- Orange warning: Needs attention (stale sync, missing label)
- Red X: Error (check error message)

**Remove Standing:**
- Go to "Request Standings"
- Click "Remove Standing" next to approved character/corp
- Approver must approve the revocation

**Troubleshooting Sync:**
- Verify contact label exists in-game (exact name match)
- Check ESI token is valid (re-add character if needed)
- Check "My Synced Characters" for error messages
- Contact your administrator if issues persist


## Admin Guide

### Approver Workflow

**Managing Requests:**
1. Navigate to "Manage Requests"
2. Review pending requests
   - Check requester information
   - Verify affiliations and scopes
   - Review request age
3. Click "Approve" or "Reject"
4. System automatically triggers sync for all characters

**Managing Revocations:**
1. Navigate to "Manage Revocations"
2. Review pending revocation requests
3. Approve to remove standing, Reject to keep it
4. System syncs removal to all characters

**Best Practices:**
- Review requests promptly (check daily)
- Verify requester identity for high-value standings
- Use rejection notes to explain decisions
- Monitor auto-revocations (system-initiated)

### Django Admin Functions

**Standings Entry Management:**
- View all approved standings
- Filter by entity type, standing value, date
- Manually add/edit/delete standings
- Bulk actions available

**Request/Revocation Management:**
- View all requests (pending, approved, rejected)
- Bulk approve/reject actions
- Read-only (use UI or actions for changes)

**Synced Character Management:**
- View all synced characters
- Check sync status (fresh, stale, errors)
- Force manual sync for troubleshooting
- Validate eligibility (removes ineligible)

**Audit Log:**
- View all actions (approvals, rejections, removals)
- Filter by action type, date, user
- Export to CSV for compliance
- Read-only (immutable log)

F
## Troubleshooting

### Common Issues

**"Contact label not found"**
- **Cause**: Character doesn't have the configured label in-game
- **Fix**: Create the label in EVE (see "Creating Contact Label In-Game" above)

**"Missing required ESI scopes"**
- **Cause**: Character token doesn't have required scopes
- **Fix**: Re-add character in Alliance Auth to grant scopes

**"Token is invalid or expired"**
- **Cause**: ESI token expired or revoked
- **Fix**: Re-authenticate character in Alliance Auth

**"Sync is stale"**
- **Cause**: Sync hasn't run recently (could be ESI issues)
- **Fix**: Check Celery workers are running, check ESI status

**"Corporation request failed - missing tokens"**
- **Cause**: Don't have tokens for all characters in corporation
- **Fix**: Add all your corp characters to Alliance Auth with required scopes

### Checking System Health

**Verify Celery is Running:**
```bash
systemctl status allianceauth-worker
systemctl status allianceauth-beat
```

**Check Task Logs:**
```bash
# View Celery worker logs
journalctl -u allianceauth-worker -f

# Check for sync errors
grep "ERROR" /var/log/allianceauth/allianceauth.log | grep standingsmanager
```

**Force Manual Sync (Admin):**
1. Go to Django Admin → Synced Characters
2. Select character(s)
3. Choose "Force sync selected characters"
4. Click "Go"

**Check ESI Status:**
- Visit [EVE Online ESI Status](https://esi.evetech.net/)
- Check for ongoing outages or issues

## FAQ

**Q: What happened to alliance contact sync and war targets?**
A: Version 2.0 uses a persistent standings database instead of cloning alliance contacts. War targets feature has been removed. Each organization manages their own standings list.

**Q: Can I migrate from version 1.x?**
A: Version 2.0 is a complete rewrite with a new database schema. See [MIGRATION_GUIDE.md](MIGRATION_GUIDE.md) for migration instructions.

**Q: Do all my characters need to be in the same alliance?**
A: No! This system works for any organizational structure. Characters just need appropriate permissions and ESI scopes.

**Q: How often do contacts sync?**
A: By default every 30 minutes. Configurable via `STANDINGS_SYNC_INTERVAL` setting.

**Q: What happens if I lose alliance membership?**
A: The system automatically detects permission loss and removes your characters from sync. Your in-game contacts remain until manually deleted.

**Q: Can I have personal contacts and org contacts?**
A: Yes! The system only manages contacts with your organization's label. Other contacts are untouched.

**Q: How do I add a corporation standing?**
A: Request a corporation standing from the UI. You must have valid tokens for ALL characters in that corp you own in Alliance Auth.

**Q: What standing value is used for synced contacts?**
A: The value in the standings database (default: +5.0, configurable per entry).

**Q: Can I see who approved a standing?**
A: Yes! Check the Audit Log (requires `view_auditlog` permission) or view standing details in admin.

## Credits

### Original Projects

**AA-StandingsSync**
- **Author**: Erik Kalkoken
- **Repository**: https://gitlab.com/ErikKalkoken/aa-standingssync
- **Features Adapted**:
  - SyncedCharacter model concept
  - ESI contact synchronization logic
  - Contact label management
  - Background task architecture

**AA-StandingsRequests**
- **Repository**: https://gitlab.com/colcrunch/standingsrequests
- **Features Adapted**:
  - Request/approval workflow
  - StandingRequest and StandingRevocation models
  - Approver permission system
  - Scope requirements per Auth state
  - Audit logging

### Key Innovations in Version 2.0

- **Persistent Standings Database**: Central standings management vs. cloning alliance contacts
- **Character-Level Sync**: Each user's characters sync independently vs. alliance manager approach
- **Combined Workflows**: Integrated request + sync in one application
- **Configurable Labels**: Support any organizational structure
- **Enhanced Validation**: Comprehensive scope and token validation
- **Improved Error Handling**: Retry logic with exponential backoff


### Maintainer

- **Current Maintainer**: guarzo
- **Repository**: https://github.com/guarzo/aa-standingsmanager

## Support

### Getting Help

- **Documentation**: See docs in this repository
- **Issues**: Report bugs at https://github.com/guarzo/aa-standingsmanager/issues
- **Discussions**: Community discussions on GitHub

### Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Write tests for new features
4. Submit a pull request


### Security Issues

For security vulnerabilities, please email the maintainer directly rather than opening a public issue.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for version history and release notes.

---

**Version**: 0.0.1
**Last Updated**: 2025-11-16
**Status**: Initial Release
