"""Permission helper functions for standingsmanager.

This module provides helper functions for checking user permissions
in the standings management system.
"""

from django.contrib.auth.models import User


def user_can_request_standings(user: User) -> bool:
    """Check if user has permission to request standings.

    Args:
        user: User object to check

    Returns:
        True if user can request standings, False otherwise
    """
    return user.has_perm("standingsmanager.add_syncedcharacter")


def user_can_approve_standings(user: User) -> bool:
    """Check if user has permission to approve standing requests.

    Args:
        user: User object to check

    Returns:
        True if user can approve standings, False otherwise
    """
    return user.has_perm("standingsmanager.approve_standings")


def user_can_manage_standings(user: User) -> bool:
    """Check if user has permission to manage standings database.

    Args:
        user: User object to check

    Returns:
        True if user can manage standings, False otherwise
    """
    return user.has_perm("standingsmanager.manage_standings")


def user_can_view_audit_log(user: User) -> bool:
    """Check if user has permission to view audit log.

    Args:
        user: User object to check

    Returns:
        True if user can view audit log, False otherwise
    """
    return user.has_perm("standingsmanager.view_auditlog")
