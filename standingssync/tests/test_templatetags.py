from django.template import Context, Template
from django.test import TestCase

from .factories import EveEntityAllianceFactory


class TestTemplateTags(TestCase):
    def test_should_render_war_participant(self):
        # given
        template = Template(
            """
            {% load standingssync %}
            {% war_participant obj %}
            """
        )
        obj = EveEntityAllianceFactory()
        context = Context({"obj": obj})
        # when
        result = template.render(context)
        # then
        self.assertIn(str(obj.id), result)

    def test_should_display_no_data_for_empty_obj(self):
        # given
        template = Template(
            """
            {% load standingssync %}
            {% war_participant obj %}
            """
        )
        obj = EveEntityAllianceFactory(name="")
        context = Context({"obj": obj})
        # when
        result = template.render(context)
        # then
        self.assertIn("[NO DATA]", result)

    def test_should_display_no_data_for_invalid_obj(self):
        # given
        template = Template(
            """
            {% load standingssync %}
            {% war_participant obj %}
            """
        )
        context = Context({"obj": "abc"})
        # when
        result = template.render(context)
        # then
        self.assertIn("[NO DATA]", result)
