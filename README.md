# Standings Sync

Alliance Auth app for cloning alliance standings and war targets to alts.

[![release](https://img.shields.io/pypi/v/aa-standingssync-zoo?label=release)](https://pypi.org/project/aa-standingssync-zoo/)
[![python](https://img.shields.io/pypi/pyversions/aa-standingssync-zoo)](https://pypi.org/project/aa-standingssync-zoo/)
[![django](https://img.shields.io/pypi/djversions/aa-standingssync-zoo?label=django)](https://pypi.org/project/aa-standingssync-zoo/)
[![license](https://img.shields.io/badge/license-MIT-green)](https://github.com/guarzo/aa-standingssync-zoo/blob/main/LICENSE)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

> **Note**: This is a fork of [aa-standingssync](https://gitlab.com/ErikKalkoken/aa-standingssync) maintained at [github.com/guarzo/aa-standingssync-zoo](https://github.com/guarzo/aa-standingssync-zoo)

## Content

- [Features](#features)
- [Screenshot](#screenshot)
- [How it works](#how-it-works)
- [Contact Sync Modes](#contact-sync-modes)
- [Installation](#installation)
- [Updating](#updating)
- [Settings](#settings)
- [Permissions](#permissions)
- [Admin Functions](#admin-functions)
- [Feedback](#feedback)
- [Change Log](CHANGELOG.md)

## Features

The main purpose of this app is to enable non-alliance characters to have the same standings view of other pilots in game as their alliance main. This e.g. allows non-alliance scouts to correctly report blues and non-blues. Or JF pilots can see which other non-alliance characters on grid not blues and therefore a potential threat.

Here is an high level overview of the main features:

- Synchronize alliance contacts to chosen non-alliance characters
- Supports coalition usage with multiple alliances in the same Alliance Auth installation
- Synchronize alliance war targets as contacts with terrible standing
- Automatically deactivates synchronization when a user ceases to be eligible (e.g. main left the alliance)

## Screenshot

Here is a screenshot of the main screen.

![Main Screen](https://i.imgur.com/xGdoqsp.png)

## How it works

To enable non-alliance members to use alliance standings the personal contact of that character are replaced with the alliance contacts.

## Contact Sync Modes

Standings Sync supports three contact synchronization modes:

### Replace Mode (Default)

`STANDINGSSYNC_REPLACE_CONTACTS = True` or `"replace"`

**Behavior:**
- Deletes ALL character contacts
- Replaces with alliance contacts only
- Personal contacts are NOT preserved

**Use Case:** Strict alliance-only contact lists

---

### Preserve Mode

`STANDINGSSYNC_REPLACE_CONTACTS = False` or `"preserve"`

**Behavior:**
- Keeps ALL character contacts unchanged
- Does NOT sync alliance contacts
- Only updates war targets (if enabled)

**Use Case:** Manual contact management, no alliance sync

---

### Merge Mode

`STANDINGSSYNC_REPLACE_CONTACTS = "merge"`

**Behavior:**
- Preserves personal contacts
- Adds new alliance contacts with +5.0 standing
- Removes alliance contacts when removed from alliance list
- Updates alliance contact standings to +5.0
- Handles war targets normally (if enabled)

**Use Case:** Automatic alliance sync while keeping personal contacts

**Example:**
```python
# In your Django settings (local.py)
STANDINGSSYNC_REPLACE_CONTACTS = "merge"
```

**How It Works:**
- Alliance contacts are tracked using the "ALLIANCE" label (similar to "WAR TARGETS" label)
- All alliance contacts are automatically marked with the ALLIANCE label and +5.0 standing
- Personal contacts (without ALLIANCE label) are never modified
- When an entity leaves the alliance, their contact is automatically removed (identified by label)
- When an entity joins the alliance, their contact is automatically added with the ALLIANCE label

**Requirements:**
- You must create an "ALLIANCE" contact label in-game for each synced character
- The label name is case-insensitive and can be configured via `STANDINGSSYNC_ALLIANCE_CONTACTS_LABEL_NAME` setting
- Without the label, merge mode will still add/update alliance contacts, but cannot remove old ones

---

### Migration Guide

**Existing Users:**
- Boolean values (`True`/`False`) continue to work for backward compatibility
- `True` is automatically converted to `"replace"` mode
- `False` is automatically converted to `"preserve"` mode

**To Enable Merge Mode:**
```python
# In your local.py or settings file
STANDINGSSYNC_REPLACE_CONTACTS = "merge"
```

## Installation

### Step 1 - Check Preconditions

Please make sure you meet all preconditions before proceeding:

1. Standings Sync is a plugin for [Alliance Auth](https://gitlab.com/allianceauth/allianceauth). If you don't have Alliance Auth running already, please install it first before proceeding. (see the official [AA installation guide](https://allianceauth.readthedocs.io/en/latest/installation/auth/allianceauth/) for details)

2. Standings Sync needs the app [django-eveuniverse](https://gitlab.com/ErikKalkoken/django-eveuniverse) to function. Please make sure it is installed, before continuing.

### Step 2 - Install app

Install into AA virtual environment with PIP install from PyPI:

```bash
pip install aa-standingssync-zoo
```

### Step 3 - Update Eve Online app

Update the Eve Online app used for authentication in your AA installation to include the following scopes:

```plain
esi-characters.read_contacts.v1
esi-characters.write_contacts.v1
esi-alliances.read_contacts.v1
```

### Step 4 - Configure AA settings

Configure your AA settings (`local.py`) as follows:

Add `'standingssync'` to `INSTALLED_APPS`

Add these lines add to bottom of your settings file:

```python
# settings for standingssync
CELERYBEAT_SCHEDULE['standingssync.run_regular_sync'] = {
    'task': 'standingssync.tasks.run_regular_sync',
    'schedule': crontab(minute=0, hour='*/2')
}
```

Please also see the [settings](#settings) section for more configuration options. For example a setting is required to enable syncing war targets.

### Step 5 - Finalize installation into AA

Run migrations & copy static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
```

Restart your supervisor services for AA

### Step 6 - Setup permissions

Now you can access Alliance Auth and setup permissions for your users. See section "Permissions" below for details.

### Step 7 - Setup alliance character

Finally you need to set the alliance character that will be used for fetching the alliance contacts / standing. Just click on "Set Alliance Character" and add the requested token. Note that only users with the appropriate permission will be able to see and use this function.

Once an alliance character is set the app will immediately start fetching alliance contacts. Wait a minute and then reload the page to see the result.

That's it. The Standing Sync app is fully installed and ready to be used.

## Updating

To update your existing installation of Alliance Freight first enable your virtual environment.

Then run the following commands from your AA project directory (the one that contains `manage.py`).

```bash
pip install -U aa-standingssync-zoo
```

```bash
python manage.py migrate
```

```bash
python manage.py collectstatic --noinput
```

Finally restart your AA supervisor services.

## Settings

Here is a list of available settings for this app. They can be configured by adding them to your AA settings file (`local.py`). If they are not set the defaults are used.

Name|Description|Default
--|--|--
`STANDINGSSYNC_ADD_WAR_TARGETS`|When enabled will automatically add or set war targets  with standing = -10 to synced characters.|`False`
`STANDINGSSYNC_ALLIANCE_CONTACTS_LABEL_NAME`|Name of EVE contact label for alliance contacts in merge mode. Needs to be created by the user for each synced character when using merge mode. Required to ensure that old alliance contacts are removed when entities leave the alliance. Not case sensitive.|`ALLIANCE`
`STANDINGSSYNC_CHAR_MIN_STANDING`|Minimum standing a character needs to have in order to get alliance contacts. Any char with a standing smaller than this value will be rejected. Set to `0.0` if you want to allow neutral alts to sync.|`0.1`
`STANDINGSSYNC_REPLACE_CONTACTS`|Contact sync mode. Options: `True` or `"replace"` (replace all contacts with alliance contacts), `False` or `"preserve"` (preserve all contacts, don't sync alliance), `"merge"` (merge alliance contacts with personal contacts). See [Contact Sync Modes](#contact-sync-modes) for details.|`True`
`STANDINGSSYNC_STORE_ESI_CONTACTS_ENABLED`|Wether to store contacts received from ESI to disk. This is for debugging.|`False`
`STANDINGSSYNC_SYNC_TIMEOUT`|Duration in minutes after which a delayed sync for managers and characters is reported as down. This value should be aligned with the frequency of the sync task.|`180`
`STANDINGSSYNC_WAR_TARGETS_LABEL_NAME`|Name of EVE contact label for war targets. Needs to be created by the user for each synced character. Required to ensure that war targets are deleted once they become invalid. Not case sensitive.|`WAR TARGETS`

## Permissions

This app only uses two permission. One for enabling this app for users and one for enabling users to add alliances for syncing.

Name | Purpose | Code
-- | -- | --
Can add synced character |Enabling the app for a user. This permission should be enabled for everyone who is allowed to use the app (e.g. Member state) |  `add_syncedcharacter`
Can add alliance manager |Enables adding alliances for syncing by setting the character for fetching alliance contacts. This should be limited to users with admins / leadership privileges. |  `add_syncmanager`

## Admin functions

Admins will find a "Standings Sync" section on the admin page. This section provides the following features:

- See a list of all setup alliances with their sync status

- See a list of all enabled characters with their current sync status

- Manually remove characters / alliances from sync

- Manually start the sync process for characters / alliances

## Feedback

If you encounter any bugs or would like to request a new feature please open an issue on [GitHub](https://github.com/guarzo/aa-standingssync-zoo/issues).
