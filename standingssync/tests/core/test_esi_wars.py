from unittest.mock import patch

from app_utils.esi_testing import BravadoOperationStub
from app_utils.testing import NoSocketsTestCase

from standingssync.core import esi_wars

MODULE_PATH = "standingssync.core.esi_wars"


class TestEsiWars(NoSocketsTestCase):
    @patch(MODULE_PATH + ".STANDINGSSYNC_MINIMUM_UNFINISHED_WAR_ID", 4)
    @patch(MODULE_PATH + ".STANDINGSSYNC_SPECIAL_WAR_IDS", [1, 2])
    @patch(MODULE_PATH + ".esi")
    def test_should_fetch_war_ids_with_paging(self, mock_esi):
        def esi_get_wars(max_war_id=None):
            if max_war_id:
                war_ids = [war_id for war_id in esi_war_ids if war_id < max_war_id]
            else:
                war_ids = esi_war_ids
            return BravadoOperationStub(sorted(war_ids, reverse=True)[:page_size])

        # given
        esi_war_ids = [1, 2, 3, 4, 5, 6, 7, 8]
        page_size = 3
        mock_esi.client.Wars.get_wars.side_effect = esi_get_wars
        # when
        with patch(MODULE_PATH + ".FETCH_WARS_MAX_ITEMS", 3):
            result = esi_wars.fetch_war_ids()
        # then
        self.assertSetEqual(result, {1, 2, 4, 5, 6, 7, 8})
