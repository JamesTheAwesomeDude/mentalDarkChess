import chess
import zmq
import bencodepy
from cryptography.hazmat.primitives.asymmetric import x25519
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
	revealed = probe_opponent(board)
	logging.info("REVEALED: %s", revealed)
	print(board.unicode())
	move = chess.Move.from_uci(input('MOVE IN UCI FORMAT (e.g. e2e4)\n> '))
	dest = move.to_square
	target_piece = board.piece_at(dest)
	if target_piece is None:
		notify_capture(None)
	else:
		if target_piece.color != board.turn:
			raise ValueError("Can't capture your own piece")
		notify_capture(dest)
		logging.info("CAPTURED: %s@%s", target_piece.symbol(), chess.SQUARE_NAMES[dest])
	board.push(move)
	forget_player(board, board.turn)


def their_turn(board):
	forget_player(board, board.turn)
	queries = respond_to_probe(board)
	captured_square = rcv_notify_capture()
	if captured_square is None:
		captured_piece = None
		console.info("NO CAPTURE BY OPPONENT THIS TURN")
	else:
		captured_piece = board.piece_at(captured_square)
		board.push(chess.Move(captured_square, captured_square, drop=chess.NO_PIECE))
		console.info("OPPONENT CAPTURED: %s@%s", captured_piece.symbol(), chess.SQUARE_NAMES[captured_square])
	if captured_piece.piece_type == chess.KING:
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
	socket.connect('tcp://localhost:%u' % (CHESS_PORT + board.halfmove_clock))
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
		piece_map = dict()
		for square, sk in zip(vision, keys):
			piece_data = pk_decrypt(sk, payload[square])
			piece = chess.Piece.fromsymbol(piece_data.decode()) if piece_data != b'\x00' else None
			piece_map[square] = piece
			if piece:
				_Board.set_piece_at(square, piece)
		logging.info('GOT VISION: %s', json.dumps(dict(((chess.SQUARE_NAMES[k], v.symbol() if v else None) for k, v in piece_map.items()))))


def respond_to_probe(board):
	ctx = zmq.Context()
	socket = ctx.socket(zmq.PAIR)
	socket.bind('tcp://*:%u' % (CHESS_PORT + board.halfmove_clock))
	for _ in range(1, 8):
		hseed, pkeys = socket.recv_serialized(_deserialize)
		logging.info('GOT SEED COMMITMENT: %s', b64encode(hseed, b'-_').decode())
		logging.info('GOT QUERY: %s', json.dumps(list(b64encode(pk, b'-_').decode() for pk in pkeys)))
		payload = []
		for square, pk in zip(chess.SQUARES, pkeys):
			# note: you should forget opponent pieces BEFORE running this function
			piece = board.piece_at(square)
			piece_data = piece.symbol().encode() if piece else b'\x00'
			encrypted_piece_data = pk_encrypt(pk, piece_data)
			payload.append(encrypted_piece_data)
		socket.send_serialized(payload, _serialize)


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

def publickey(sk):
	return x25519.X25519PrivateKey.from_private_bytes(sk).public_key().public_bytes(encoding=_crypto_serialization.Encoding.Raw, format=_crypto_serialization.PublicFormat.Raw)


def forget_player(board, color):
	_Board = chess.BaseBoard if type(board) == chess.Board else type(board)
	for square in chess.SQUARES:
		piece = board.piece_at(square)
		if piece and piece.color == color:
			_Board.remove_piece_at(board, square)


if __name__ == '__main__':
	import os, sys
	board = chess.Board()
	color = {'white': chess.WHITE, 'black': chess.BLACK}[os.environ.get('chesscolor', 'white')]
	_main(board, color)
