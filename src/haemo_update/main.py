"""haemo-update main module"""
import argparse
from haemo_update import HaemoUpdate


def main():
    """
    haemo-update entry point
    :return:
    """
    parser = argparse.ArgumentParser(prog='haemo-update', description='HaemoUpdate package installer')
    parser.add_argument(
        '-u',
        '--update-package',
        required=True,
        type=str,
        help='Path to update package directory'
    )
    args = parser.parse_args()
    update = HaemoUpdate(args.update_package)
    update.perform_update()
