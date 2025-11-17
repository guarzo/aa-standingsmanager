"""Model test factories."""

from typing import Generic, TypeVar

import factory
import factory.fuzzy

from eveuniverse.models import EveEntity

from app_utils.testdata_factories import (
    EveAllianceInfoFactory,
    EveCharacterFactory,
    EveCorporationInfoFactory,
    UserMainFactory,
)

from standingsmanager.core.esi_contacts import EsiContact, EsiContactLabel
from standingsmanager.models import SyncedCharacter

T = TypeVar("T")


class BaseMetaFactory(Generic[T], factory.base.FactoryMetaClass):
    def __call__(cls, *args, **kwargs) -> T:
        return super().__call__(*args, **kwargs)


class EveEntityFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[EveEntity]
):
    class Meta:
        model = EveEntity
        django_get_or_create = ("id", "name")

    category = EveEntity.CATEGORY_CHARACTER

    @factory.lazy_attribute
    def id(self):
        if self.category == EveEntity.CATEGORY_CHARACTER:
            obj = EveCharacterFactory()
            return obj.character_id
        if self.category == EveEntity.CATEGORY_CORPORATION:
            obj = EveCorporationInfoFactory()
            return obj.corporation_id
        if self.category == EveEntity.CATEGORY_ALLIANCE:
            obj = EveAllianceInfoFactory()
            return obj.alliance_id
        raise NotImplementedError(f"Unknown category: {self.category}")


class EveEntityCharacterFactory(EveEntityFactory):
    name = factory.Faker("name")
    category = EveEntity.CATEGORY_CHARACTER


class EveEntityCorporationFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_CORPORATION


class EveEntityAllianceFactory(EveEntityFactory):
    name = factory.Faker("company")
    category = EveEntity.CATEGORY_ALLIANCE


class EveEntityFactionFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[EveEntity]
):
    class Meta:
        model = EveEntity
        django_get_or_create = ("id", "name")

    id = factory.Sequence(lambda n: 500001 + n)
    name = factory.Faker("color_name")
    category = EveEntity.CATEGORY_FACTION


class UserMainManagerFactory(UserMainFactory):
    main_character__scopes = ["esi-alliances.read_contacts.v1"]
    permissions__ = ["standingsmanager.add_syncmanager"]


class UserMainSyncerFactory(UserMainFactory):
    main_character__scopes = [
        "esi-characters.read_contacts.v1",
        "esi-characters.write_contacts.v1",
    ]
    permissions__ = ["standingsmanager.add_syncedcharacter"]


class SyncedCharacterFactory(
    factory.django.DjangoModelFactory, metaclass=BaseMetaFactory[SyncedCharacter]
):
    class Meta:
        model = SyncedCharacter

    class Params:
        user = factory.SubFactory(UserMainSyncerFactory)

    @factory.lazy_attribute
    def character_ownership(self):
        return self.user.profile.main_character.character_ownership  # type: ignore


class EsiContactDictFactory(factory.base.DictFactory, metaclass=BaseMetaFactory[dict]):
    contact_id = factory.fuzzy.FuzzyInteger(90_000, 99_999)
    contact_type = factory.fuzzy.FuzzyChoice(["character", "corporation", "alliance"])
    standing = factory.fuzzy.FuzzyFloat(-10.0, 10.0)


class EsiLabelDictFactory(factory.base.DictFactory, metaclass=BaseMetaFactory[dict]):
    label_id = factory.fuzzy.FuzzyInteger(1, 9_999)
    label_name = factory.Faker("word")


class EsiContactFactory(factory.base.Factory, metaclass=BaseMetaFactory[EsiContact]):
    class Meta:
        model = EsiContact

    contact_id = factory.fuzzy.FuzzyInteger(90_000, 99_999)
    contact_type = factory.fuzzy.FuzzyChoice(list(EsiContact.ContactType))
    standing = factory.fuzzy.FuzzyFloat(-10.0, 10.0)


class EsiContactLabelFactory(
    factory.base.Factory, metaclass=BaseMetaFactory[EsiContactLabel]
):
    class Meta:
        model = EsiContactLabel

    id = factory.fuzzy.FuzzyInteger(1, 9_999)
    name = factory.Faker("word")
