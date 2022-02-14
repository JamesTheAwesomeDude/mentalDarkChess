from sys import stdout
from os import urandom, environ
import json
from warnings import warn
import logging
from zmq.utils.z85 import encode as z85encode, decode as z85decode
logging.basicConfig(stream=stdout, level=getattr(logging, environ.get('LOGLEVEL', 'INFO')))

import chess

from .variants import DarkBoard
from ._crypto import h, gen_fake_pubkeys, make_real_keypair, publickey, pk_encrypt, pk_decrypt
from ._protos import probe_opponent, respond_to_probe


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
	logging.info('REVEALED: %s', ','.join('%s@%s' % (piece.symbol(), chess.SQUARE_NAMES[square]) for square, piece in revealed.items() if piece))
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
