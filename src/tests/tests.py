"""
Main test module
"""
from unittest import mock
from src.haemo_update import HaemoUpdate


@mock.patch('src.haemo_update.haemo_update.call_system')
def test_user_message(_mock_call_system):
    """
    Test the user_message function
    """
    haemo_update = HaemoUpdate('update-package')
    haemo_update.user_message('user-message')
