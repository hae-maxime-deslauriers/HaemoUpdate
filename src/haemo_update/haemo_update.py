"""
HaemoUpdate main class module
"""
import os
import subprocess
import tarfile
import shutil
import logging


class HaemoUpdateException(Exception):
    """
    Exceptions handled by HaemoUpdate
    """


def call_system(command, pretty=None) -> None:
    """
    Call a system command

    :param command: Command
    :param pretty: Pretty string that should not be split by spaces
    :return:
    """
    _command = command.split(' ')
    if pretty:
        _command.append(pretty)

    logging.info('Calling system with command: %s', _command)
    subprocess.call(_command)


class HaemoUpdate:
    """
    Main class
    """

    def __init__(self, update_package, old_part=None, new_part=None):
        self.root_target_path = '/flash/newroot'
        self.boot_target_path = '/flash/newboot'
        self.old_part = old_part
        self.new_part = new_part
        self.boot_target_part = '/dev/disk/by-partlabel/boot'
        self.update_package = update_package

    def _get_part_sets(self) -> None:
        with open('/proc/cmdline', 'r', encoding='utf-8') as cmdline_file:
            cmdline = cmdline_file.read()

        if 'root=PARTLABEL=root_a ' in cmdline:
            self.old_part = 'a'
            self.new_part = 'b'
        else:
            if 'root=PARTLABEL=root_b ' in cmdline:
                self.old_part = 'b'
                self.new_part = 'a'
            else:
                raise HaemoUpdateException('Could not determine the original and new partition sets')

        logging.info('Determined we are updating from partition set "%s" to set "%s"', self.old_part, self.new_part)

    def user_message(self, message) -> None:
        """
        Display a message to the console

        :param message: Message to display
        :return:
        """
        call_system(
            f'{self.update_package}/haesplash '
            f'{self.update_package}/Lat2-Terminus16.psfu '
            f'{self.update_package}/splash.bmp '
            f'0',
            f'Software Update: {message}')

    @property
    def root_target_part(self) -> str:
        """
        Path to the target root file system

        :return:
        """
        return f'/dev/disk/by-partlabel/root_{self.new_part}'

    def mount_partitions(self) -> None:
        """
        Mount the partitions

        :return:
        """
        os.makedirs(self.root_target_path, exist_ok=True)
        os.makedirs(self.boot_target_path, exist_ok=True)
        call_system(f'mount {self.root_target_part} {self.root_target_path}')
        call_system(f'mount {self.boot_target_part} {self.boot_target_path}')

    def create_fs(self) -> None:
        """
        Create a file system on partitions

        :return:
        """
        call_system(f'wipefs --all {self.root_target_part}')
        call_system(f'mkfs.ext4 {self.root_target_part}')

    def unmount_partitions(self) -> None:
        """
        Unmount partitions

        :return:
        """
        call_system(f'umount {self.root_target_part}')
        call_system(f'umount {self.boot_target_part}')

    def extract_file_system(self) -> None:
        """
        Extract the new root file system

        :return:
        """
        logging.info('Extracting the new root file system')
        with tarfile.open(f'{self.update_package}/rootfs.tar.bz2', 'r:bz2') as tar:
            tar.extractall(path=self.root_target_path, filter='fully_trusted')

    def modify_grub_config(self) -> None:
        """
        Modify the grub configuration file to point to the new partition set

        :return:
        """
        shutil.copyfile(f'{self.boot_target_path}/grub/grub.cfg', f'{self.boot_target_path}/grub/grub.cfg.old')
        with open(f'{self.boot_target_path}/grub/grub.cfg', 'r', encoding='utf-8') as grub_cfg_file:
            grub_config = grub_cfg_file.read()

        grub_config = (grub_config.replace(f'bzImage.{self.old_part}', f'bzImage.{self.new_part}')
                       .replace(f'root_{self.old_part}', f'root_{self.new_part}')
                       .replace(f'initramfs.img.{self.old_part}', f'initramfs.img.{self.new_part}')
                       .replace(f'- {self.old_part.upper()}', f'- {self.new_part.upper()}'))
        with open(f'{self.boot_target_path}/grub/grub.cfg', 'w', encoding='utf-8') as grub_cfg_file:
            grub_cfg_file.write(grub_config)

    def fix_boot_partition(self) -> None:
        """
        Make needed modifications to the boot partition

        :return:
        """
        shutil.copyfile(f'{self.update_package}/bzImage', f'{self.boot_target_path}/bzImage.{self.new_part}')
        shutil.copyfile(
            f'{self.update_package}/initramfs.img',
            f'{self.boot_target_path}/initramfs.img.{self.new_part}'
        )
        self.modify_grub_config()

    @staticmethod
    def prepare_console() -> None:
        """
        Performs actions on the console in preparation for the update process

        :return:
        """
        call_system('systemctl stop autostartx')
        call_system('setterm --cursor off')
        with open('/sys/class/graphics/fbcon/cursor_blink', 'w', encoding='utf-8') as cursor_blink:
            cursor_blink.write('0')

    def verify_update_package(self) -> None:
        """
        TODO: Implement
        """
        return None

    def verify_partitions(self) -> None:
        """
        TODO: Implement
        """
        return None

    def complete_installation(self) -> None:
        """
        TODO: Implement
        """
        return None

    def perform_update(self) -> None:
        """
        Main function that performs the update

        :return:
        """
        try:
            if self.old_part is not None or self.new_part is None:
                self._get_part_sets()

            self.prepare_console()
            self.user_message('Verifying package...')
            self.verify_update_package()
            self.verify_partitions()
            self.user_message('Installing...')
            self.create_fs()
            self.mount_partitions()
            self.extract_file_system()
            self.user_message('Verifying installation...')
            self.fix_boot_partition()
        except HaemoUpdateException as error:
            logging.error(str(error))

        self.unmount_partitions()
        self.user_message('Completing...')
        self.complete_installation()
        self.user_message('Restarting...')
        self.unmount_partitions()
