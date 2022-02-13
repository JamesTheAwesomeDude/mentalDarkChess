from sys import stdout
from os import urandom, environ
import json
from warnings import warn
import logging
from itertools import islice
from zmq.utils.z85 import encode as z85encode, decode as z85decode
logging.basicConfig(level=logging.INFO, stream=stdout)

import chess
import zmq
import bencodepy

from choss import monkey_patch as _monkey_patch
_monkey_patch(chess)
from criptogrvfy import h, gen_fake_pubkeys, make_real_keypair, publickey, pk_encrypt, pk_decrypt

CHESS_PORT = 64355


_UNICODE_TERMINAL = ('UTF-' in environ.get('LANG', 'C'))


def show_board(board, *args, **kwargs):
	if _UNICODE_TERMINAL:
		print(board.unicode(*args, **kwargs))
	else:
		if(args or kwargs):
			warn("Arguments to show_board not supported in this environment (LANG=%s)" % environ.get('LANG', ''))
		print(str(board))


def prettyprint_bytes(b):
	return z85encode(b).decode()


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
	board.forget_player(not board.turn)
	alice = probe_opponent(board)
	revealed = next(alice)
	logging.info('REVEALED: %s', json.dumps(dict(((chess.SQUARE_NAMES[k], v.symbol() if v else None) for k, v in revealed.items()))))
	board.vision = board.calc_vision()
	show_board(board)
	move = chess.Move.from_uci(input('MOVE IN UCI FORMAT (e.g. e2e4,f7f5)\n> '))
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
	# Don't run board.update_vision here as it won't yield correct results
	show_board(board)


def their_turn(board):
	board.forget_player(board.turn)
	bob = respond_to_probe(board)
	queries = next(bob)
	captured_square = next(bob)
	if captured_square == chess.NO_SQUARE:
		captured_piece = None
		logging.info("NO CAPTURE BY OPPONENT THIS TURN")
		board.push(chess.Move.null())
	else:
		captured_piece = board.piece_at(captured_square)
		board.push(chess.Move.remove(captured_square))
		logging.info("OPPONENT CAPTURED: %s@%s", captured_piece.symbol(), chess.SQUARE_NAMES[captured_square])
	#board.update_vision(pov=not board.turn)
	show_board(board)
	if captured_piece and captured_piece.piece_type == chess.KING:
		return not board.turn


def probe_opponent(board):
	ctx = zmq.Context()
	socket = ctx.socket(zmq.PAIR)
	socket.connect('tcp://localhost:%u' % (CHESS_PORT + board.fullmove_number * 2 - 1 + (not board.turn)))
	seed = urandom(32) # TODO allow Bob to ensure randomness
	logging.info('CHOSE SEED     : [%s]', prettyprint_bytes(seed))
	hseed = h(seed)
	logging.info('SEED COMMITMENT: [%s]', prettyprint_bytes(hseed))
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
	logging.info('GOT SEED COMMITMENT: [%s]', prettyprint_bytes(hseed))
	queries = []
	for i in range(1, 8):
		pkeys = socket.recv_serialized(_deserialize)
		logging.debug('GOT QUERY #%u: [%s]', i, ''.join(prettyprint_bytes(pk) for pk in pkeys))
		queries.append(pkeys)
		payload = []
		for square, pk in zip(chess.SQUARES, pkeys):
			# note: you should forget opponent pieces BEFORE running this function
			piece = board.piece_at(square)
			piece_data = piece.symbol().encode() if piece else b'\x00'
			encrypted_piece_data = pk_encrypt(pk, piece_data)
			payload.append(encrypted_piece_data)
		socket.send_serialized(payload, _serialize)
	logging.info('H(QUERIES): [%s]', prettyprint_bytes(h(bytes().join(bytes().join(query) for query in queries))))
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
	board = chess.DarkBoard(pov=color)
	if "lol" in environ:
		board.remove_piece_at(chess.D2)
		board.remove_piece_at(chess.E2)
	sys.exit(_main(board, color))
