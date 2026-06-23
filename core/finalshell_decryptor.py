"""FinalShell 连接配置中的密码解密逻辑。"""

import base64
import hashlib
import re
import struct
from typing import Optional

try:
    from Crypto.Cipher import DES
except ImportError:  # 让界面能够给出明确的依赖提示，而不是导入时直接退出。
    DES = None


class FinalShellDecryptError(ValueError):
    """FinalShell 密码无法解密时抛出的异常。"""


class _JavaRandom:
    """仅实现 FinalShell 密钥派生过程需要的 java.util.Random 行为。"""

    _MULTIPLIER = 0x5DEECE66D
    _ADDEND = 0xB
    _MASK = (1 << 48) - 1

    def __init__(self, seed: int):
        self._seed = (seed ^ self._MULTIPLIER) & self._MASK

    def _next(self, bits: int) -> int:
        self._seed = (self._seed * self._MULTIPLIER + self._ADDEND) & self._MASK
        return self._seed >> (48 - bits)

    def next_int(self, bound: int) -> int:
        """复现 java.util.Random.nextInt(bound)。"""
        if bound <= 0:
            raise ValueError("bound 必须为正数")

        if (bound & -bound) == bound:
            return (bound * self._next(31)) >> 31

        while True:
            bits = self._next(31)
            value = bits % bound
            # Java 此处用 int 判断；显式处理溢出以保持完全一致。
            if bits - value + (bound - 1) <= 0x7FFFFFFF:
                return value

    def next_long(self) -> int:
        """复现 java.util.Random.nextLong() 的有符号 long 结果。"""
        high = self._next(32)
        low = self._next(32)
        if high >= 1 << 31:
            high -= 1 << 32
        if low >= 1 << 31:
            low -= 1 << 32
        return (high << 32) + low


def _signed_byte(value: int) -> int:
    return value - 256 if value >= 128 else value


def _derive_des_key(header: bytes) -> bytes:
    """由密文前 8 字节派生 FinalShell 使用的 DES 密钥。"""
    if len(header) != 8:
        raise FinalShellDecryptError("密文头长度无效")

    divisor = _JavaRandom(_signed_byte(header[5])).next_int(127)
    if divisor == 0:
        raise FinalShellDecryptError("密文头无法生成有效密钥")

    random = _JavaRandom(3680984568597093857 // divisor)
    for _ in range(_signed_byte(header[0])):
        random.next_long()

    random_two = _JavaRandom(random.next_long())
    key_parts = (
        _signed_byte(header[4]),
        random_two.next_long(),
        _signed_byte(header[7]),
        _signed_byte(header[3]),
        random_two.next_long(),
        _signed_byte(header[1]),
        random.next_long(),
        _signed_byte(header[2]),
    )
    key_material = b"".join(
        struct.pack(">Q", value & ((1 << 64) - 1)) for value in key_parts
    )
    return hashlib.md5(key_material).digest()[:8]


def decrypt_password(encrypted_password: Optional[str]) -> str:
    """解密 FinalShell JSON 配置中的 ``password`` 字段。"""
    if encrypted_password is None or encrypted_password == "":
        return ""
    if not isinstance(encrypted_password, str):
        raise FinalShellDecryptError("password 不是字符串")
    if DES is None:
        raise FinalShellDecryptError("缺少 pycryptodome 依赖，请安装 requirements.txt 中的依赖")

    try:
        encrypted_data = base64.b64decode(encrypted_password.strip(), validate=True)
    except (ValueError, TypeError) as error:
        raise FinalShellDecryptError("password 不是有效的 Base64 密文") from error

    if len(encrypted_data) <= 8 or (len(encrypted_data) - 8) % DES.block_size != 0:
        raise FinalShellDecryptError("password 密文长度无效")

    key = _derive_des_key(encrypted_data[:8])
    try:
        plaintext = DES.new(key, DES.MODE_ECB).decrypt(encrypted_data[8:]).decode("utf-8")
    except (UnicodeDecodeError, ValueError) as error:
        raise FinalShellDecryptError("password 解密失败") from error

    # FinalShell 的明文块带有控制字符填充，移除方式与参考实现一致。
    return re.sub(r"[\x00-\x1F\x7F-\x9F]", "", plaintext)
