"""Model managers for standingsmanager - Refactored for AA Standings Manager."""

from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import models


class StandingsEntryManager(models.Manager):
    """Manager for StandingsEntry model."""

    def for_entity_type(self, entity_type: str):
        """Filter standings by entity type.

        Args:
            entity_type: One of 'character', 'corporation', or 'alliance'

        Returns:
            QuerySet of StandingsEntry objects
        """
        return self.filter(entity_type=entity_type)

    def all_characters(self):
        """Get all character standings."""
        return self.for_entity_type("character")

    def all_corporations(self):
        """Get all corporation standings."""
        return self.for_entity_type("corporation")

    def all_alliances(self):
        """Get all alliance standings."""
        return self.for_entity_type("alliance")

    def for_entity(self, eve_entity):
        """Get standing for a specific entity.

        Args:
            eve_entity: EveEntity object or ID

        Returns:
            StandingsEntry object or None
        """
        if hasattr(eve_entity, "id"):
            eve_entity = eve_entity.id

        try:
            return self.get(eve_entity_id=eve_entity)
        except self.model.DoesNotExist:
            return None


class StandingRequestManager(models.Manager):
    """Manager for StandingRequest model."""

    def pending(self):
        """Get all pending requests.

        Returns:
            QuerySet of pending StandingRequest objects
        """
        return self.filter(state="pending")

    def approved(self):
        """Get all approved requests.

        Returns:
            QuerySet of approved StandingRequest objects
        """
        return self.filter(state="approved")

    def rejected(self):
        """Get all rejected requests.

        Returns:
            QuerySet of rejected StandingRequest objects
        """
        return self.filter(state="rejected")

    def for_user(self, user: User):
        """Get all requests made by a specific user.

        Args:
            user: User object

        Returns:
            QuerySet of StandingRequest objects
        """
        return self.filter(requested_by=user)

    def create_character_request(self, character, user: User):
        """Create a standing request for a character.

        Args:
            character: EveCharacter object
            user: User making the request

        Returns:
            StandingRequest object

        Raises:
            ValidationError: If validation fails
        """
        from eveuniverse.models import EveEntity

        # Get or create EveEntity for character
        eve_entity, _ = EveEntity.objects.get_or_create(
            id=character.character_id,
            defaults={
                "name": character.character_name,
                "category": EveEntity.CATEGORY_CHARACTER,
            },
        )

        # Check for duplicate pending request
        if self.filter(eve_entity=eve_entity, state="pending").exists():
            raise ValidationError(
                f"A pending request already exists for {character.character_name}"
            )

        # Check if already in standings
        from .models import StandingsEntry

        if StandingsEntry.objects.filter(eve_entity=eve_entity).exists():
            raise ValidationError(f"{character.character_name} already has a standing")

        # Create request
        request = self.create(
            eve_entity=eve_entity,
            entity_type="character",
            requested_by=user,
        )

        return request

    def create_corporation_request(self, corporation, user: User):
        """Create a standing request for a corporation.

        Args:
            corporation: EveCorporationInfo object
            user: User making the request

        Returns:
            StandingRequest object

        Raises:
            ValidationError: If validation fails
        """
        from eveuniverse.models import EveEntity

        # Get or create EveEntity for corporation
        eve_entity, _ = EveEntity.objects.get_or_create(
            id=corporation.corporation_id,
            defaults={
                "name": corporation.corporation_name,
                "category": EveEntity.CATEGORY_CORPORATION,
            },
        )

        # Check for duplicate pending request
        if self.filter(eve_entity=eve_entity, state="pending").exists():
            raise ValidationError(
                f"A pending request already exists for {corporation.corporation_name}"
            )

        # Check if already in standings
        from .models import StandingsEntry

        if StandingsEntry.objects.filter(eve_entity=eve_entity).exists():
            raise ValidationError(
                f"{corporation.corporation_name} already has a standing"
            )

        # Create request
        request = self.create(
            eve_entity=eve_entity,
            entity_type="corporation",
            requested_by=user,
        )

        return request


class StandingRevocationManager(models.Manager):
    """Manager for StandingRevocation model."""

    def pending(self):
        """Get all pending revocations.

        Returns:
            QuerySet of pending StandingRevocation objects
        """
        return self.filter(state="pending")

    def approved(self):
        """Get all approved revocations.

        Returns:
            QuerySet of approved StandingRevocation objects
        """
        return self.filter(state="approved")

    def rejected(self):
        """Get all rejected revocations.

        Returns:
            QuerySet of rejected StandingRevocation objects
        """
        return self.filter(state="rejected")

    def for_user(self, user: User):
        """Get all revocations requested by a specific user.

        Args:
            user: User object

        Returns:
            QuerySet of StandingRevocation objects
        """
        return self.filter(requested_by=user)

    def auto_revocations(self):
        """Get all system-initiated auto-revocations.

        Returns:
            QuerySet of auto-revocation StandingRevocation objects
        """
        return self.filter(requested_by__isnull=True)

    def create_for_entity(
        self, eve_entity, reason: str, user: User = None, entity_type: str = None
    ):
        """Create a revocation request for an entity.

        Args:
            eve_entity: EveEntity object
            reason: Reason for revocation (from Reason choices)
            user: User requesting revocation (None for auto-revocations)
            entity_type: Entity type override (detected from eve_entity if None)

        Returns:
            StandingRevocation object

        Raises:
            ValidationError: If validation fails
        """
        # Detect entity type if not provided
        if entity_type is None:
            from eveuniverse.models import EveEntity

            entity_type_map = {
                EveEntity.CATEGORY_CHARACTER: "character",
                EveEntity.CATEGORY_CORPORATION: "corporation",
                EveEntity.CATEGORY_ALLIANCE: "alliance",
            }
            entity_type = entity_type_map.get(eve_entity.category)
            if entity_type is None:
                raise ValidationError(f"Unknown entity category: {eve_entity.category}")

        # Check if standing exists
        from .models import StandingsEntry

        if not StandingsEntry.objects.filter(eve_entity=eve_entity).exists():
            raise ValidationError(f"No standing exists for {eve_entity.name}")

        # Check for duplicate pending revocation
        if self.filter(eve_entity=eve_entity, state="pending").exists():
            raise ValidationError(
                f"A pending revocation already exists for {eve_entity.name}"
            )

        # Create revocation
        revocation = self.create(
            eve_entity=eve_entity,
            entity_type=entity_type,
            requested_by=user,
            reason=reason,
        )

        return revocation


class AuditLogManager(models.Manager):
    """Manager for AuditLog model.

    This manager prevents updates and deletions of audit log entries.
    """

    def update(self, **kwargs):
        """Prevent updates to audit log."""
        raise ValidationError("Audit log entries cannot be updated")

    def delete(self):
        """Prevent deletion of audit log entries."""
        raise ValidationError("Audit log entries cannot be deleted")

    def for_user(self, user: User):
        """Get all audit logs where user was the actor.

        Args:
            user: User object

        Returns:
            QuerySet of AuditLog objects
        """
        return self.filter(actioned_by=user)

    def for_requester(self, user: User):
        """Get all audit logs where user was the requester.

        Args:
            user: User object

        Returns:
            QuerySet of AuditLog objects
        """
        return self.filter(requested_by=user)

    def for_action_type(self, action_type: str):
        """Get all audit logs of a specific action type.

        Args:
            action_type: Action type (from ActionType choices)

        Returns:
            QuerySet of AuditLog objects
        """
        return self.filter(action_type=action_type)


class SyncedCharacterManager(models.Manager):
    """Manager for SyncedCharacter model."""

    def active(self):
        """Get all active synced characters (have been synced at least once).

        Returns:
            QuerySet of SyncedCharacter objects
        """
        return self.filter(last_sync_at__isnull=False)

    def stale(self):
        """Get characters that need syncing (stale or never synced).

        Returns:
            QuerySet of SyncedCharacter objects
        """
        import datetime as dt

        from django.utils.timezone import now

        from .app_settings import STANDINGS_SYNC_TIMEOUT

        deadline = now() - dt.timedelta(minutes=STANDINGS_SYNC_TIMEOUT)
        return self.filter(
            models.Q(last_sync_at__isnull=True) | models.Q(last_sync_at__lt=deadline)
        )

    def for_user(self, user: User):
        """Get all synced characters for a specific user.

        Args:
            user: User object

        Returns:
            QuerySet of SyncedCharacter objects
        """
        return self.filter(character_ownership__user=user)

    def with_errors(self):
        """Get all characters that have sync errors.

        Returns:
            QuerySet of SyncedCharacter objects
        """
        return self.exclude(last_error="")

    def without_label(self):
        """Get all characters that don't have the configured label.

        Returns:
            QuerySet of SyncedCharacter objects
        """
        return self.filter(has_label=False)
