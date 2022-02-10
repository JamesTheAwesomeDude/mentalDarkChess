from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.hashes import Hash, SHA256
from rng import RijndaelRng
from os import urandom

def _H(m):
	h = Hash(SHA256())
	h.update(m)
	return h.finalize()


def commit_seed_alice(randval=None):
	if randval is None:
		randval = urandom(15)
	a = randval
	b = yield _H(a)
	s = a + b
	yield s

def commit_seed_bob(randval=None):
	if randval is None:
		randval = urandom(15)
	b = randval
	h_of_a = yield
	s = yield b
	a = s[:-len(b)]
	if _H(a) != h_of_a:
		raise ValueError("Cheated value from alice", {'a': a, 'b': b, 'h_of_a': h_of_a, 's': s})
	elif not s.endswith(b):
		raise ValueError("Unrecognized seed")
	else:
		yield True

if __name__ == '__main__':
	import time
	A = commit_seed_alice()
	B = commit_seed_bob(); next(B)
	print("ALICE PUBLISHES H(a):", (h_a:=next(A)).hex())
	print("BOB PUBLISHES b:", (b:=B.send(h_a)).hex())
	s = A.send(b)
	time.sleep(1)
	print("LATER, ALICE PUBLISHES s:", s.hex())
	print("BOB VERIFIES s:", B.send(s))

