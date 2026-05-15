"""
HaemoUpdate main class module
"""
import os
import gzip
import re
import subprocess
import tempfile
import tarfile
import shutil
import logging

import libarchive

class HaemoUpdateException(Exception):
    """
    Exceptions handled by HaemoUpdate
    """


def call_system(command, pretty=None) -> int:
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
    return subprocess.run(_command).returncode


class HaemoUpdate:
    """
    Main class
    """

    key_file = '/dev/shm/rtfskey'
    boot_target_part = '/dev/disk/by-partlabel/boot'
    root_target_path = '/flash/newroot'
    boot_target_path = '/flash/newboot'
    boot_part_name = 'boot'
    archive_key_path = 'usr/share/misc/rtfskey-unique'

    def __init__(self, update_package, old_part=None, new_part=None):
        if old_part is None or new_part is None:
            self._get_part_sets()
        else:
            self.old_part = old_part
            self.new_part = new_part
        self.update_package = update_package
        self._encryption_enabled = self.is_encrypted(self.root_target_part)

    @property
    def mapped_root_target_part(self) -> str:
        if self._encryption_enabled:
            return f'/dev/mapper/root_{self.new_part}'
        return self.root_target_part

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

    @property
    def old_root_name(self) -> str:
        return f'root_{self.old_part}'

    @property
    def new_root_name(self) -> str:
        return f'root_{self.new_part}'

    @staticmethod
    def extract_key_content(archive_path: str) -> bytes:
        with tempfile.TemporaryDirectory() as tmp_dir:
            with gzip.open(archive_path, 'rb') as f_in:
                with open(os.path.join(tmp_dir, 'initramfs.cpio'), 'wb') as f_out:
                    shutil.copyfileobj(f_in, f_out)
            with libarchive.file_reader(os.path.join(tmp_dir, 'initramfs.cpio')) as archive:
                for entry in archive:
                    if entry.pathname == 'usr/share/misc/rtfskey-unique':
                        with open(os.path.join(tmp_dir, 'rtfskey-unique'), 'wb') as f_out:
                            return next(entry.get_blocks())
        raise HaemoUpdateException(f'Could not extract encryption key from archive {archive_path}')

    @classmethod
    def mount_boot_partition(cls) -> None:
        cls.mount_single_partition(cls.boot_target_part, cls.boot_target_path)

    @classmethod
    def get_encryption_key(cls) -> None:
        if os.path.exists(cls.key_file):
            return
        cls.mount_boot_partition()
        key_content = cls.extract_key_content(os.path.join(cls.boot_target_path, 'initramfs.img.a'))
        with open(cls.key_file, 'wb') as file:
            file.write(key_content)

    def user_message(self, message: str) -> None:
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

    @staticmethod
    def is_encrypted(device: str) -> bool:
        return call_system(f'cryptsetup isLuks {device}') == 0

    @classmethod
    def decrypt_partition(cls, device: str, name: str) -> bool:
        cls.get_encryption_key()
        return call_system(f'cryptsetup --key-file={cls.key_file} luksOpen {device} {name}') == 0

    @staticmethod
    def is_mounted(device: str) -> bool:
        device_real = os.path.realpath(device)
        with open('/proc/mounts', 'r', encoding='utf-8') as file:
            mounts = file.read()
        return re.search(device, mounts) is not None or re.search(device_real, mounts) is not None

    @classmethod
    def mount_single_partition(cls, device: str, path: str) -> None:
        logging.info(f'Mounting {device} at path {path}')
        if cls.is_mounted(device):
            logging.warning(f'Device {device} is already mounted. Will not re-mount')
            return
        call_system(f'mount {device} {path}')

    # def mount_target_root_partition(self) -> None:


    def mount_partitions(self) -> None:
        """
        Mount the partitions

        :return:
        """
        os.makedirs(self.root_target_path, exist_ok=True)
        os.makedirs(self.boot_target_path, exist_ok=True)
        self.mount_target_root_partition()
        self.mount_single_partition(self.boot_target_part, self.boot_target_path)

    def mount_target_root_partition(self) -> None:
        # self.mount_single_partition(self.mapped_root_target_part, self.root_target_path, self.new_root_name)
        if self._encryption_enabled:
            self.decrypt_partition(self.root_target_part, self.new_root_name)
        self.mount_single_partition(self.mapped_root_target_part, self.root_target_path)

    @staticmethod
    def unmount_fs(path: str) -> None:
        call_system(f'umount {path}')


    def create_fs(self) -> None:
        """
        Create a file system on partitions

        :return:
        """
        if self.is_mounted(self.mapped_root_target_part):
            self.unmount_fs(self.root_target_path)
        if self._encryption_enabled:
            self.decrypt_partition(self.root_target_part, self.new_root_name)
        call_system(f'wipefs --all {self.mapped_root_target_part}')
        call_system(f'mkfs.ext4 {self.mapped_root_target_part}')

    @classmethod
    def unmount_partitions(cls) -> None:
        """
        Unmount partitions

        :return:
        """
        cls.unmount_fs(cls.root_target_path)
        cls.unmount_fs(cls.boot_target_path)

    def unmap_partitions(self) -> None:
        call_system(f'cryptsetup luksClose {self.new_root_name}')

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
        # Insert encryption key
        if self._encryption_enabled:
            with libarchive.file_reader(f'{self.update_package}/initramfs.img', format_name='cpio', filter_name='gzip') as archive_in:
                with libarchive.file_writer(f'{self.boot_target_path}/initramfs.img.{self.new_part}', format_name='cpio', filter_name='gzip') as archive_out:
                    archive_out.add_entries(
                        entry for entry in archive_in if entry.pathname != self.archive_key_path)
                    # with open(self.key_file, 'rb') as key_file:
                    #     archive_out.add_file_from_memory(self.archive_key_path, os.path.getsize(self.key_file), key_file.read(), permission=0o400)
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
        self.unmap_partitions()
