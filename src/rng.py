from random import Random
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms as _cipher_algorithms, modes as _cipher_modes
try:
	from resource import getpagesize as _getpagesize
except ImportError:
	def _getpagesize():
		return 4096
from functools import reduce as _reduce
from itertools import islice as _islice, repeat as _repeat
from types import SimpleNamespace as _SimpleNamespace
from os import urandom


class StreamBasedRandom(Random):
	def __init__(self, stream, blocksize=_getpagesize()):
		self._randbitgen = _ibytestobits(map(stream.read, _repeat(blocksize)))
	def getrandbits(self, k):
		return _concatbits(_islice(self._randbitgen, k))
	# Fix the following functions to prevent implementation-dependency
	def randbytes(self, n):
		return self.getrandbits(n * 8).to_bytes(n, 'big')
	def _randbelow(self, n):
		"""Replacement for CPython's Random._randbelow that wastes very few bits"""
		if n <= 1:
			return 0
		getrandbits = self.getrandbits
		k = (n - 1).bit_length()
		a = getrandbits(k)
		b = 2 ** k
		if n == b:
			return a
		while (n * a // b) != (n * (a + 1) // b):
			a = a * 2 | getrandbits(1)
			b *= 2
		return n * a // b
	def shuffle(self, x):
		"""Modern Fisher-Yates shuffle"""
		randbelow = self._randbelow
		for i in reversed(range(1, len(x))):
			j = randbelow(i + 1)
			x[i], x[j] = x[j], x[i]


class RijndaelRng(StreamBasedRandom):
	def __init__(self, seed):
		assert len(seed) == 256//8, "AES-256-CTR requires a 256 bit (32 byte) key"
		key = seed
		blocksize = _cipher_algorithms.AES.block_size//8
		nonce = bytes(blocksize) # null nonce for repeatability
		cipher = Cipher(_cipher_algorithms.AES(key), _cipher_modes.CTR(nonce)).encryptor()
		stream = _SimpleNamespace(read=lambda n: cipher.update(b'\x00' * n))
		super().__init__(stream=stream, blocksize=blocksize)


def _ibytestobits(ibytes):
	"""Turns an iterator of bytes into an iterator of its component bits, big-endian"""
	yield from ((i >> k) & 0b1 for b in ibytes for i in b for k in reversed(range(8)))

def _concatbits(bits):
	"""Takes a finite iterator of bits and returns their big-endian concatenation as an integer"""
	return _reduce((lambda acc, cur: ((acc << 1) | cur)), bits, 0)
