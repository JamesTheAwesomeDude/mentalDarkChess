import logging
import chess
import zmq
from os import urandom
from itertools import islice
#logging.basicConfig(stream=stdout, level=getattr(logging, environ.get('LOGLEVEL', 'INFO')))
import bencodepy
from zmq.utils.z85 import encode as z85encode, decode as z85decode

from ._crypto import h, gen_fake_pubkeys, make_real_keypair, publickey, pk_encrypt, pk_decrypt


CHESS_PORT = 64355


def prettyprint_bytes(b):
        return "'%s'" % z85encode(b).decode()


def probe_opponent(board):
	ctx = zmq.Context()
	socket = ctx.socket(zmq.PAIR)
	socket.connect('tcp://localhost:%u' % (CHESS_PORT + board.fullmove_number * 2 - 1 + (not board.turn)))
	seed = urandom(32) # TODO allow Bob to ensure randomness
	logging.info('CHOSE SEED     : %s', prettyprint_bytes(seed))
	hseed = h(seed)
	logging.info('SEED COMMITMENT: %s', prettyprint_bytes(hseed))
	socket.send_serialized(hseed, _serialize)
	fake_pkgen = gen_fake_pubkeys(seed)
	piece_map = dict()
	board.vision = chess.SquareSet()
	for max_vision in range(1, 8):
		board.vision = board.calc_vision(initial=int(board.vision), max_vision=max_vision)
		pkeys = list(islice(fake_pkgen, len(chess.SQUARES)))
		keys = []
		for square in board.vision:
			sk, pk = make_real_keypair()
			keys.append(sk)
			pkeys[square] = pk
		logging.debug('PEEK #%u: %s', max_vision, ','.join(chess.SQUARE_NAMES[square] for square in board.vision))
		socket.send_serialized(pkeys, _serialize)
		payload = socket.recv_serialized(_deserialize)
		for square, sk in zip(board.vision, keys):
			piece_data = pk_decrypt(sk, payload[square])
			piece = chess.Piece.from_symbol(piece_data.decode()) if piece_data != b'\x00' else None
			if square in piece_map:
				assert piece_map[square] == piece, "Opponent sent contradictory information"
			else:
				piece_map[square] = piece
			if piece:
				board.set_piece_at(square, piece, gently=True)
	logging.info('PEEKED AT: %s', ','.join(chess.SQUARE_NAMES[square] for square in board.vision))
	captured_square = yield piece_map
	yield socket.send_serialized(captured_square, _serialize)


def respond_to_probe(board):
	ctx = zmq.Context()
	socket = ctx.socket(zmq.PAIR)
	socket.bind('tcp://*:%u' % (CHESS_PORT + board.fullmove_number * 2 - 1 + (not board.turn)))
	hseed = socket.recv_serialized(_deserialize)
	logging.info('GOT SEED COMMITMENT: %s', prettyprint_bytes(hseed))
	queries = []
	for i in range(1, 8):
		pkeys = socket.recv_serialized(_deserialize)
		logging.debug('GOT QUERY #%u: %s', i, ''.join(prettyprint_bytes(pk) for pk in pkeys))
		queries.append(pkeys)
		payload = []
		for square, pk in zip(chess.SQUARES, pkeys):
			# note: you should forget opponent pieces BEFORE running this function
			piece = board.piece_at(square)
			piece_data = piece.symbol().encode() if piece else b'\x00'
			encrypted_piece_data = pk_encrypt(pk, piece_data)
			payload.append(encrypted_piece_data)
		socket.send_serialized(payload, _serialize)
	logging.info('H(QUERIES): %s', prettyprint_bytes(h(bytes().join(bytes().join(query) for query in queries))))
	yield queries
	captured_square = socket.recv_serialized(_deserialize)
	yield captured_square


def _serialize(m):
	return [bencodepy.encode(m)]

def _deserialize(b):
	return bencodepy.decode(bytes().join(b))

if __name__ == '__main__':
	import sys
	colorstring = environ.get('chesscolor', None)
	if colorstring is None:
		colorstring = {'W': 'white', 'B': 'black'}[input("Do you want to play as WHITE (w) or as BLACK (b)?\n> ")[0].upper()]
	color = chess.COLOR_NAMES.index(colorstring)
	board = DarkBoard(pov=color)
	if "lol" in environ:
		board.remove_piece_at(chess.D2)
		board.remove_piece_at(chess.E2)
	sys.exit(_main(board, color))
