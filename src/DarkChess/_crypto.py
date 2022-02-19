import hashlib
from os import urandom
from warnings import warn as _warn

from cryptography.hazmat.primitives.asymmetric import x25519, ed25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import serialization as _crypto_serialization
from zmq.utils.z85 import encode as z85encode, decode as z85decode

from ._rng import RijndaelRng


def prettyprint_bytes(b):
        return "'%s'" % z85encode(b).decode()

def h(m):
	return hashlib.sha256(m).digest()


def gen_fake_pubkeys(seed, m=32):
	aes_key = h(seed)
	r = RijndaelRng(aes_key)
	while True:
		pk = urandom(m)
		yield pk

def make_real_keypair(m=32):
	sk = urandom(m)
	pk = publickey(sk)
	return sk, pk

def _publickey(_sk):
	_pk = _sk.public_key()
	return _pk.public_bytes(encoding=_crypto_serialization.Encoding.Raw, format=_crypto_serialization.PublicFormat.Raw)

def publickey(sk):
	_sk = x25519.X25519PrivateKey.from_private_bytes(sk)
	return _publickey(_sk)

def pk_encrypt(pk, data, aad=None):
	_sk = x25519.X25519PrivateKey.generate()
	ephemeral_pk = _publickey(_sk)
	_pk = x25519.X25519PublicKey.from_public_bytes(pk)
	key = _sk.exchange(_pk)
	nonce = urandom(12)
	cipher = ChaCha20Poly1305(key)
	ciphertext = cipher.encrypt(nonce, data, aad)
	return ephemeral_pk + ciphertext + nonce

def pk_decrypt(sk, ciphertext, aad=None):
	ephemeral_pk, ciphertext, nonce = ciphertext[:32], ciphertext[32:-12], ciphertext[-12:]
	_sk = x25519.X25519PrivateKey.from_private_bytes(sk)
	_pk = x25519.X25519PublicKey.from_public_bytes(ephemeral_pk)
	key = _sk.exchange(_pk)
	cipher = ChaCha20Poly1305(key)
	return cipher.decrypt(nonce, ciphertext, aad)

def pk_sign(sk, data):
	_sk = ed25519.Ed25519PrivateKey.from_private_bytes(sk)
	return _sk.sign(data)

def pk_verify(pk, data, signature):
	_pk = ed25519.Ed25519PublicKey.from_public_bytes(pk)
	return _pk.verify(signature, data)
