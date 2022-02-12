import chess
import zmq
import bencodepy
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives import serialization as _crypto_serialization
import logging
import json
import hashlib
import ed25519
from sys import stdout
from os import urandom
from base64 import b64encode, b64decode
from rng import RijndaelRng
logging.basicConfig(level=logging.INFO, stream=stdout)

chess.NO_PIECE = -len(chess.PIECE_NAMES)
chess.NO_SQUARE = len(chess.SQUARES)

CHESS_PORT = 64355

def _main(board, color):
	winner = None
	if color == chess.BLACK:
		winner = their_turn(board)
	while winner is None:
		if board.turn == color:
			winner = my_turn(board)
		else:
			winner = their_turn(board)
	if winner == color:
		return 0
	else:
		return 1


def my_turn(board):
	forget_player(board, not board.turn)
	alice = probe_opponent(board)
	revealed = next(alice)
	logging.info('REVEALED: %s', json.dumps(dict(((chess.SQUARE_NAMES[k], v.symbol() if v else None) for k, v in revealed.items()))))
	print(board.unicode())
	move = chess.Move.from_uci(input('MOVE IN UCI FORMAT (e.g. e2e4)\n> '))
	dest = move.to_square
	target_piece = board.piece_at(dest)
	if target_piece is None:
		alice.send(chess.NO_SQUARE)
	else:
		if target_piece.color == board.turn:
			raise ValueError("Can't capture your own %s piece %s@%s")
		alice.send(dest)
		logging.info("CAPTURED: %s@%s", target_piece.symbol(), chess.SQUARE_NAMES[dest])
	board.push(move)


def their_turn(board):
	forget_player(board, board.turn)
	bob = respond_to_probe(board)
	queries = next(bob)
	captured_square = next(bob)
	if captured_square == chess.NO_SQUARE:
		captured_piece = None
		logging.info("NO CAPTURE BY OPPONENT THIS TURN")
		board.push(chess.Move.null())
	else:
		captured_piece = board.piece_at(captured_square)
		board.push(chess.Move(captured_square, captured_square, drop=chess.NO_PIECE))
		logging.info("OPPONENT CAPTURED: %s@%s", captured_piece.symbol(), chess.SQUARE_NAMES[captured_square])
	if captured_piece and captured_piece.piece_type == chess.KING:
		return not board.turn


def check_vision(board, square, max_vision=99, self_vision=False):
	piece = board.piece_at(square)
	if piece and piece.color == board.turn:
		return self_vision
	for attacker_square in board.attackers(board.turn, square):
		attacker = board.piece_at(attacker_square)
		if attacker.piece_type != chess.KNIGHT or max_vision < 1:
			if chess.square_distance(attacker_square, square) <= max_vision:
				return True
		else:
			return True
	return False


def calc_vision(board, max_vision=99, self_vision=False):
	vision = chess.SquareSet()
	for square in chess.SQUARES:
		if square in vision:
			continue
		if check_vision(board, square, max_vision, self_vision):
			vision.add(square)
	return vision



def probe_opponent(board):
	_Board = chess.BaseBoard if type(board) == chess.Board else type(board)
	ctx = zmq.Context()
	socket = ctx.socket(zmq.PAIR)
	socket.connect('tcp://localhost:%u' % (CHESS_PORT + board.fullmove_number * 2 - 1 + (not board.turn)))
	piece_map = dict()
	for max_vision in range(1, 8):
		seed = urandom(32) # TODO allow Bob to ensure randomness
		logging.info('CHOSE SEED: %s', b64encode(seed, b'-_').decode())
		hseed = h(seed)
		logging.info('SEED COMMITMENT: %s', b64encode(hseed, b'-_').decode())
		vision = calc_vision(board, max_vision)
		pkeys = gen_fake_pubkeys(seed)
		keys = []
		for square in vision:
			sk, pk = gen_real_keypair()
			keys.append(sk)
			pkeys[square] = pk
		logging.info('CLAIMING VISION %u: %s', max_vision, json.dumps(list(vision)))
		socket.send_serialized([hseed, pkeys], _serialize)
		payload = socket.recv_serialized(_deserialize)
		for square, sk in zip(vision, keys):
			piece_data = pk_decrypt(sk, payload[square])
			piece = chess.Piece.from_symbol(piece_data.decode()) if piece_data != b'\x00' else None
			if square in piece_map:
				assert piece_map[square] == piece, "Opponent sent contradictory information"
			else:
				piece_map[square] = piece
			if piece:
				_Board.set_piece_at(board, square, piece)
	captured_square = yield piece_map
	yield socket.send_serialized(captured_square, _serialize)


def respond_to_probe(board):
	ctx = zmq.Context()
	socket = ctx.socket(zmq.PAIR)
	socket.bind('tcp://*:%u' % (CHESS_PORT + board.fullmove_number * 2 - 1 + (not board.turn)))
	queries = []
	for _ in range(1, 8):
		hseed, pkeys = socket.recv_serialized(_deserialize)
		logging.info('GOT SEED COMMITMENT: %s', b64encode(hseed, b'-_').decode())
		logging.info('GOT QUERY: %s', json.dumps(list(b64encode(pk, b'-_').decode() for pk in pkeys)))
		queries.append((hseed, pkeys))
		payload = []
		for square, pk in zip(chess.SQUARES, pkeys):
			# note: you should forget opponent pieces BEFORE running this function
			piece = board.piece_at(square)
			piece_data = piece.symbol().encode() if piece else b'\x00'
			encrypted_piece_data = pk_encrypt(pk, piece_data)
			payload.append(encrypted_piece_data)
		socket.send_serialized(payload, _serialize)
	yield queries
	captured_square = socket.recv_serialized(_deserialize)
	yield captured_square


def _serialize(m):
	return [bencodepy.encode(m)]

def _deserialize(b):
	return bencodepy.decode(bytes().join(b))


def h(m):
	return hashlib.sha256(m).digest()

def gen_fake_pubkeys(seed, m=32, n=64):
	key = h(seed)
	r = RijndaelRng(seed)
	payload = []
	while len(payload) < n:
		pk = urandom(m)
		try:
			ed25519.decodepoint(pk)
		except ValueError:
			pass
		else:
			payload.append(pk)
	return payload

def gen_real_keypair(m=32):
	sk = urandom(m)
	pk = publickey(sk)
	return sk, pk

def _publickey(sk):
	return sk.public_key().public_bytes(encoding=_crypto_serialization.Encoding.Raw, format=_crypto_serialization.PublicFormat.Raw)

def publickey(sk):
	return _publickey(x25519.X25519PrivateKey.from_private_bytes(sk))

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


def forget_player(board, color):
	_Board = chess.BaseBoard if type(board) == chess.Board else type(board)
	for square in chess.SQUARES:
		piece = board.piece_at(square)
		if piece and piece.color == color:
			_Board.remove_piece_at(board, square)


if __name__ == '__main__':
	import os, sys
	board = chess.Board()
	if "lol" in os.environ:
		board.remove_piece_at(chess.D2)
		board.remove_piece_at(chess.E2)
	color = {'white': chess.WHITE, 'black': chess.BLACK}[os.environ.get('chesscolor', 'white')]
	_main(board, color)
